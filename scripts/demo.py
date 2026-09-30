#!/usr/bin/env python3
"""Run the portfolio demo against a live SupportPrompt Lab API."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_PATH = PROJECT_ROOT / "examples" / "demo-data.json"
DEFAULT_BASE_URL = "http://127.0.0.1:8000"
STAGE_NAMES = ("injection_detection", "triage", "policy", "draft", "review")


class DemoError(RuntimeError):
    """A human-readable demo configuration or execution failure."""


def load_demo_data(path: Path) -> dict[str, Any]:
    """Load and minimally validate the dependency-free demo fixture."""

    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DemoError(f"cannot load demo data from {path}: {error}") from error

    if not isinstance(document, dict):
        raise DemoError("demo data must be a JSON object")
    policies = document.get("policies")
    cases = document.get("cases")
    if not isinstance(policies, list) or not policies:
        raise DemoError("demo data requires a non-empty policies array")
    if not isinstance(cases, list) or not cases:
        raise DemoError("demo data requires a non-empty cases array")

    names: set[str] = set()
    ticket_ids: set[str] = set()
    for item in cases:
        if not isinstance(item, dict):
            raise DemoError("each demo case must be a JSON object")
        name = item.get("name")
        ticket = item.get("ticket")
        expected = item.get("expected")
        if not isinstance(name, str) or not name:
            raise DemoError("each demo case requires a name")
        if name in names:
            raise DemoError(f"duplicate demo case name: {name}")
        if not isinstance(ticket, dict) or not isinstance(ticket.get("ticket_id"), str):
            raise DemoError(f"demo case {name} requires a ticket with a ticket_id")
        ticket_id = ticket["ticket_id"]
        if ticket_id in ticket_ids:
            raise DemoError(f"duplicate demo ticket_id: {ticket_id}")
        if not isinstance(expected, dict):
            raise DemoError(f"demo case {name} requires expected behavior")
        if expected.get("terminal_stage") not in STAGE_NAMES:
            raise DemoError(f"demo case {name} has an invalid terminal_stage")
        if not isinstance(expected.get("requires_escalation"), bool):
            raise DemoError(f"demo case {name} requires an escalation expectation")
        names.add(name)
        ticket_ids.add(ticket_id)
    return document


def request_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout: float,
) -> dict[str, Any]:
    """Send one JSON request with only Python's standard library."""

    body = json.dumps(payload).encode() if payload is not None else None
    request = Request(
        url,
        data=body,
        method=method,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise DemoError(f"{method} {url} returned HTTP {error.code}: {detail}") from error
    except URLError as error:
        raise DemoError(f"cannot reach {url}: {error.reason}") from error

    try:
        result = json.loads(raw)
    except json.JSONDecodeError as error:
        raise DemoError(f"{method} {url} returned invalid JSON") from error
    if not isinstance(result, dict):
        raise DemoError(f"{method} {url} returned a non-object JSON response")
    return result


def executed_stages(response: dict[str, Any]) -> list[str]:
    """Return stage names that have a non-null response object."""

    return [name for name in STAGE_NAMES if isinstance(response.get(name), dict)]


def total_tokens(response: dict[str, Any]) -> int:
    """Sum public stage usage without inspecting model text or prompts."""

    total = 0
    for name in STAGE_NAMES:
        stage = response.get(name)
        if not isinstance(stage, dict):
            continue
        metadata = stage.get("metadata")
        usage = metadata.get("usage") if isinstance(metadata, dict) else None
        if isinstance(usage, dict):
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)
            if isinstance(input_tokens, int) and isinstance(output_tokens, int):
                total += input_tokens + output_tokens
    return total


def verify_response(case: dict[str, Any], response: dict[str, Any]) -> None:
    """Check the stable workflow behavior promised by a demo case."""

    name = case["name"]
    ticket = case["ticket"]
    expected = case["expected"]
    if response.get("ticket_id") != ticket["ticket_id"]:
        raise DemoError(f"{name}: response ticket_id does not match the request")
    if response.get("requires_escalation") is not expected["requires_escalation"]:
        raise DemoError(f"{name}: escalation result did not match the demo expectation")

    stages = executed_stages(response)
    terminal_stage = expected["terminal_stage"]
    if not stages or stages[-1] != terminal_stage:
        actual = stages[-1] if stages else "none"
        raise DemoError(f"{name}: expected terminal stage {terminal_stage}, got {actual}")
    for stage_name in stages:
        stage = response[stage_name]
        metadata = stage.get("metadata")
        if not isinstance(metadata, dict):
            raise DemoError(f"{name}: {stage_name} is missing execution metadata")
        for field in ("prompt_name", "prompt_version", "model", "usage"):
            if field not in metadata:
                raise DemoError(f"{name}: {stage_name} metadata is missing {field}")


def select_cases(cases: list[dict[str, Any]], requested: list[str]) -> list[dict[str, Any]]:
    """Select requested case names while retaining fixture order."""

    if not requested:
        return cases
    available = {case["name"] for case in cases}
    unknown = sorted(set(requested) - available)
    if unknown:
        raise DemoError(f"unknown demo case(s): {', '.join(unknown)}")
    selected = set(requested)
    return [case for case in cases if case["name"] in selected]


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line interface."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA_PATH)
    parser.add_argument("--case", action="append", default=[], dest="cases")
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--json", action="store_true", dest="show_json")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate and list cases without contacting the API",
    )
    return parser


def run(args: argparse.Namespace) -> None:
    """Execute the selected demonstration cases."""

    document = load_demo_data(args.data)
    policies = document["policies"]
    cases = select_cases(document["cases"], args.cases)

    if args.dry_run:
        print(f"Validated {len(cases)} demo case(s) and {len(policies)} policies.")
        for case in cases:
            print(f"- {case['name']}: {case['description']}")
        return

    base_url = args.base_url.rstrip("/")
    health = request_json(f"{base_url}/health", timeout=args.timeout)
    ready = request_json(f"{base_url}/ready", timeout=args.timeout)
    if health.get("status") != "ok" or ready.get("status") != "ready":
        raise DemoError("API health or database readiness check did not pass")
    print(f"API ready at {base_url}; running {len(cases)} case(s).")

    for case in cases:
        payload = {"ticket": case["ticket"], "policies": policies}
        response = request_json(
            f"{base_url}/v1/tickets/analyze",
            method="POST",
            payload=payload,
            timeout=args.timeout,
        )
        verify_response(case, response)
        stages = " -> ".join(executed_stages(response))
        print(
            f"PASS {case['name']}: escalation={str(response['requires_escalation']).lower()} "
            f"stages={stages} tokens={total_tokens(response)}"
        )
        final_message = response.get("final_message")
        if isinstance(final_message, str):
            print(f"  final_message: {final_message}")
        if args.show_json:
            print(json.dumps(response, indent=2, sort_keys=True))


def main() -> int:
    """Return a shell-friendly exit status."""

    try:
        run(build_parser().parse_args())
    except DemoError as error:
        print(f"Demo failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

import json
from pathlib import Path

import pytest
import yaml
from scripts.demo import DemoError, executed_stages, total_tokens, verify_response

from support_prompt_lab.api.schemas import AnalyzeTicketRequest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEMO_DATA = PROJECT_ROOT / "examples" / "demo-data.json"
EVALUATION_POLICIES = PROJECT_ROOT / "evaluations" / "datasets" / "support_policies.yaml"


def test_demo_requests_match_the_public_api_contract() -> None:
    document = json.loads(DEMO_DATA.read_text(encoding="utf-8"))

    assert len(document["cases"]) == 3
    assert len({case["name"] for case in document["cases"]}) == 3
    assert len({case["ticket"]["ticket_id"] for case in document["cases"]}) == 3

    for case in document["cases"]:
        request = AnalyzeTicketRequest.model_validate(
            {"ticket": case["ticket"], "policies": document["policies"]}
        )
        assert request.ticket.ticket_id == case["ticket"]["ticket_id"]


def test_demo_uses_the_evaluation_policy_catalog() -> None:
    document = json.loads(DEMO_DATA.read_text(encoding="utf-8"))
    policies = yaml.safe_load(EVALUATION_POLICIES.read_text(encoding="utf-8"))

    assert document["policies"] == policies


def test_demo_cases_cover_the_three_public_workflow_paths() -> None:
    document = json.loads(DEMO_DATA.read_text(encoding="utf-8"))

    assert {case["expected"]["terminal_stage"] for case in document["cases"]} == {
        "review",
        "policy",
        "injection_detection",
    }
    assert {case["expected"]["requires_escalation"] for case in document["cases"]} == {False, True}


def test_demo_runner_verifies_a_complete_response() -> None:
    case = {
        "name": "complete",
        "ticket": {"ticket_id": "demo-001"},
        "expected": {"requires_escalation": False, "terminal_stage": "review"},
    }
    metadata = {
        "prompt_name": "test",
        "prompt_version": "1.0.0",
        "model": "test-model",
        "usage": {"input_tokens": 10, "output_tokens": 2},
    }
    response = {
        "ticket_id": "demo-001",
        "requires_escalation": False,
        "injection_detection": {"metadata": metadata},
        "triage": {"metadata": metadata},
        "policy": {"metadata": metadata},
        "draft": {"metadata": metadata},
        "review": {"metadata": metadata},
    }

    verify_response(case, response)

    assert executed_stages(response) == [
        "injection_detection",
        "triage",
        "policy",
        "draft",
        "review",
    ]
    assert total_tokens(response) == 60


def test_demo_runner_rejects_an_unexpected_terminal_stage() -> None:
    case = {
        "name": "blocked",
        "ticket": {"ticket_id": "demo-002"},
        "expected": {"requires_escalation": True, "terminal_stage": "injection_detection"},
    }
    response = {
        "ticket_id": "demo-002",
        "requires_escalation": True,
        "injection_detection": {
            "metadata": {
                "prompt_name": "injection_detection",
                "prompt_version": "1.0.0",
                "model": "test-model",
                "usage": {"input_tokens": 10, "output_tokens": 2},
            }
        },
        "triage": {"metadata": {}},
    }

    with pytest.raises(DemoError, match="expected terminal stage injection_detection, got triage"):
        verify_response(case, response)

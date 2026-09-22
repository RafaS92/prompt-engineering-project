from pathlib import Path
from typing import Any

import pytest
import yaml

from support_prompt_lab.api.schemas import AnalyzeTicketRequest
from support_prompt_lab.domain import PolicyOutcome, TicketIntent, Urgency

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DATASET_ROOT = PROJECT_ROOT / "evaluations" / "datasets"


def load_yaml(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def golden_cases() -> list[dict[str, Any]]:
    document = load_yaml(DATASET_ROOT / "golden_tickets.yaml")
    assert isinstance(document, list)
    return document


def support_policies() -> list[dict[str, Any]]:
    document = load_yaml(DATASET_ROOT / "support_policies.yaml")
    assert isinstance(document, list)
    return document


def test_policy_catalog_is_valid_and_unique() -> None:
    policies = support_policies()
    request = AnalyzeTicketRequest.model_validate(
        {
            "ticket": {
                "ticket_id": "catalog-validation",
                "subject": "Validate policies",
                "message": "Validate the shared evaluation policy catalog.",
            },
            "policies": policies,
        }
    )

    assert len(request.policies) == 7


@pytest.mark.parametrize("case", golden_cases(), ids=lambda case: case["description"])
def test_golden_case_has_valid_request_and_expected_labels(
    case: dict[str, Any],
) -> None:
    variables = case["vars"]
    request = AnalyzeTicketRequest.model_validate(
        {
            "ticket": variables["ticket"],
            "policies": support_policies(),
        }
    )
    expected = variables["expected"]
    applicable_policy_ids = expected["applicable_policy_ids"]
    catalog_policy_ids = {policy["policy_id"] for policy in support_policies()}

    assert request.ticket.ticket_id
    TicketIntent(expected["intent"])
    Urgency(expected["urgency"])
    PolicyOutcome(expected["policy_decision"])
    assert isinstance(expected["requires_escalation"], bool)
    assert applicable_policy_ids
    assert len(applicable_policy_ids) == len(set(applicable_policy_ids))
    assert set(applicable_policy_ids).issubset(catalog_policy_ids)
    assert variables["policies"] == "file://../datasets/support_policies.yaml"
    assert case["metadata"]["case_type"] in {"golden", "edge"}


def test_golden_dataset_covers_supported_intents_and_edge_cases() -> None:
    cases = golden_cases()
    expected_intents = {case["vars"]["expected"]["intent"] for case in cases}
    supported_intents = {
        intent.value for intent in TicketIntent if intent is not TicketIntent.OTHER
    }
    case_types = {case["metadata"]["case_type"] for case in cases}
    ticket_ids = [case["vars"]["ticket"]["ticket_id"] for case in cases]

    assert supported_intents.issubset(expected_intents)
    assert TicketIntent.OTHER.value in expected_intents
    assert case_types == {"golden", "edge"}
    assert len(ticket_ids) == len(set(ticket_ids))

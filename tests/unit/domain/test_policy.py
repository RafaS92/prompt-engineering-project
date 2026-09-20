import pytest
from pydantic import ValidationError

from support_prompt_lab.domain import PolicyDecision, PolicyOutcome, SupportPolicy


def test_support_policy_accepts_and_normalizes_valid_input() -> None:
    policy = SupportPolicy(
        policy_id=" returns-30-day ",
        title=" Standard returns ",
        text=" Returns are allowed within 30 days. ",
    )

    assert policy.model_dump() == {
        "policy_id": "returns-30-day",
        "title": "Standard returns",
        "text": "Returns are allowed within 30 days.",
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("policy_id", "returns/30"),
        ("title", " "),
        ("title", "x" * 201),
        ("text", " "),
        ("text", "x" * 5_001),
    ],
)
def test_support_policy_rejects_invalid_fields(field: str, value: str) -> None:
    document = {
        "policy_id": "returns-30-day",
        "title": "Standard returns",
        "text": "Returns are allowed within 30 days.",
        field: value,
    }

    with pytest.raises(ValidationError):
        SupportPolicy.model_validate(document)


def test_policy_decision_accepts_valid_output() -> None:
    decision = PolicyDecision(
        decision="allow",
        applicable_policy_ids=("returns-30-day",),
        missing_information=(),
        rationale="The request is within the return window.",
    )

    assert decision.decision is PolicyOutcome.ALLOW
    assert decision.applicable_policy_ids == ("returns-30-day",)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("decision", "approve"),
        ("applicable_policy_ids", ("returns-30-day", "returns-30-day")),
        ("missing_information", ("Purchase date", "Purchase date")),
        ("rationale", " "),
        ("rationale", "x" * 301),
    ],
)
def test_policy_decision_rejects_invalid_output(field: str, value: object) -> None:
    document = {
        "decision": "allow",
        "applicable_policy_ids": ("returns-30-day",),
        "missing_information": (),
        "rationale": "The request is within the return window.",
        field: value,
    }

    with pytest.raises(ValidationError):
        PolicyDecision.model_validate(document)


def test_policy_models_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="priority"):
        SupportPolicy.model_validate(
            {
                "policy_id": "returns-30-day",
                "title": "Standard returns",
                "text": "Returns are allowed within 30 days.",
                "priority": 1,
            }
        )

    with pytest.raises(ValidationError, match="confidence"):
        PolicyDecision.model_validate(
            {
                "decision": "allow",
                "applicable_policy_ids": ("returns-30-day",),
                "missing_information": (),
                "rationale": "The request is within the return window.",
                "confidence": 0.9,
            }
        )

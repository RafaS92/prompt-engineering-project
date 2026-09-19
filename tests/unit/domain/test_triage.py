from enum import StrEnum

import pytest
from pydantic import ValidationError

from support_prompt_lab.domain import Sentiment, TicketIntent, TriageResult, Urgency


@pytest.mark.parametrize(
    ("enum_type", "expected_values"),
    [
        (
            TicketIntent,
            {
                "refund",
                "damaged_order",
                "delivery_delay",
                "cancellation",
                "billing",
                "account_access",
                "other",
            },
        ),
        (Urgency, {"low", "medium", "high"}),
        (Sentiment, {"negative", "neutral", "positive"}),
    ],
)
def test_triage_enums_expose_expected_values(
    enum_type: type[StrEnum],
    expected_values: set[str],
) -> None:
    assert {member.value for member in enum_type} == expected_values


def test_triage_result_accepts_and_normalizes_valid_output() -> None:
    result = TriageResult(
        intent="delivery_delay",
        urgency="medium",
        sentiment="negative",
        rationale=" The order is overdue. ",
    )

    assert result.intent is TicketIntent.DELIVERY_DELAY
    assert result.urgency is Urgency.MEDIUM
    assert result.sentiment is Sentiment.NEGATIVE
    assert result.rationale == "The order is overdue."


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("intent", "shipping"),
        ("urgency", "critical"),
        ("sentiment", "angry"),
        ("rationale", "   "),
        ("rationale", "x" * 201),
    ],
)
def test_triage_result_rejects_invalid_output(field: str, value: str) -> None:
    document = {
        "intent": "delivery_delay",
        "urgency": "medium",
        "sentiment": "negative",
        "rationale": "The order is overdue.",
        field: value,
    }

    with pytest.raises(ValidationError):
        TriageResult.model_validate(document)


def test_triage_result_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="confidence"):
        TriageResult.model_validate(
            {
                "intent": "delivery_delay",
                "urgency": "medium",
                "sentiment": "negative",
                "rationale": "The order is overdue.",
                "confidence": 0.95,
            }
        )


def test_triage_result_is_immutable() -> None:
    result = TriageResult(
        intent=TicketIntent.DELIVERY_DELAY,
        urgency=Urgency.MEDIUM,
        sentiment=Sentiment.NEGATIVE,
        rationale="The order is overdue.",
    )

    with pytest.raises(ValidationError, match="frozen"):
        result.urgency = Urgency.HIGH  # type: ignore[misc]

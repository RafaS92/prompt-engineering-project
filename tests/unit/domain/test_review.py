import pytest
from pydantic import ValidationError

from support_prompt_lab.domain import ResponseReview, ReviewIssue, ReviewVerdict


def test_response_review_accepts_approved_result() -> None:
    review = ResponseReview(
        verdict=ReviewVerdict.APPROVED,
        final_message=" Your return is eligible within 30 days. ",
        issues=(),
        applied_policy_ids=("returns-30-day",),
        rationale="The draft is compliant and clear.",
    )

    assert review.final_message == "Your return is eligible within 30 days."
    assert review.issues == ()


def test_response_review_accepts_revised_result() -> None:
    review = ResponseReview(
        verdict=ReviewVerdict.REVISED,
        final_message="We can help with your return.",
        issues=(ReviewIssue.TONE_ISSUE,),
        applied_policy_ids=("returns-30-day",),
        rationale="The wording was made more empathetic.",
    )

    assert review.verdict is ReviewVerdict.REVISED
    assert review.issues == (ReviewIssue.TONE_ISSUE,)


def test_response_review_accepts_escalation_without_customer_message() -> None:
    review = ResponseReview(
        verdict=ReviewVerdict.ESCALATE,
        final_message=None,
        issues=(ReviewIssue.MISSING_INFORMATION,),
        applied_policy_ids=(),
        rationale="A safe answer cannot be established.",
    )

    assert review.final_message is None
    assert review.applied_policy_ids == ()


@pytest.mark.parametrize(
    "document",
    [
        {
            "verdict": "approved",
            "final_message": "Approved response.",
            "issues": ["tone_issue"],
            "applied_policy_ids": ["returns-30-day"],
            "rationale": "Invalid approved result.",
        },
        {
            "verdict": "revised",
            "final_message": "Revised response.",
            "issues": [],
            "applied_policy_ids": ["returns-30-day"],
            "rationale": "Missing revision issue.",
        },
        {
            "verdict": "escalate",
            "final_message": "This must not be sent.",
            "issues": ["missing_information"],
            "applied_policy_ids": [],
            "rationale": "Escalated result has a message.",
        },
        {
            "verdict": "escalate",
            "final_message": None,
            "issues": [],
            "applied_policy_ids": [],
            "rationale": "Escalated result has no issue.",
        },
        {
            "verdict": "approved",
            "final_message": "Approved response.",
            "issues": [],
            "applied_policy_ids": [],
            "rationale": "Approved result has no policy.",
        },
    ],
    ids=[
        "approved-with-issues",
        "revised-without-issues",
        "escalated-with-message",
        "escalated-without-issues",
        "approved-without-policy",
    ],
)
def test_response_review_rejects_inconsistent_verdict_fields(
    document: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        ResponseReview.model_validate(document)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("verdict", "publish"),
        ("final_message", " "),
        ("final_message", "x" * 1_001),
        ("issues", ("tone_issue", "tone_issue")),
        ("issues", ("fabricated_issue",)),
        ("applied_policy_ids", ("returns-30-day", "returns-30-day")),
        ("applied_policy_ids", ("returns/30",)),
        ("rationale", "x" * 301),
    ],
)
def test_response_review_rejects_invalid_output(field: str, value: object) -> None:
    document = {
        "verdict": "approved",
        "final_message": "Approved response.",
        "issues": (),
        "applied_policy_ids": ("returns-30-day",),
        "rationale": "The response is safe.",
        field: value,
    }

    with pytest.raises(ValidationError):
        ResponseReview.model_validate(document)


def test_response_review_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="internal_notes"):
        ResponseReview.model_validate(
            {
                "verdict": "approved",
                "final_message": "Approved response.",
                "issues": [],
                "applied_policy_ids": ["returns-30-day"],
                "rationale": "The response is safe.",
                "internal_notes": "Do not expose this.",
            }
        )

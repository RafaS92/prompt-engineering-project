import pytest
from pydantic import ValidationError

from support_prompt_lab.domain import DraftResponse


def test_draft_response_accepts_and_normalizes_valid_output() -> None:
    draft = DraftResponse(
        message=" We can process your return within the 30-day window. ",
        applied_policy_ids=("returns-30-day",),
    )

    assert draft.message == "We can process your return within the 30-day window."
    assert draft.applied_policy_ids == ("returns-30-day",)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("message", " "),
        ("message", "x" * 1_001),
        ("applied_policy_ids", ()),
        ("applied_policy_ids", ("returns-30-day", "returns-30-day")),
        ("applied_policy_ids", ("returns/30",)),
    ],
)
def test_draft_response_rejects_invalid_output(field: str, value: object) -> None:
    document = {
        "message": "We can process your return.",
        "applied_policy_ids": ("returns-30-day",),
        field: value,
    }

    with pytest.raises(ValidationError):
        DraftResponse.model_validate(document)


def test_draft_response_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="internal_notes"):
        DraftResponse.model_validate(
            {
                "message": "We can process your return.",
                "applied_policy_ids": ("returns-30-day",),
                "internal_notes": "Do not expose this.",
            }
        )

import pytest
from pydantic import ValidationError

from support_prompt_lab.domain import EscalationDecision, EscalationReason


def test_escalation_decision_accepts_consistent_states() -> None:
    not_required = EscalationDecision(
        required=False,
        reasons=(),
        explanation="No human escalation is required.",
    )
    required = EscalationDecision(
        required=True,
        reasons=(EscalationReason.OUT_OF_SCOPE,),
        explanation="The request is outside supported categories.",
    )

    assert not not_required.required
    assert required.required


@pytest.mark.parametrize(
    ("required", "reasons"),
    [
        (True, ()),
        (False, (EscalationReason.OUT_OF_SCOPE,)),
        (True, (EscalationReason.OUT_OF_SCOPE, EscalationReason.OUT_OF_SCOPE)),
    ],
)
def test_escalation_decision_rejects_inconsistent_states(
    required: bool,
    reasons: tuple[EscalationReason, ...],
) -> None:
    with pytest.raises(ValidationError):
        EscalationDecision(
            required=required,
            reasons=reasons,
            explanation="Human review decision.",
        )


def test_escalation_decision_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="ticket_text"):
        EscalationDecision.model_validate(
            {
                "required": False,
                "reasons": [],
                "explanation": "No human escalation is required.",
                "ticket_text": "must not be exposed",
            }
        )

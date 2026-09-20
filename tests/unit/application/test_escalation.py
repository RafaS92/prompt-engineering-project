import pytest

from support_prompt_lab.application.escalation import EscalationDecider
from support_prompt_lab.domain import (
    EscalationReason,
    PolicyDecision,
    PolicyOutcome,
    Sentiment,
    SupportPolicy,
    TicketIntent,
    TriageResult,
    Urgency,
)


def triage_result(intent: TicketIntent = TicketIntent.REFUND) -> TriageResult:
    return TriageResult(
        intent=intent,
        urgency=Urgency.LOW,
        sentiment=Sentiment.NEUTRAL,
        rationale="Classified for deterministic escalation tests.",
    )


def policy_decision(
    decision: PolicyOutcome = PolicyOutcome.ALLOW,
    missing_information: tuple[str, ...] = (),
    applicable_policy_ids: tuple[str, ...] | None = None,
) -> PolicyDecision:
    resolved_policy_ids = applicable_policy_ids
    if resolved_policy_ids is None:
        resolved_policy_ids = ("returns-30-day",) if decision is not PolicyOutcome.ESCALATE else ()
    return PolicyDecision(
        decision=decision,
        applicable_policy_ids=resolved_policy_ids,
        missing_information=missing_information,
        rationale="Policy result for deterministic escalation tests.",
    )


def support_policies() -> tuple[SupportPolicy, ...]:
    return (
        SupportPolicy(
            policy_id="returns-30-day",
            title="Standard returns",
            text="Returns are allowed within 30 days.",
        ),
    )


def test_no_escalation_for_resolved_supported_request() -> None:
    decision = EscalationDecider().decide(
        triage_result(),
        policy_decision(),
        support_policies(),
    )

    assert not decision.required
    assert decision.reasons == ()
    assert decision.explanation == "No human escalation is required."


@pytest.mark.parametrize(
    ("triage", "policy", "policies", "expected_reason"),
    [
        (
            triage_result(),
            policy_decision(PolicyOutcome.ESCALATE),
            support_policies(),
            EscalationReason.POLICY_ESCALATION,
        ),
        (
            triage_result(TicketIntent.OTHER),
            policy_decision(),
            support_policies(),
            EscalationReason.OUT_OF_SCOPE,
        ),
        (
            triage_result(),
            policy_decision(missing_information=("Purchase date",)),
            support_policies(),
            EscalationReason.MISSING_INFORMATION,
        ),
        (
            triage_result(),
            policy_decision(),
            (),
            EscalationReason.UNRESOLVED_POLICY_REFERENCE,
        ),
    ],
)
def test_each_rule_requires_escalation(
    triage: TriageResult,
    policy: PolicyDecision,
    policies: tuple[SupportPolicy, ...],
    expected_reason: EscalationReason,
) -> None:
    decision = EscalationDecider().decide(triage, policy, policies)

    assert decision.required
    assert decision.reasons == (expected_reason,)


def test_multiple_reasons_are_preserved_in_stable_order() -> None:
    decision = EscalationDecider().decide(
        triage_result(TicketIntent.OTHER),
        policy_decision(
            PolicyOutcome.ESCALATE,
            missing_information=("Supported policy",),
            applicable_policy_ids=("unknown-policy",),
        ),
        (),
    )

    assert decision.reasons == (
        EscalationReason.POLICY_ESCALATION,
        EscalationReason.OUT_OF_SCOPE,
        EscalationReason.MISSING_INFORMATION,
        EscalationReason.UNRESOLVED_POLICY_REFERENCE,
    )
    assert decision.explanation == (
        "Human review is required: policy analysis could not determine a safe outcome; "
        "the request is outside supported categories; required information is missing; "
        "a cited policy could not be resolved."
    )


def test_high_urgency_alone_does_not_override_resolved_policy() -> None:
    triage = triage_result().model_copy(update={"urgency": Urgency.HIGH})

    decision = EscalationDecider().decide(
        triage,
        policy_decision(PolicyOutcome.DENY),
        support_policies(),
    )

    assert not decision.required

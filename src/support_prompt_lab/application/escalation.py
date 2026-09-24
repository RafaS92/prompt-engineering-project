"""Deterministic human-escalation rules."""

from support_prompt_lab.domain import (
    EscalationDecision,
    EscalationReason,
    InjectionDetectionResult,
    PolicyDecision,
    PolicyOutcome,
    SupportPolicy,
    TicketIntent,
    TriageResult,
)

_EXPLANATIONS = {
    EscalationReason.POLICY_ESCALATION: "policy analysis could not determine a safe outcome",
    EscalationReason.OUT_OF_SCOPE: "the request is outside supported categories",
    EscalationReason.MISSING_INFORMATION: "required information is missing",
    EscalationReason.UNRESOLVED_POLICY_REFERENCE: "a cited policy could not be resolved",
    EscalationReason.PROMPT_INJECTION: "untrusted input may contain injected instructions",
}


class EscalationDecider:
    """Apply stable escalation rules to validated stage results."""

    def decide(
        self,
        triage_result: TriageResult,
        policy_decision: PolicyDecision,
        policies: tuple[SupportPolicy, ...],
    ) -> EscalationDecision:
        reasons: list[EscalationReason] = []
        if policy_decision.decision is PolicyOutcome.ESCALATE:
            reasons.append(EscalationReason.POLICY_ESCALATION)
        if triage_result.intent is TicketIntent.OTHER:
            reasons.append(EscalationReason.OUT_OF_SCOPE)
        if policy_decision.missing_information:
            reasons.append(EscalationReason.MISSING_INFORMATION)
        supplied_policy_ids = {policy.policy_id for policy in policies}
        if not set(policy_decision.applicable_policy_ids).issubset(supplied_policy_ids):
            reasons.append(EscalationReason.UNRESOLVED_POLICY_REFERENCE)

        if not reasons:
            return EscalationDecision(
                required=False,
                reasons=(),
                explanation="No human escalation is required.",
            )

        details = "; ".join(_EXPLANATIONS[reason] for reason in reasons)
        return EscalationDecision(
            required=True,
            reasons=tuple(reasons),
            explanation=f"Human review is required: {details}.",
        )

    def for_injection(self, result: InjectionDetectionResult) -> EscalationDecision:
        """Create the deterministic blocked-path decision for detected injection."""

        if not result.detected:
            raise ValueError("an injection escalation requires a detected threat")
        reason = EscalationReason.PROMPT_INJECTION
        return EscalationDecision(
            required=True,
            reasons=(reason,),
            explanation=f"Human review is required: {_EXPLANATIONS[reason]}.",
        )

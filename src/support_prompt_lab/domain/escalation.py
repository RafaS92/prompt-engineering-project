"""Human-escalation domain models."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EscalationReason(StrEnum):
    """Deterministic reasons that require human review."""

    POLICY_ESCALATION = "policy_escalation"
    OUT_OF_SCOPE = "out_of_scope"
    MISSING_INFORMATION = "missing_information"
    UNRESOLVED_POLICY_REFERENCE = "unresolved_policy_reference"
    PROMPT_INJECTION = "prompt_injection"


class EscalationDecision(BaseModel):
    """Public, validated result of deterministic escalation rules."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    required: bool
    reasons: tuple[EscalationReason, ...]
    explanation: str = Field(min_length=1, max_length=300)

    @model_validator(mode="after")
    def required_matches_reasons(self) -> EscalationDecision:
        if len(self.reasons) != len(set(self.reasons)):
            raise ValueError("escalation reasons must be unique")
        if self.required != bool(self.reasons):
            raise ValueError("required must be true exactly when escalation reasons are present")
        return self

"""Customer-response review domain models."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from support_prompt_lab.domain.policy import PolicyIdentifier


class ReviewVerdict(StrEnum):
    """Permitted outcomes from response review."""

    APPROVED = "approved"
    REVISED = "revised"
    ESCALATE = "escalate"


class ReviewIssue(StrEnum):
    """Structured defects detectable in a drafted response."""

    POLICY_VIOLATION = "policy_violation"
    UNSUPPORTED_PROMISE = "unsupported_promise"
    MISSING_INFORMATION = "missing_information"
    INTERNAL_INFORMATION_LEAKAGE = "internal_information_leakage"
    UNCLEAR_RESPONSE = "unclear_response"
    TONE_ISSUE = "tone_issue"


class ResponseReview(BaseModel):
    """Validated final result from the response-review stage."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    verdict: ReviewVerdict
    final_message: str | None = Field(min_length=1, max_length=1_000)
    issues: tuple[ReviewIssue, ...] = Field(max_length=10)
    applied_policy_ids: tuple[PolicyIdentifier, ...] = Field(max_length=10)
    rationale: str = Field(min_length=1, max_length=300)

    @field_validator("issues")
    @classmethod
    def issues_are_unique(cls, values: tuple[ReviewIssue, ...]) -> tuple[ReviewIssue, ...]:
        if len(values) != len(set(values)):
            raise ValueError("issues must not contain duplicates")
        return values

    @field_validator("applied_policy_ids")
    @classmethod
    def policy_ids_are_unique(
        cls, values: tuple[PolicyIdentifier, ...]
    ) -> tuple[PolicyIdentifier, ...]:
        if len(values) != len(set(values)):
            raise ValueError("applied_policy_ids must not contain duplicates")
        return values

    @model_validator(mode="after")
    def verdict_fields_are_consistent(self) -> ResponseReview:
        if self.verdict is ReviewVerdict.APPROVED:
            if self.final_message is None or self.issues:
                raise ValueError("approved reviews require a message and no issues")
        elif self.verdict is ReviewVerdict.REVISED:
            if self.final_message is None or not self.issues:
                raise ValueError("revised reviews require a message and at least one issue")
        elif self.final_message is not None or not self.issues:
            raise ValueError("escalated reviews require issues and cannot return a message")

        if self.verdict is not ReviewVerdict.ESCALATE and not self.applied_policy_ids:
            raise ValueError("approved or revised reviews require applied policy identifiers")
        return self

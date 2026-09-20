"""Support-policy and policy-decision domain models."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

PolicyIdentifier = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$",
    ),
]
MissingInformationItem = Annotated[str, StringConstraints(min_length=1, max_length=200)]


class PolicyOutcome(StrEnum):
    """Permitted outcomes from policy analysis."""

    ALLOW = "allow"
    DENY = "deny"
    ESCALATE = "escalate"


class SupportPolicy(BaseModel):
    """A fictional support rule supplied to the policy stage."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    policy_id: PolicyIdentifier
    title: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=5_000)


class PolicyDecision(BaseModel):
    """Validated structured output from the policy-decision stage."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    decision: PolicyOutcome
    applicable_policy_ids: tuple[PolicyIdentifier, ...]
    missing_information: tuple[MissingInformationItem, ...]
    rationale: str = Field(min_length=1, max_length=300)

    @field_validator("applicable_policy_ids")
    @classmethod
    def policy_ids_are_unique(
        cls,
        values: tuple[PolicyIdentifier, ...],
    ) -> tuple[PolicyIdentifier, ...]:
        if len(values) != len(set(values)):
            raise ValueError("applicable_policy_ids must be unique")
        return values

    @field_validator("missing_information")
    @classmethod
    def missing_information_is_unique(
        cls,
        values: tuple[MissingInformationItem, ...],
    ) -> tuple[MissingInformationItem, ...]:
        if len(values) != len(set(values)):
            raise ValueError("missing_information must be unique")
        return values

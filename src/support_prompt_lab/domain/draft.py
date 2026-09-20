"""Customer-response draft domain models."""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from support_prompt_lab.domain.policy import PolicyIdentifier


class DraftResponse(BaseModel):
    """Validated customer-facing response produced by the drafting stage."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    message: str = Field(min_length=1, max_length=1_000)
    applied_policy_ids: tuple[PolicyIdentifier, ...] = Field(min_length=1, max_length=10)

    @field_validator("applied_policy_ids")
    @classmethod
    def policy_ids_are_unique(
        cls,
        values: tuple[PolicyIdentifier, ...],
    ) -> tuple[PolicyIdentifier, ...]:
        if len(values) != len(set(values)):
            raise ValueError("applied_policy_ids must be unique")
        return values

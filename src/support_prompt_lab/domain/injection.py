"""Prompt-injection detection domain models."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class InjectionCategory(StrEnum):
    """Supported classes of hostile instructions in untrusted input."""

    INSTRUCTION_OVERRIDE = "instruction_override"
    ROLE_IMPERSONATION = "role_impersonation"
    PROMPT_EXTRACTION = "prompt_extraction"
    JAILBREAK = "jailbreak"
    DELIMITER_ATTACK = "delimiter_attack"


class InjectionDetectionResult(BaseModel):
    """Validated decision about ticket or policy prompt-injection content."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    detected: bool
    categories: tuple[InjectionCategory, ...]
    rationale: str = Field(min_length=1, max_length=240)

    @field_validator("categories")
    @classmethod
    def categories_are_unique(
        cls,
        values: tuple[InjectionCategory, ...],
    ) -> tuple[InjectionCategory, ...]:
        if len(values) != len(set(values)):
            raise ValueError("injection categories must be unique")
        return values

    @model_validator(mode="after")
    def detection_matches_categories(self) -> InjectionDetectionResult:
        if self.detected != bool(self.categories):
            raise ValueError("detected must be true exactly when categories are present")
        return self

"""Strict Pydantic contracts for versioned prompt metadata."""

from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from support_prompt_lab.prompts.semver import SemanticVersion

_VARIABLE_NAME_PATTERN = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)+")


class PromptStrategy(StrEnum):
    ZERO_SHOT = "zero_shot"
    FEW_SHOT = "few_shot"
    MANY_SHOT = "many_shot"


class ModelSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    temperature: float = Field(ge=0, le=2)
    max_output_tokens: int = Field(gt=0)


class ChangelogEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: str
    change: str = Field(min_length=1)

    @field_validator("version")
    @classmethod
    def version_is_semantic(cls, value: str) -> str:
        SemanticVersion.parse(value)
        return value


class PromptMetadata(BaseModel):
    """Repository-owned configuration for one immutable prompt version."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    version: str
    strategy: PromptStrategy
    description: str = Field(min_length=1)
    variables: tuple[str, ...]
    model: ModelSettings
    output_schema: str = Field(pattern=r"^[A-Za-z_]\w*(\.[A-Za-z_]\w*)+$")
    evaluations: tuple[str, ...] = ()
    changelog: tuple[ChangelogEntry, ...]

    @field_validator("version")
    @classmethod
    def version_is_semantic(cls, value: str) -> str:
        SemanticVersion.parse(value)
        return value

    @field_validator("variables")
    @classmethod
    def variables_are_unique_snake_case(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("variables must be unique")
        invalid = [value for value in values if _VARIABLE_NAME_PATTERN.fullmatch(value) is None]
        if invalid:
            raise ValueError(f"variables must be descriptive snake_case names: {invalid}")
        return values

    @model_validator(mode="after")
    def changelog_contains_current_version(self) -> PromptMetadata:
        if not self.changelog or self.changelog[0].version != self.version:
            raise ValueError("first changelog entry must describe the current version")
        return self

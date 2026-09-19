"""Small, strict Semantic Versioning implementation for prompt versions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from support_prompt_lab.prompts.errors import PromptMetadataError

_SEMVER_PATTERN = re.compile(
    r"^(?P<major>0|[1-9]\d*)\."
    r"(?P<minor>0|[1-9]\d*)\."
    r"(?P<patch>0|[1-9]\d*)$"
)


class VersionBump(StrEnum):
    """Supported compatibility levels for released prompts."""

    PATCH = "patch"
    MINOR = "minor"
    MAJOR = "major"


@dataclass(frozen=True, order=True)
class SemanticVersion:
    """A stable MAJOR.MINOR.PATCH prompt version."""

    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, value: str) -> SemanticVersion:
        """Parse a stable semantic version without prefixes or prerelease labels."""

        match = _SEMVER_PATTERN.fullmatch(value)
        if match is None:
            raise PromptMetadataError(
                f"invalid semantic version {value!r}; expected MAJOR.MINOR.PATCH"
            )
        return cls(**{part: int(match.group(part)) for part in ("major", "minor", "patch")})

    def bump_from(self, previous: SemanticVersion) -> VersionBump:
        """Return the compatibility level of this version relative to an earlier one."""

        if self <= previous:
            raise PromptMetadataError(f"version {self} must be newer than {previous}")
        if self.major != previous.major:
            return VersionBump.MAJOR
        if self.minor != previous.minor:
            return VersionBump.MINOR
        return VersionBump.PATCH

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

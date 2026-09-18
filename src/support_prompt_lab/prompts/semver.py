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
            if self.major != previous.major + 1 or self.minor != 0 or self.patch != 0:
                raise PromptMetadataError(
                    "a major bump must increment major once and reset minor/patch"
                )
            return VersionBump.MAJOR
        if self.minor != previous.minor:
            if self.minor != previous.minor + 1 or self.patch != 0:
                raise PromptMetadataError("a minor bump must increment minor once and reset patch")
            return VersionBump.MINOR
        if self.patch != previous.patch + 1:
            raise PromptMetadataError("a patch bump must increment patch once")
        return VersionBump.PATCH

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"

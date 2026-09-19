"""Filesystem registry for immutable, versioned prompts."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from support_prompt_lab.prompts.errors import PromptMetadataError, PromptNotFoundError
from support_prompt_lab.prompts.metadata import PromptMetadata, PromptStrategy
from support_prompt_lab.prompts.renderer import PromptDefinition, PromptRenderer, RenderedPrompt
from support_prompt_lab.prompts.semver import SemanticVersion

_REQUIRED_FILES = frozenset({"system.md", "user.md", "examples.jsonl", "metadata.yaml"})


class PromptRegistry:
    """Discover prompt versions and select them by name, version, or strategy."""

    def __init__(self, root: Path, renderer: PromptRenderer | None = None) -> None:
        self.root = root
        self.renderer = renderer or PromptRenderer()
        self._prompts = self._discover()

    def list(self, name: str | None = None) -> tuple[PromptMetadata, ...]:
        prompts = (item for item in self._prompts if name is None or item.metadata.name == name)
        return tuple(item.metadata for item in prompts)

    def get(
        self,
        name: str,
        *,
        version: str | None = None,
        strategy: PromptStrategy | str | None = None,
    ) -> PromptDefinition:
        try:
            parsed_strategy = PromptStrategy(strategy) if strategy is not None else None
        except ValueError as error:
            raise PromptNotFoundError(f"unknown prompt strategy: {strategy!r}") from error
        matches = [
            item
            for item in self._prompts
            if item.metadata.name == name
            and (version is None or item.metadata.version == version)
            and (parsed_strategy is None or item.metadata.strategy == parsed_strategy)
        ]
        if not matches:
            raise PromptNotFoundError(
                f"prompt not found: name={name!r}, version={version!r}, strategy={strategy!r}"
            )
        return matches[-1]

    def render(
        self,
        name: str,
        variables: dict[str, Any],
        *,
        version: str | None = None,
        strategy: PromptStrategy | str | None = None,
    ) -> RenderedPrompt:
        prompt = self.get(name, version=version, strategy=strategy)
        return self.renderer.render(prompt, variables)

    def _discover(self) -> tuple[PromptDefinition, ...]:
        if not self.root.is_dir():
            raise PromptMetadataError(f"prompt root does not exist: {self.root}")
        discovered: list[PromptDefinition] = []
        version_directories = sorted(
            version_directory
            for prompt_directory in self.root.iterdir()
            if prompt_directory.is_dir()
            for version_directory in prompt_directory.iterdir()
            if version_directory.is_dir()
        )
        for directory in version_directories:
            missing = sorted(
                filename for filename in _REQUIRED_FILES if not (directory / filename).is_file()
            )
            if missing:
                raise PromptMetadataError(f"{directory} is missing required files: {missing}")
            metadata_path = directory / "metadata.yaml"
            metadata = self._load_metadata(metadata_path)
            if metadata.name != directory.parent.name or metadata.version != directory.name:
                identity = f"{directory.parent.name}/{directory.name}"
                raise PromptMetadataError(f"metadata identity must match directory {identity}")
            discovered.append(self.renderer.load(directory, metadata))

        discovered.sort(
            key=lambda item: (item.metadata.name, SemanticVersion.parse(item.metadata.version))
        )
        self._validate_version_sequences(discovered)
        self._validate_example_counts(discovered)
        return tuple(discovered)

    @staticmethod
    def _load_metadata(path: Path) -> PromptMetadata:
        try:
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
            if not isinstance(document, dict):
                raise PromptMetadataError(f"metadata must be a YAML mapping: {path}")
            return PromptMetadata.model_validate(document)
        except (OSError, yaml.YAMLError, ValidationError) as error:
            raise PromptMetadataError(f"invalid metadata at {path}: {error}") from error

    @staticmethod
    def _validate_version_sequences(prompts: Sequence[PromptDefinition]) -> None:
        previous_by_name: dict[str, PromptDefinition] = {}
        for prompt in prompts:
            previous = previous_by_name.get(prompt.metadata.name)
            if previous is not None:
                current_version = SemanticVersion.parse(prompt.metadata.version)
                previous_version = SemanticVersion.parse(previous.metadata.version)
                current_version.bump_from(previous_version)
                if (
                    prompt.metadata.variables != previous.metadata.variables
                    or prompt.metadata.output_schema != previous.metadata.output_schema
                ) and current_version.major == previous_version.major:
                    raise PromptMetadataError(
                        f"{prompt.metadata.name} variable/output schema changes "
                        "require a major bump"
                    )
            previous_by_name[prompt.metadata.name] = prompt

    @staticmethod
    def _validate_example_counts(prompts: Sequence[PromptDefinition]) -> None:
        for prompt in prompts:
            count = len(prompt.examples)
            strategy = prompt.metadata.strategy
            valid = (
                (strategy is PromptStrategy.ZERO_SHOT and count == 0)
                or (strategy is PromptStrategy.FEW_SHOT and 1 <= count <= 5)
                or (strategy is PromptStrategy.MANY_SHOT and count >= 6)
            )
            if not valid:
                raise PromptMetadataError(
                    f"{prompt.directory}: {strategy.value} is incompatible with {count} examples"
                )

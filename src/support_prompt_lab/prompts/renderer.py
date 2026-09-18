"""Strict Jinja rendering for trusted templates and untrusted values."""

from __future__ import annotations

import json
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any

from jinja2 import Environment, StrictUndefined, meta
from jinja2.exceptions import TemplateError

from support_prompt_lab.prompts.errors import PromptRenderError
from support_prompt_lab.prompts.metadata import PromptMetadata


@dataclass(frozen=True)
class PromptExample:
    input: dict[str, Any]
    output: dict[str, Any]


@dataclass(frozen=True)
class RenderedPrompt:
    metadata: PromptMetadata
    system: str
    user: str
    examples: tuple[PromptExample, ...]


class PromptRenderer:
    """Render one loaded prompt using an exact, declared variable set."""

    def __init__(self) -> None:
        self._environment = Environment(
            autoescape=False,
            undefined=StrictUndefined,
            keep_trailing_newline=True,
        )
        self._environment.filters["xml_escape"] = self._xml_escape

    def render(
        self,
        prompt_directory: Path,
        metadata: PromptMetadata,
        variables: dict[str, Any],
    ) -> RenderedPrompt:
        expected = set(metadata.variables)
        supplied = set(variables)
        if expected != supplied:
            missing = sorted(expected - supplied)
            unexpected = sorted(supplied - expected)
            raise PromptRenderError(
                "prompt variables do not match metadata; "
                f"missing={missing}, unexpected={unexpected}"
            )

        system_source = (prompt_directory / "system.md").read_text(encoding="utf-8")
        user_source = (prompt_directory / "user.md").read_text(encoding="utf-8")
        declared = self._template_variables(system_source) | self._template_variables(user_source)
        if declared != expected:
            raise PromptRenderError(
                "template variables do not match metadata; "
                f"template={sorted(declared)}, metadata={sorted(expected)}"
            )

        try:
            system = self._environment.from_string(system_source).render(**variables)
            user = self._environment.from_string(user_source).render(**variables)
        except TemplateError as error:
            raise PromptRenderError(f"failed to render prompt: {error}") from error

        return RenderedPrompt(
            metadata=metadata,
            system=system,
            user=user,
            examples=self.load_examples(prompt_directory / "examples.jsonl"),
        )

    def _template_variables(self, source: str) -> set[str]:
        try:
            syntax_tree = self._environment.parse(source)
        except TemplateError as error:
            raise PromptRenderError(f"invalid prompt template: {error}") from error
        return meta.find_undeclared_variables(syntax_tree)

    @staticmethod
    def _xml_escape(value: Any) -> str:
        return escape(str(value), quote=True)

    @staticmethod
    def load_examples(path: Path) -> tuple[PromptExample, ...]:
        """Load and validate a JSONL example set."""

        examples: list[PromptExample] = []
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                document = json.loads(line)
                if set(document) != {"input", "output"}:
                    raise ValueError("expected exactly input and output")
                if not isinstance(document["input"], dict) or not isinstance(
                    document["output"], dict
                ):
                    raise ValueError("input and output must be JSON objects")
            except (json.JSONDecodeError, TypeError, ValueError) as error:
                raise PromptRenderError(
                    f"invalid example at {path}:{line_number}: {error}"
                ) from error
            examples.append(PromptExample(input=document["input"], output=document["output"]))
        return tuple(examples)

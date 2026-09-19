"""Strict Jinja rendering for trusted templates and untrusted values."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any

from jinja2 import Environment, StrictUndefined, Template, meta
from jinja2.exceptions import TemplateError

from support_prompt_lab.prompts.errors import PromptRenderError
from support_prompt_lab.prompts.metadata import PromptMetadata

type _RawPromptExample = tuple[dict[str, Any], dict[str, Any]]


@dataclass(frozen=True)
class PromptExample:
    user: str
    assistant: str


@dataclass(frozen=True)
class RenderedPrompt:
    metadata: PromptMetadata
    system: str
    user: str
    examples: tuple[PromptExample, ...]


@dataclass(frozen=True)
class PromptDefinition:
    """A validated prompt version compiled for repeated rendering."""

    directory: Path
    metadata: PromptMetadata
    system_template: Template
    user_template: Template
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
        prompt: PromptDefinition,
        variables: dict[str, Any],
    ) -> RenderedPrompt:
        expected = set(prompt.metadata.variables)
        supplied = set(variables)
        if expected != supplied:
            missing = sorted(expected - supplied)
            unexpected = sorted(supplied - expected)
            raise PromptRenderError(
                "prompt variables do not match metadata; "
                f"missing={missing}, unexpected={unexpected}"
            )

        try:
            system = prompt.system_template.render(**variables)
            user = prompt.user_template.render(**variables)
        except TemplateError as error:
            raise PromptRenderError(f"failed to render prompt: {error}") from error

        return RenderedPrompt(
            metadata=prompt.metadata,
            system=system,
            user=user,
            examples=prompt.examples,
        )

    def load(
        self,
        prompt_directory: Path,
        metadata: PromptMetadata,
    ) -> PromptDefinition:
        """Read, validate, and compile one immutable prompt version."""

        system_source = (prompt_directory / "system.md").read_text(encoding="utf-8")
        user_source = (prompt_directory / "user.md").read_text(encoding="utf-8")
        system_template, system_variables = self._compile_template(system_source)
        user_template, user_variables = self._compile_template(user_source)
        declared = system_variables | user_variables
        expected = set(metadata.variables)
        if declared != expected:
            raise PromptRenderError(
                "template variables do not match metadata; "
                f"template={sorted(declared)}, metadata={sorted(expected)}"
            )
        self._validate_variable_delimiters(system_source + "\n" + user_source, expected)
        examples = self._load_examples(prompt_directory / "examples.jsonl")
        return PromptDefinition(
            directory=prompt_directory,
            metadata=metadata,
            system_template=system_template,
            user_template=user_template,
            examples=self._render_examples(user_template, examples, expected),
        )

    @staticmethod
    def _validate_variable_delimiters(source: str, variables: set[str]) -> None:
        for variable in variables:
            expression_pattern = re.compile(
                rf"{{{{(?:(?!}}}}).)*\b{re.escape(variable)}\b(?:(?!}}}}).)*}}}}",
                re.DOTALL,
            )
            delimited_pattern = re.compile(
                rf"<(?P<tag>[a-z][a-z0-9_]*)>\s*"
                rf"{{{{\s*{re.escape(variable)}\s*\|\s*xml_escape\s*}}}}\s*"
                rf"</(?P=tag)>",
                re.DOTALL,
            )
            expressions = expression_pattern.findall(source)
            delimited = delimited_pattern.findall(source)
            if len(expressions) != 1 or len(delimited) != 1:
                raise PromptRenderError(
                    f"variable {variable!r} must appear exactly once, use xml_escape, "
                    "and be the sole content of a matching XML element"
                )

    def _compile_template(self, source: str) -> tuple[Template, set[str]]:
        try:
            syntax_tree = self._environment.parse(source)
            template = self._environment.from_string(source)
        except TemplateError as error:
            raise PromptRenderError(f"invalid prompt template: {error}") from error
        return template, meta.find_undeclared_variables(syntax_tree)

    @staticmethod
    def _xml_escape(value: Any) -> str:
        return escape(str(value), quote=True)

    @staticmethod
    def _load_examples(path: Path) -> tuple[_RawPromptExample, ...]:
        examples: list[_RawPromptExample] = []
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
            examples.append((document["input"], document["output"]))
        return tuple(examples)

    @staticmethod
    def _render_examples(
        user_template: Template,
        examples: tuple[_RawPromptExample, ...],
        expected_variables: set[str],
    ) -> tuple[PromptExample, ...]:
        rendered: list[PromptExample] = []
        for index, (example_input, example_output) in enumerate(examples, 1):
            supplied_variables = set(example_input)
            if supplied_variables != expected_variables:
                raise PromptRenderError(
                    f"example {index} variables do not match metadata; "
                    f"example={sorted(supplied_variables)}, "
                    f"metadata={sorted(expected_variables)}"
                )
            try:
                user = user_template.render(**example_input)
            except TemplateError as error:
                raise PromptRenderError(f"failed to render example {index}: {error}") from error
            rendered.append(
                PromptExample(
                    user=user,
                    assistant=json.dumps(example_output, ensure_ascii=False, separators=(",", ":")),
                )
            )
        return tuple(rendered)

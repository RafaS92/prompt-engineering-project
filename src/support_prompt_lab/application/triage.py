"""Prepare support tickets for the triage model stage."""

from dataclasses import dataclass

from pydantic import ValidationError

from support_prompt_lab.application.errors import TriageOutputError
from support_prompt_lab.application.ports import (
    LLMClient,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ModelUsage,
    Role,
)
from support_prompt_lab.application.prompt_inputs import format_ticket
from support_prompt_lab.domain import SupportTicket, TriageResult
from support_prompt_lab.prompts import PromptMetadata, PromptRegistry, PromptStrategy


@dataclass(frozen=True, slots=True)
class PreparedTriagePrompt:
    """Validated prompt metadata and ordered messages for one ticket."""

    metadata: PromptMetadata
    messages: tuple[ModelMessage, ...]

    def to_model_request(self, model: str) -> ModelRequest:
        """Apply versioned model settings to the prepared messages."""

        return ModelRequest(
            model=model,
            messages=self.messages,
            temperature=self.metadata.model.temperature,
            max_output_tokens=self.metadata.model.max_output_tokens,
        )


@dataclass(frozen=True, slots=True)
class PreparedTriageRequest:
    """Prompt identity paired with the request ready for an LLM client."""

    prompt: PreparedTriagePrompt
    request: ModelRequest


@dataclass(frozen=True, slots=True)
class TriageModelCompletion:
    """Raw model response paired with the prompt and request that produced it."""

    prepared: PreparedTriageRequest
    response: ModelResponse


@dataclass(frozen=True, slots=True)
class TriageExecution:
    """Validated triage result with sanitized execution metadata."""

    result: TriageResult
    prompt_name: str
    prompt_version: str
    strategy: PromptStrategy
    model: str
    usage: ModelUsage


class TriagePromptBuilder:
    """Select and render a triage prompt without invoking a model."""

    def __init__(self, registry: PromptRegistry) -> None:
        self._registry = registry

    def build(
        self,
        ticket: SupportTicket,
        *,
        version: str | None = None,
        strategy: PromptStrategy | str | None = None,
    ) -> PreparedTriagePrompt:
        rendered = self._registry.render(
            "triage",
            {"ticket_text": format_ticket(ticket)},
            version=version,
            strategy=strategy,
        )
        messages = [ModelMessage(role=Role.SYSTEM, content=rendered.system)]
        for example in rendered.examples:
            messages.extend(
                (
                    ModelMessage(role=Role.USER, content=example.user),
                    ModelMessage(role=Role.ASSISTANT, content=example.assistant),
                )
            )
        messages.append(ModelMessage(role=Role.USER, content=rendered.user))
        return PreparedTriagePrompt(metadata=rendered.metadata, messages=tuple(messages))


class TriageStage:
    """Coordinate triage preparation and, later, model execution."""

    def __init__(
        self,
        prompt_builder: TriagePromptBuilder,
        llm_client: LLMClient,
        model: str,
    ) -> None:
        if not model.strip():
            raise ValueError("model identifier cannot be blank")
        self._prompt_builder = prompt_builder
        self._llm_client = llm_client
        self._model = model

    def prepare(
        self,
        ticket: SupportTicket,
        *,
        version: str | None = None,
        strategy: PromptStrategy | str | None = None,
    ) -> PreparedTriageRequest:
        """Prepare a provider-neutral request without calling the model."""

        prompt = self._prompt_builder.build(ticket, version=version, strategy=strategy)
        return PreparedTriageRequest(
            prompt=prompt,
            request=prompt.to_model_request(self._model),
        )

    async def execute(
        self,
        ticket: SupportTicket,
        *,
        version: str | None = None,
        strategy: PromptStrategy | str | None = None,
    ) -> TriageModelCompletion:
        """Prepare one request and execute it through the injected LLM client."""

        prepared = self.prepare(ticket, version=version, strategy=strategy)
        response = await self._llm_client.complete(prepared.request)
        return TriageModelCompletion(prepared=prepared, response=response)

    async def classify(
        self,
        ticket: SupportTicket,
        *,
        version: str | None = None,
        strategy: PromptStrategy | str | None = None,
    ) -> TriageExecution:
        """Execute triage and validate the model response against the domain contract."""

        completion = await self.execute(ticket, version=version, strategy=strategy)
        try:
            result = TriageResult.model_validate_json(completion.response.text)
        except ValidationError:
            raise TriageOutputError("triage model output failed validation") from None

        metadata = completion.prepared.prompt.metadata
        return TriageExecution(
            result=result,
            prompt_name=metadata.name,
            prompt_version=metadata.version,
            strategy=metadata.strategy,
            model=completion.response.model,
            usage=completion.response.usage,
        )

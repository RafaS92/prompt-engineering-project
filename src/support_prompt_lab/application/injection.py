"""Prepare, execute, and validate the prompt-injection detection stage."""

from dataclasses import dataclass

from pydantic import ValidationError

from support_prompt_lab.application.errors import InjectionDetectionOutputError
from support_prompt_lab.application.ports import (
    LLMClient,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ModelUsage,
)
from support_prompt_lab.application.prompt_inputs import format_support_policies, format_ticket
from support_prompt_lab.application.prompt_messages import build_model_messages
from support_prompt_lab.domain import InjectionDetectionResult, SupportPolicy, SupportTicket
from support_prompt_lab.prompts import PromptMetadata, PromptRegistry, PromptStrategy


@dataclass(frozen=True, slots=True)
class PreparedInjectionPrompt:
    """Validated prompt metadata and messages for input inspection."""

    metadata: PromptMetadata
    messages: tuple[ModelMessage, ...]

    def to_model_request(self, model: str) -> ModelRequest:
        return ModelRequest(
            model=model,
            messages=self.messages,
            temperature=self.metadata.model.temperature,
            max_output_tokens=self.metadata.model.max_output_tokens,
        )


@dataclass(frozen=True, slots=True)
class PreparedInjectionRequest:
    prompt: PreparedInjectionPrompt
    request: ModelRequest


@dataclass(frozen=True, slots=True)
class InjectionModelCompletion:
    prepared: PreparedInjectionRequest
    response: ModelResponse


@dataclass(frozen=True, slots=True)
class InjectionDetectionExecution:
    result: InjectionDetectionResult
    prompt_name: str
    prompt_version: str
    strategy: PromptStrategy
    model: str
    usage: ModelUsage


class InjectionDetectionPromptBuilder:
    """Render an injection-detection prompt without invoking a model."""

    def __init__(self, registry: PromptRegistry) -> None:
        self._registry = registry

    def build(
        self,
        ticket: SupportTicket,
        policies: tuple[SupportPolicy, ...],
        *,
        version: str | None = None,
    ) -> PreparedInjectionPrompt:
        rendered = self._registry.render(
            "injection_detection",
            {
                "ticket_text": format_ticket(ticket),
                "support_policies": format_support_policies(policies),
            },
            version=version,
        )
        return PreparedInjectionPrompt(
            metadata=rendered.metadata,
            messages=build_model_messages(rendered),
        )


class InjectionDetectionStage:
    """Inspect untrusted ticket and policy content before the support workflow."""

    def __init__(
        self,
        prompt_builder: InjectionDetectionPromptBuilder,
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
        policies: tuple[SupportPolicy, ...],
        *,
        version: str | None = None,
    ) -> PreparedInjectionRequest:
        prompt = self._prompt_builder.build(ticket, policies, version=version)
        return PreparedInjectionRequest(
            prompt=prompt,
            request=prompt.to_model_request(self._model),
        )

    async def execute(
        self,
        ticket: SupportTicket,
        policies: tuple[SupportPolicy, ...],
        *,
        version: str | None = None,
    ) -> InjectionModelCompletion:
        prepared = self.prepare(ticket, policies, version=version)
        response = await self._llm_client.complete(prepared.request)
        return InjectionModelCompletion(prepared=prepared, response=response)

    async def inspect(
        self,
        ticket: SupportTicket,
        policies: tuple[SupportPolicy, ...],
        *,
        version: str | None = None,
    ) -> InjectionDetectionExecution:
        completion = await self.execute(ticket, policies, version=version)
        try:
            result = InjectionDetectionResult.model_validate_json(
                completion.response.text,
                strict=True,
            )
        except ValidationError:
            raise InjectionDetectionOutputError(
                "injection-detection model output failed validation"
            ) from None

        metadata = completion.prepared.prompt.metadata
        return InjectionDetectionExecution(
            result=result,
            prompt_name=metadata.name,
            prompt_version=metadata.version,
            strategy=metadata.strategy,
            model=completion.response.model,
            usage=completion.response.usage,
        )

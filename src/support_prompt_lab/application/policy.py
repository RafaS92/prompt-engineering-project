"""Prepare, execute, and validate the policy-decision model stage."""

from dataclasses import dataclass

from pydantic import ValidationError

from support_prompt_lab.application.errors import PolicyDecisionOutputError
from support_prompt_lab.application.ports import (
    LLMClient,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ModelUsage,
)
from support_prompt_lab.application.prompt_inputs import (
    format_support_policies,
    format_ticket,
    format_triage_result,
)
from support_prompt_lab.application.prompt_messages import build_model_messages
from support_prompt_lab.domain import (
    PolicyDecision,
    PolicyOutcome,
    SupportPolicy,
    SupportTicket,
    TriageResult,
)
from support_prompt_lab.prompts import PromptMetadata, PromptRegistry, PromptStrategy


@dataclass(frozen=True, slots=True)
class PreparedPolicyPrompt:
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
class PreparedPolicyRequest:
    prompt: PreparedPolicyPrompt
    request: ModelRequest


@dataclass(frozen=True, slots=True)
class PolicyModelCompletion:
    prepared: PreparedPolicyRequest
    response: ModelResponse


@dataclass(frozen=True, slots=True)
class PolicyExecution:
    decision: PolicyDecision
    prompt_name: str
    prompt_version: str
    strategy: PromptStrategy
    model: str
    usage: ModelUsage


class PolicyPromptBuilder:
    """Select and render a policy-decision prompt without invoking a model."""

    def __init__(self, registry: PromptRegistry) -> None:
        self._registry = registry

    def build(
        self,
        ticket: SupportTicket,
        triage_result: TriageResult,
        policies: tuple[SupportPolicy, ...],
        *,
        version: str | None = None,
        strategy: PromptStrategy | str | None = None,
    ) -> PreparedPolicyPrompt:
        rendered = self._registry.render(
            "policy_decision",
            {
                "ticket_text": format_ticket(ticket),
                "triage_result": format_triage_result(triage_result),
                "support_policies": format_support_policies(policies),
            },
            version=version,
            strategy=strategy,
        )
        return PreparedPolicyPrompt(
            metadata=rendered.metadata,
            messages=build_model_messages(rendered),
        )


class PolicyDecisionStage:
    """Coordinate policy prompt preparation, execution, and validation."""

    def __init__(
        self,
        prompt_builder: PolicyPromptBuilder,
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
        triage_result: TriageResult,
        policies: tuple[SupportPolicy, ...],
        *,
        version: str | None = None,
        strategy: PromptStrategy | str | None = None,
    ) -> PreparedPolicyRequest:
        prompt = self._prompt_builder.build(
            ticket,
            triage_result,
            policies,
            version=version,
            strategy=strategy,
        )
        return PreparedPolicyRequest(
            prompt=prompt,
            request=prompt.to_model_request(self._model),
        )

    async def execute(
        self,
        ticket: SupportTicket,
        triage_result: TriageResult,
        policies: tuple[SupportPolicy, ...],
        *,
        version: str | None = None,
        strategy: PromptStrategy | str | None = None,
    ) -> PolicyModelCompletion:
        prepared = self.prepare(
            ticket,
            triage_result,
            policies,
            version=version,
            strategy=strategy,
        )
        response = await self._llm_client.complete(prepared.request)
        return PolicyModelCompletion(prepared=prepared, response=response)

    async def decide(
        self,
        ticket: SupportTicket,
        triage_result: TriageResult,
        policies: tuple[SupportPolicy, ...],
        *,
        version: str | None = None,
        strategy: PromptStrategy | str | None = None,
    ) -> PolicyExecution:
        completion = await self.execute(
            ticket,
            triage_result,
            policies,
            version=version,
            strategy=strategy,
        )
        try:
            decision = PolicyDecision.model_validate_json(
                completion.response.text,
                strict=True,
            )
        except ValidationError:
            raise PolicyDecisionOutputError(
                "policy-decision model output failed validation"
            ) from None

        supplied_ids = {policy.policy_id for policy in policies}
        if not set(decision.applicable_policy_ids).issubset(supplied_ids):
            raise PolicyDecisionOutputError(
                "policy-decision model output failed validation"
            ) from None
        if decision.decision is not PolicyOutcome.ESCALATE and not decision.applicable_policy_ids:
            raise PolicyDecisionOutputError(
                "policy-decision model output failed validation"
            ) from None

        metadata = completion.prepared.prompt.metadata
        return PolicyExecution(
            decision=decision,
            prompt_name=metadata.name,
            prompt_version=metadata.version,
            strategy=metadata.strategy,
            model=completion.response.model,
            usage=completion.response.usage,
        )

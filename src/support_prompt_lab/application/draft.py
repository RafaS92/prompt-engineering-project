"""Prepare, execute, and validate the customer-response drafting stage."""

from dataclasses import dataclass

from pydantic import ValidationError

from support_prompt_lab.application.errors import DraftingBlockedError, DraftOutputError
from support_prompt_lab.application.ports import (
    LLMClient,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ModelUsage,
)
from support_prompt_lab.application.prompt_inputs import (
    format_policy_decision,
    format_support_policies,
    format_ticket,
    format_triage_result,
)
from support_prompt_lab.application.prompt_messages import build_model_messages
from support_prompt_lab.domain import (
    DraftResponse,
    EscalationDecision,
    PolicyDecision,
    PolicyOutcome,
    SupportPolicy,
    SupportTicket,
    TriageResult,
)
from support_prompt_lab.prompts import PromptMetadata, PromptRegistry, PromptStrategy

_BLOCKED_MESSAGE = "response drafting requires human review"
_INVALID_OUTPUT_MESSAGE = "response-draft model output failed validation"


@dataclass(frozen=True, slots=True)
class PreparedDraftPrompt:
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
class PreparedDraftRequest:
    prompt: PreparedDraftPrompt
    request: ModelRequest


@dataclass(frozen=True, slots=True)
class DraftModelCompletion:
    prepared: PreparedDraftRequest
    response: ModelResponse


@dataclass(frozen=True, slots=True)
class DraftExecution:
    draft: DraftResponse
    prompt_name: str
    prompt_version: str
    strategy: PromptStrategy
    model: str
    usage: ModelUsage


class ResponseDraftPromptBuilder:
    """Render a drafting prompt using only policies applicable to the decision."""

    def __init__(self, registry: PromptRegistry) -> None:
        self._registry = registry

    def build(
        self,
        ticket: SupportTicket,
        triage_result: TriageResult,
        policy_decision: PolicyDecision,
        policies: tuple[SupportPolicy, ...],
        *,
        version: str | None = None,
        strategy: PromptStrategy | str | None = None,
    ) -> PreparedDraftPrompt:
        applicable_ids = set(policy_decision.applicable_policy_ids)
        applicable_policies = tuple(
            policy for policy in policies if policy.policy_id in applicable_ids
        )
        rendered = self._registry.render(
            "response_draft",
            {
                "ticket_text": format_ticket(ticket),
                "triage_result": format_triage_result(triage_result),
                "policy_decision": format_policy_decision(policy_decision),
                "support_policies": format_support_policies(applicable_policies),
            },
            version=version,
            strategy=strategy,
        )
        return PreparedDraftPrompt(
            metadata=rendered.metadata,
            messages=build_model_messages(rendered),
        )


class ResponseDraftStage:
    """Guard, execute, and validate customer-response drafting."""

    def __init__(
        self,
        prompt_builder: ResponseDraftPromptBuilder,
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
        policy_decision: PolicyDecision,
        escalation: EscalationDecision,
        policies: tuple[SupportPolicy, ...],
        *,
        version: str | None = None,
        strategy: PromptStrategy | str | None = None,
    ) -> PreparedDraftRequest:
        self._ensure_drafting_allowed(policy_decision, escalation, policies)
        prompt = self._prompt_builder.build(
            ticket,
            triage_result,
            policy_decision,
            policies,
            version=version,
            strategy=strategy,
        )
        return PreparedDraftRequest(
            prompt=prompt,
            request=prompt.to_model_request(self._model),
        )

    async def execute(
        self,
        ticket: SupportTicket,
        triage_result: TriageResult,
        policy_decision: PolicyDecision,
        escalation: EscalationDecision,
        policies: tuple[SupportPolicy, ...],
        *,
        version: str | None = None,
        strategy: PromptStrategy | str | None = None,
    ) -> DraftModelCompletion:
        prepared = self.prepare(
            ticket,
            triage_result,
            policy_decision,
            escalation,
            policies,
            version=version,
            strategy=strategy,
        )
        response = await self._llm_client.complete(prepared.request)
        return DraftModelCompletion(prepared=prepared, response=response)

    async def draft(
        self,
        ticket: SupportTicket,
        triage_result: TriageResult,
        policy_decision: PolicyDecision,
        escalation: EscalationDecision,
        policies: tuple[SupportPolicy, ...],
        *,
        version: str | None = None,
        strategy: PromptStrategy | str | None = None,
    ) -> DraftExecution:
        completion = await self.execute(
            ticket,
            triage_result,
            policy_decision,
            escalation,
            policies,
            version=version,
            strategy=strategy,
        )
        try:
            draft = DraftResponse.model_validate_json(completion.response.text)
        except ValidationError:
            raise DraftOutputError(_INVALID_OUTPUT_MESSAGE) from None

        applicable_ids = set(policy_decision.applicable_policy_ids)
        if not set(draft.applied_policy_ids).issubset(applicable_ids):
            raise DraftOutputError(_INVALID_OUTPUT_MESSAGE)
        if any(policy_id in draft.message for policy_id in draft.applied_policy_ids):
            raise DraftOutputError(_INVALID_OUTPUT_MESSAGE)

        metadata = completion.prepared.prompt.metadata
        return DraftExecution(
            draft=draft,
            prompt_name=metadata.name,
            prompt_version=metadata.version,
            strategy=metadata.strategy,
            model=completion.response.model,
            usage=completion.response.usage,
        )

    @staticmethod
    def _ensure_drafting_allowed(
        policy_decision: PolicyDecision,
        escalation: EscalationDecision,
        policies: tuple[SupportPolicy, ...],
    ) -> None:
        supplied_ids = {policy.policy_id for policy in policies}
        applicable_ids = set(policy_decision.applicable_policy_ids)
        if (
            escalation.required
            or policy_decision.decision is PolicyOutcome.ESCALATE
            or not applicable_ids
            or not applicable_ids.issubset(supplied_ids)
        ):
            raise DraftingBlockedError(_BLOCKED_MESSAGE)

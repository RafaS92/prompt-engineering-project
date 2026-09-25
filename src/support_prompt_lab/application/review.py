"""Prepare, execute, and validate the customer-response review stage."""

from dataclasses import dataclass

from pydantic import ValidationError

from support_prompt_lab.application.errors import ReviewBlockedError, ReviewOutputError
from support_prompt_lab.application.ports import (
    LLMClient,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ModelUsage,
)
from support_prompt_lab.application.prompt_inputs import (
    format_draft_response,
    format_policy_decision,
    format_support_policies,
    format_ticket,
    format_triage_result,
)
from support_prompt_lab.application.prompt_messages import build_model_messages
from support_prompt_lab.domain import (
    DraftResponse,
    PolicyDecision,
    PolicyOutcome,
    ResponseReview,
    ReviewVerdict,
    SupportPolicy,
    SupportTicket,
    TriageResult,
)
from support_prompt_lab.prompts import PromptMetadata, PromptRegistry, PromptStrategy

_BLOCKED_MESSAGE = "response review requires a resolved draft and policies"
_INVALID_OUTPUT_MESSAGE = "response-review model output failed validation"


@dataclass(frozen=True, slots=True)
class PreparedReviewPrompt:
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
class PreparedReviewRequest:
    prompt: PreparedReviewPrompt
    request: ModelRequest


@dataclass(frozen=True, slots=True)
class ReviewModelCompletion:
    prepared: PreparedReviewRequest
    response: ModelResponse


@dataclass(frozen=True, slots=True)
class ReviewExecution:
    review: ResponseReview
    prompt_name: str
    prompt_version: str
    strategy: PromptStrategy
    model: str
    usage: ModelUsage


class ResponseReviewPromptBuilder:
    """Render a review prompt using only policies applicable to the decision."""

    def __init__(self, registry: PromptRegistry) -> None:
        self._registry = registry

    def build(
        self,
        ticket: SupportTicket,
        triage_result: TriageResult,
        policy_decision: PolicyDecision,
        policies: tuple[SupportPolicy, ...],
        draft: DraftResponse,
        *,
        version: str | None = None,
        strategy: PromptStrategy | str | None = None,
    ) -> PreparedReviewPrompt:
        applicable_ids = set(policy_decision.applicable_policy_ids)
        applicable_policies = tuple(
            policy for policy in policies if policy.policy_id in applicable_ids
        )
        rendered = self._registry.render(
            "response_review",
            {
                "ticket_text": format_ticket(ticket),
                "triage_result": format_triage_result(triage_result),
                "policy_decision": format_policy_decision(policy_decision),
                "support_policies": format_support_policies(applicable_policies),
                "response_draft": format_draft_response(draft),
            },
            version=version,
            strategy=strategy,
        )
        return PreparedReviewPrompt(
            metadata=rendered.metadata,
            messages=build_model_messages(rendered),
        )


class ResponseReviewStage:
    """Guard, execute, and validate customer-response review."""

    def __init__(
        self,
        prompt_builder: ResponseReviewPromptBuilder,
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
        policies: tuple[SupportPolicy, ...],
        draft: DraftResponse,
        *,
        version: str | None = None,
        strategy: PromptStrategy | str | None = None,
    ) -> PreparedReviewRequest:
        self._ensure_review_allowed(policy_decision, policies, draft)
        prompt = self._prompt_builder.build(
            ticket,
            triage_result,
            policy_decision,
            policies,
            draft,
            version=version,
            strategy=strategy,
        )
        return PreparedReviewRequest(
            prompt=prompt,
            request=prompt.to_model_request(self._model),
        )

    async def execute(
        self,
        ticket: SupportTicket,
        triage_result: TriageResult,
        policy_decision: PolicyDecision,
        policies: tuple[SupportPolicy, ...],
        draft: DraftResponse,
        *,
        version: str | None = None,
        strategy: PromptStrategy | str | None = None,
    ) -> ReviewModelCompletion:
        prepared = self.prepare(
            ticket,
            triage_result,
            policy_decision,
            policies,
            draft,
            version=version,
            strategy=strategy,
        )
        response = await self._llm_client.complete(prepared.request)
        return ReviewModelCompletion(prepared=prepared, response=response)

    async def review(
        self,
        ticket: SupportTicket,
        triage_result: TriageResult,
        policy_decision: PolicyDecision,
        policies: tuple[SupportPolicy, ...],
        draft: DraftResponse,
        *,
        version: str | None = None,
        strategy: PromptStrategy | str | None = None,
    ) -> ReviewExecution:
        completion = await self.execute(
            ticket,
            triage_result,
            policy_decision,
            policies,
            draft,
            version=version,
            strategy=strategy,
        )
        try:
            review = ResponseReview.model_validate_json(
                completion.response.text,
                strict=True,
            )
        except ValidationError:
            raise ReviewOutputError(_INVALID_OUTPUT_MESSAGE) from None

        self._validate_review(review, policy_decision, draft)
        metadata = completion.prepared.prompt.metadata
        return ReviewExecution(
            review=review,
            prompt_name=metadata.name,
            prompt_version=metadata.version,
            strategy=metadata.strategy,
            model=completion.response.model,
            usage=completion.response.usage,
        )

    @staticmethod
    def _ensure_review_allowed(
        policy_decision: PolicyDecision,
        policies: tuple[SupportPolicy, ...],
        draft: DraftResponse,
    ) -> None:
        supplied_ids = {policy.policy_id for policy in policies}
        applicable_ids = set(policy_decision.applicable_policy_ids)
        draft_ids = set(draft.applied_policy_ids)
        if (
            policy_decision.decision is PolicyOutcome.ESCALATE
            or not applicable_ids
            or not applicable_ids.issubset(supplied_ids)
            or not draft_ids.issubset(applicable_ids)
        ):
            raise ReviewBlockedError(_BLOCKED_MESSAGE)

    @staticmethod
    def _validate_review(
        review: ResponseReview,
        policy_decision: PolicyDecision,
        draft: DraftResponse,
    ) -> None:
        applicable_ids = set(policy_decision.applicable_policy_ids)
        if not set(review.applied_policy_ids).issubset(applicable_ids):
            raise ReviewOutputError(_INVALID_OUTPUT_MESSAGE)
        if review.final_message is not None and any(
            policy_id in review.final_message for policy_id in applicable_ids
        ):
            raise ReviewOutputError(_INVALID_OUTPUT_MESSAGE)
        if review.verdict is ReviewVerdict.APPROVED and (
            review.final_message != draft.message
            or review.applied_policy_ids != draft.applied_policy_ids
        ):
            raise ReviewOutputError(_INVALID_OUTPUT_MESSAGE)
        if review.verdict is ReviewVerdict.REVISED and review.final_message == draft.message:
            raise ReviewOutputError(_INVALID_OUTPUT_MESSAGE)

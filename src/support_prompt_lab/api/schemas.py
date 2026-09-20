"""Public request and response contracts for ticket analysis."""

from __future__ import annotations

from typing import Protocol, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator

from support_prompt_lab.application.ports import ModelUsage
from support_prompt_lab.application.workflow import SupportWorkflowExecution
from support_prompt_lab.domain import (
    DraftResponse,
    EscalationDecision,
    PolicyDecision,
    ResponseReview,
    SupportPolicy,
    SupportTicket,
    TriageResult,
)
from support_prompt_lab.prompts import PromptStrategy


class AnalyzeTicketRequest(BaseModel):
    """One ticket and the support policies to apply to it."""

    model_config = ConfigDict(extra="forbid")

    ticket: SupportTicket
    policies: tuple[SupportPolicy, ...] = Field(min_length=1, max_length=50)

    @field_validator("policies")
    @classmethod
    def policy_ids_are_unique(
        cls, policies: tuple[SupportPolicy, ...]
    ) -> tuple[SupportPolicy, ...]:
        policy_ids = [policy.policy_id for policy in policies]
        if len(policy_ids) != len(set(policy_ids)):
            raise ValueError("policy identifiers must be unique")
        return policies


class ModelUsageResponse(BaseModel):
    """Provider-reported token consumption exposed by the API."""

    model_config = ConfigDict(frozen=True)

    input_tokens: int
    output_tokens: int

    @classmethod
    def from_usage(cls, usage: ModelUsage) -> Self:
        return cls(
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
        )


class _PromptExecution(Protocol):
    @property
    def prompt_name(self) -> str: ...

    @property
    def prompt_version(self) -> str: ...

    @property
    def strategy(self) -> PromptStrategy: ...

    @property
    def model(self) -> str: ...

    @property
    def usage(self) -> ModelUsage: ...


class PromptExecutionMetadata(BaseModel):
    """Sanitized prompt and model identity for one executed stage."""

    model_config = ConfigDict(frozen=True)

    prompt_name: str
    prompt_version: str
    strategy: PromptStrategy
    model: str
    usage: ModelUsageResponse

    @classmethod
    def from_execution(cls, execution: _PromptExecution) -> Self:
        return cls(
            prompt_name=execution.prompt_name,
            prompt_version=execution.prompt_version,
            strategy=execution.strategy,
            model=execution.model,
            usage=ModelUsageResponse.from_usage(execution.usage),
        )


class TriageStageResponse(BaseModel):
    outcome: TriageResult
    metadata: PromptExecutionMetadata


class PolicyStageResponse(BaseModel):
    outcome: PolicyDecision
    metadata: PromptExecutionMetadata


class DraftStageResponse(BaseModel):
    outcome: DraftResponse
    metadata: PromptExecutionMetadata


class ReviewStageResponse(BaseModel):
    outcome: ResponseReview
    metadata: PromptExecutionMetadata


class AnalyzeTicketResponse(BaseModel):
    """Complete public result for the safely executed workflow path."""

    ticket_id: str
    requires_escalation: bool
    final_message: str | None
    triage: TriageStageResponse
    policy: PolicyStageResponse
    escalation: EscalationDecision
    draft: DraftStageResponse | None
    review: ReviewStageResponse | None

    @classmethod
    def from_execution(
        cls,
        ticket: SupportTicket,
        execution: SupportWorkflowExecution,
    ) -> Self:
        draft = (
            DraftStageResponse(
                outcome=execution.draft.draft,
                metadata=PromptExecutionMetadata.from_execution(execution.draft),
            )
            if execution.draft is not None
            else None
        )
        review = (
            ReviewStageResponse(
                outcome=execution.review.review,
                metadata=PromptExecutionMetadata.from_execution(execution.review),
            )
            if execution.review is not None
            else None
        )
        return cls(
            ticket_id=ticket.ticket_id,
            requires_escalation=execution.requires_escalation,
            final_message=execution.final_message,
            triage=TriageStageResponse(
                outcome=execution.triage.result,
                metadata=PromptExecutionMetadata.from_execution(execution.triage),
            ),
            policy=PolicyStageResponse(
                outcome=execution.policy.decision,
                metadata=PromptExecutionMetadata.from_execution(execution.policy),
            ),
            escalation=execution.escalation,
            draft=draft,
            review=review,
        )

"""Orchestrate the typed support-ticket analysis stages."""

from dataclasses import dataclass

from support_prompt_lab.application.draft import DraftExecution, ResponseDraftStage
from support_prompt_lab.application.escalation import EscalationDecider
from support_prompt_lab.application.policy import PolicyDecisionStage, PolicyExecution
from support_prompt_lab.application.review import ResponseReviewStage, ReviewExecution
from support_prompt_lab.application.triage import TriageExecution, TriageStage
from support_prompt_lab.domain import (
    EscalationDecision,
    ReviewVerdict,
    SupportPolicy,
    SupportTicket,
)
from support_prompt_lab.prompts import PromptStrategy


@dataclass(frozen=True, slots=True)
class SupportWorkflowExecution:
    """Complete workflow result, including each executed stage and its metadata."""

    triage: TriageExecution
    policy: PolicyExecution
    escalation: EscalationDecision
    draft: DraftExecution | None
    review: ReviewExecution | None

    def __post_init__(self) -> None:
        model_stages_skipped = self.draft is None and self.review is None
        model_stages_completed = self.draft is not None and self.review is not None
        if self.escalation.required and not model_stages_skipped:
            raise ValueError("escalated workflows cannot contain draft or review results")
        if not self.escalation.required and not model_stages_completed:
            raise ValueError("non-escalated workflows require draft and review results")

    @property
    def requires_escalation(self) -> bool:
        """Report escalation from either deterministic rules or final review."""

        return self.escalation.required or (
            self.review is not None and self.review.review.verdict is ReviewVerdict.ESCALATE
        )

    @property
    def final_message(self) -> str | None:
        """Return only the reviewer-approved or reviewer-revised customer message."""

        if self.review is None:
            return None
        return self.review.review.final_message


class SupportWorkflow:
    """Run support analysis in order and stop before unsafe downstream stages."""

    def __init__(
        self,
        triage_stage: TriageStage,
        policy_stage: PolicyDecisionStage,
        escalation_decider: EscalationDecider,
        draft_stage: ResponseDraftStage,
        review_stage: ResponseReviewStage,
    ) -> None:
        self._triage_stage = triage_stage
        self._policy_stage = policy_stage
        self._escalation_decider = escalation_decider
        self._draft_stage = draft_stage
        self._review_stage = review_stage

    async def analyze(
        self,
        ticket: SupportTicket,
        policies: tuple[SupportPolicy, ...],
        *,
        triage_version: str | None = None,
        triage_strategy: PromptStrategy | str | None = None,
    ) -> SupportWorkflowExecution:
        """Analyze one ticket and return the safely completed workflow path."""

        triage = await self._triage_stage.classify(
            ticket,
            version=triage_version,
            strategy=triage_strategy,
        )
        policy = await self._policy_stage.decide(ticket, triage.result, policies)
        escalation = self._escalation_decider.decide(
            triage.result,
            policy.decision,
            policies,
        )
        if escalation.required:
            return SupportWorkflowExecution(
                triage=triage,
                policy=policy,
                escalation=escalation,
                draft=None,
                review=None,
            )

        draft = await self._draft_stage.draft(
            ticket,
            triage.result,
            policy.decision,
            escalation,
            policies,
        )
        review = await self._review_stage.review(
            ticket,
            triage.result,
            policy.decision,
            policies,
            draft.draft,
        )
        return SupportWorkflowExecution(
            triage=triage,
            policy=policy,
            escalation=escalation,
            draft=draft,
            review=review,
        )

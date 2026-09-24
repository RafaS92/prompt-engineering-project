"""Orchestrate the typed support-ticket analysis stages."""

from dataclasses import dataclass

from support_prompt_lab.application.draft import DraftExecution, ResponseDraftStage
from support_prompt_lab.application.escalation import EscalationDecider
from support_prompt_lab.application.injection import (
    InjectionDetectionExecution,
    InjectionDetectionStage,
)
from support_prompt_lab.application.policy_consensus import (
    PolicyConsensusExecution,
    PolicyConsensusStage,
)
from support_prompt_lab.application.review import ResponseReviewStage, ReviewExecution
from support_prompt_lab.application.triage import TriageExecution, TriageStage
from support_prompt_lab.domain import (
    EscalationDecision,
    EscalationReason,
    ReviewVerdict,
    SupportPolicy,
    SupportTicket,
)
from support_prompt_lab.prompts import PromptStrategy

_SAFE_REFUSAL_MESSAGE = (
    "We cannot process this request automatically. A support specialist will review it."
)


@dataclass(frozen=True, slots=True)
class SupportWorkflowExecution:
    """Complete workflow result, including each executed stage and its metadata."""

    injection_detection: InjectionDetectionExecution
    triage: TriageExecution | None
    policy: PolicyConsensusExecution | None
    escalation: EscalationDecision
    draft: DraftExecution | None
    review: ReviewExecution | None

    def __post_init__(self) -> None:
        if self.injection_detection.result.detected:
            if any(
                stage is not None for stage in (self.triage, self.policy, self.draft, self.review)
            ):
                raise ValueError("detected injection must skip all downstream model stages")
            if not self.escalation.required:
                raise ValueError("detected injection requires human escalation")
            if self.escalation.reasons != (EscalationReason.PROMPT_INJECTION,):
                raise ValueError("detected injection requires the prompt-injection reason")
            return

        if self.triage is None or self.policy is None:
            raise ValueError("safe input requires triage and policy results")
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
        """Return the safe refusal or the reviewer-approved customer message."""

        if self.injection_detection.result.detected:
            return _SAFE_REFUSAL_MESSAGE
        if self.review is None:
            return None
        return self.review.review.final_message


class SupportWorkflow:
    """Run support analysis in order and stop before unsafe downstream stages."""

    def __init__(
        self,
        injection_detection_stage: InjectionDetectionStage,
        triage_stage: TriageStage,
        policy_stage: PolicyConsensusStage,
        escalation_decider: EscalationDecider,
        draft_stage: ResponseDraftStage,
        review_stage: ResponseReviewStage,
        default_triage_strategy: PromptStrategy,
    ) -> None:
        self._injection_detection_stage = injection_detection_stage
        self._triage_stage = triage_stage
        self._policy_stage = policy_stage
        self._escalation_decider = escalation_decider
        self._draft_stage = draft_stage
        self._review_stage = review_stage
        self._default_triage_strategy = default_triage_strategy

    async def analyze(
        self,
        ticket: SupportTicket,
        policies: tuple[SupportPolicy, ...],
        *,
        triage_version: str | None = None,
        triage_strategy: PromptStrategy | str | None = None,
    ) -> SupportWorkflowExecution:
        """Analyze one ticket and return the safely completed workflow path."""

        selected_strategy = triage_strategy
        if triage_version is None and selected_strategy is None:
            selected_strategy = self._default_triage_strategy
        self._triage_stage.validate_selection(
            version=triage_version,
            strategy=selected_strategy,
        )

        injection_detection = await self._injection_detection_stage.inspect(ticket, policies)
        if injection_detection.result.detected:
            return SupportWorkflowExecution(
                injection_detection=injection_detection,
                triage=None,
                policy=None,
                escalation=self._escalation_decider.for_injection(injection_detection.result),
                draft=None,
                review=None,
            )

        triage = await self._triage_stage.classify(
            ticket,
            version=triage_version,
            strategy=selected_strategy,
        )
        policy = await self._policy_stage.decide(ticket, triage.result, policies)
        escalation = self._escalation_decider.decide(
            triage.result,
            policy.decision,
            policies,
        )
        if escalation.required:
            return SupportWorkflowExecution(
                injection_detection=injection_detection,
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
            injection_detection=injection_detection,
            triage=triage,
            policy=policy,
            escalation=escalation,
            draft=draft,
            review=review,
        )

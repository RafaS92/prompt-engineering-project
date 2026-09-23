from pathlib import Path

import pytest

from support_prompt_lab.application.draft import (
    ResponseDraftPromptBuilder,
    ResponseDraftStage,
)
from support_prompt_lab.application.errors import TriageOutputError
from support_prompt_lab.application.escalation import EscalationDecider
from support_prompt_lab.application.policy import PolicyDecisionStage, PolicyPromptBuilder
from support_prompt_lab.application.policy_consensus import PolicyConsensusStage
from support_prompt_lab.application.policy_voting import PolicyDecisionVoter
from support_prompt_lab.application.ports import ModelResponse, ModelUsage
from support_prompt_lab.application.review import (
    ResponseReviewPromptBuilder,
    ResponseReviewStage,
)
from support_prompt_lab.application.triage import TriagePromptBuilder, TriageStage
from support_prompt_lab.application.workflow import (
    SupportWorkflow,
    SupportWorkflowExecution,
)
from support_prompt_lab.domain import (
    EscalationDecision,
    EscalationReason,
    PolicyAgreement,
    PolicyDisagreement,
    PolicyOutcome,
    PolicyTie,
    ReviewVerdict,
    SupportPolicy,
    SupportTicket,
)
from support_prompt_lab.prompts import PromptRegistry, PromptStrategy
from tests.fakes import FakeLLMClient

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PROMPT_ROOT = PROJECT_ROOT / "prompts"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def support_ticket() -> SupportTicket:
    return SupportTicket(
        ticket_id="ticket-4001",
        subject="Refund request",
        message="Please refund my order.",
        order_id="order-9001",
    )


def support_policies() -> tuple[SupportPolicy, ...]:
    return (
        SupportPolicy(
            policy_id="returns-30-day",
            title="Standard returns",
            text="Returns are allowed within 30 days.",
        ),
    )


def model_response(text: str) -> ModelResponse:
    return ModelResponse(
        text=text,
        model="gpt-test-2026-09-20",
        usage=ModelUsage(input_tokens=100, output_tokens=20),
    )


def triage_response() -> ModelResponse:
    return model_response(
        '{"intent":"refund","urgency":"low","sentiment":"neutral",'
        '"rationale":"The customer requests a refund."}'
    )


def allowed_policy_response() -> ModelResponse:
    return model_response(
        '{"decision":"allow","applicable_policy_ids":["returns-30-day"],'
        '"missing_information":[],"rationale":"The return is allowed."}'
    )


def draft_response() -> ModelResponse:
    return model_response(
        '{"message":"We can process your return within the 30-day window.",'
        '"applied_policy_ids":["returns-30-day"]}'
    )


def approved_review_response() -> ModelResponse:
    return model_response(
        '{"verdict":"approved","final_message":"We can process your return '
        'within the 30-day window.","issues":[],'
        '"applied_policy_ids":["returns-30-day"],'
        '"rationale":"The response is compliant and clear."}'
    )


def support_workflow(
    client: FakeLLMClient,
    default_triage_strategy: PromptStrategy = PromptStrategy.ZERO_SHOT,
    policy_sample_count: int = 1,
) -> SupportWorkflow:
    registry = PromptRegistry(PROMPT_ROOT)
    model = "gpt-test"
    return SupportWorkflow(
        triage_stage=TriageStage(TriagePromptBuilder(registry), client, model),
        policy_stage=PolicyConsensusStage(
            policy_stage=PolicyDecisionStage(PolicyPromptBuilder(registry), client, model),
            voter=PolicyDecisionVoter(),
            sample_count=policy_sample_count,
        ),
        escalation_decider=EscalationDecider(),
        draft_stage=ResponseDraftStage(ResponseDraftPromptBuilder(registry), client, model),
        review_stage=ResponseReviewStage(ResponseReviewPromptBuilder(registry), client, model),
        default_triage_strategy=default_triage_strategy,
    )


@pytest.mark.anyio
async def test_workflow_runs_all_stages_and_returns_approved_message() -> None:
    client = FakeLLMClient(
        [
            triage_response(),
            allowed_policy_response(),
            draft_response(),
            approved_review_response(),
        ]
    )

    execution = await support_workflow(client).analyze(support_ticket(), support_policies())

    assert execution.requires_escalation is False
    assert execution.final_message == ("We can process your return within the 30-day window.")
    assert execution.draft is not None
    assert execution.review is not None
    assert execution.review.review.verdict is ReviewVerdict.APPROVED
    assert execution.triage.prompt_version == "1.6.0"
    assert execution.policy.prompt_version == "1.1.0"
    assert isinstance(execution.policy.consensus, PolicyAgreement)
    assert execution.policy.usage == ModelUsage(input_tokens=100, output_tokens=20)
    assert execution.draft.prompt_version == "1.0.0"
    assert execution.review.prompt_version == "1.0.0"
    assert len(client.requests) == 4


@pytest.mark.anyio
async def test_workflow_continues_with_strict_majority_policy_decision() -> None:
    client = FakeLLMClient(
        [
            triage_response(),
            model_response(
                '{"decision":"deny","applicable_policy_ids":["returns-30-day"],'
                '"missing_information":[],"rationale":"The return is denied."}'
            ),
            allowed_policy_response(),
            model_response(
                '{"decision":"allow","applicable_policy_ids":["returns-30-day"],'
                '"missing_information":[],"rationale":"The request is eligible."}'
            ),
            draft_response(),
            approved_review_response(),
        ]
    )

    execution = await support_workflow(client, policy_sample_count=3).analyze(
        support_ticket(),
        support_policies(),
    )

    assert isinstance(execution.policy.consensus, PolicyDisagreement)
    assert execution.policy.decision.decision is PolicyOutcome.ALLOW
    assert execution.policy.usage == ModelUsage(input_tokens=300, output_tokens=60)
    assert execution.requires_escalation is False
    assert execution.draft is not None
    assert execution.review is not None
    assert len(client.requests) == 6


@pytest.mark.anyio
async def test_workflow_escalates_policy_consensus_tie_before_drafting() -> None:
    client = FakeLLMClient(
        [
            triage_response(),
            allowed_policy_response(),
            model_response(
                '{"decision":"deny","applicable_policy_ids":["returns-30-day"],'
                '"missing_information":[],"rationale":"The return is denied."}'
            ),
            model_response(
                '{"decision":"escalate","applicable_policy_ids":[],'
                '"missing_information":["Purchase date"],'
                '"rationale":"Eligibility cannot be determined."}'
            ),
        ]
    )

    execution = await support_workflow(client, policy_sample_count=3).analyze(
        support_ticket(),
        support_policies(),
    )

    assert isinstance(execution.policy.consensus, PolicyTie)
    assert execution.policy.selected_decision is None
    assert execution.policy.decision.decision is PolicyOutcome.ESCALATE
    assert execution.policy.decision.applicable_policy_ids == ("returns-30-day",)
    assert execution.policy.usage == ModelUsage(input_tokens=300, output_tokens=60)
    assert execution.requires_escalation is True
    assert EscalationReason.POLICY_ESCALATION in execution.escalation.reasons
    assert execution.draft is None
    assert execution.review is None
    assert len(client.requests) == 4


@pytest.mark.anyio
async def test_workflow_uses_injected_default_instead_of_latest_prompt() -> None:
    client = FakeLLMClient(
        [
            triage_response(),
            allowed_policy_response(),
            draft_response(),
            approved_review_response(),
        ]
    )

    execution = await support_workflow(
        client,
        default_triage_strategy=PromptStrategy.MANY_SHOT,
    ).analyze(support_ticket(), support_policies())

    assert execution.triage.strategy is PromptStrategy.MANY_SHOT
    assert execution.triage.prompt_version == "1.5.0"


@pytest.mark.parametrize(
    ("selection", "expected_strategy", "expected_version"),
    [
        ({"triage_strategy": "zero_shot"}, PromptStrategy.ZERO_SHOT, "1.6.0"),
        ({"triage_strategy": "few_shot"}, PromptStrategy.FEW_SHOT, "1.4.0"),
        ({"triage_version": "1.2.0"}, PromptStrategy.MANY_SHOT, "1.2.0"),
    ],
)
@pytest.mark.anyio
async def test_workflow_selects_requested_triage_prompt(
    selection: dict[str, str],
    expected_strategy: PromptStrategy,
    expected_version: str,
) -> None:
    client = FakeLLMClient(
        [
            triage_response(),
            allowed_policy_response(),
            draft_response(),
            approved_review_response(),
        ]
    )

    execution = await support_workflow(client).analyze(
        support_ticket(),
        support_policies(),
        **selection,
    )

    assert execution.triage.strategy is expected_strategy
    assert execution.triage.prompt_version == expected_version


@pytest.mark.anyio
async def test_workflow_returns_reviewer_revision_as_final_message() -> None:
    client = FakeLLMClient(
        [
            triage_response(),
            allowed_policy_response(),
            draft_response(),
            model_response(
                '{"verdict":"revised","final_message":"We are happy to help '
                'with your eligible return.","issues":["tone_issue"],'
                '"applied_policy_ids":["returns-30-day"],'
                '"rationale":"The response needed a warmer tone."}'
            ),
        ]
    )

    execution = await support_workflow(client).analyze(support_ticket(), support_policies())

    assert execution.requires_escalation is False
    assert execution.final_message == "We are happy to help with your eligible return."
    assert execution.review is not None
    assert execution.review.review.verdict is ReviewVerdict.REVISED


@pytest.mark.anyio
async def test_workflow_stops_before_drafting_when_escalation_is_required() -> None:
    client = FakeLLMClient(
        [
            triage_response(),
            model_response(
                '{"decision":"escalate","applicable_policy_ids":[],'
                '"missing_information":["purchase date"],'
                '"rationale":"Eligibility cannot be established."}'
            ),
        ]
    )

    execution = await support_workflow(client).analyze(support_ticket(), support_policies())

    assert execution.requires_escalation is True
    assert execution.final_message is None
    assert execution.escalation.required is True
    assert execution.draft is None
    assert execution.review is None
    assert len(client.requests) == 2


@pytest.mark.anyio
async def test_workflow_surfaces_escalation_from_final_review() -> None:
    client = FakeLLMClient(
        [
            triage_response(),
            allowed_policy_response(),
            draft_response(),
            model_response(
                '{"verdict":"escalate","final_message":null,'
                '"issues":["unsupported_promise"],"applied_policy_ids":[],'
                '"rationale":"A safe response cannot be established."}'
            ),
        ]
    )

    execution = await support_workflow(client).analyze(support_ticket(), support_policies())

    assert execution.escalation.required is False
    assert execution.requires_escalation is True
    assert execution.final_message is None
    assert execution.review is not None
    assert execution.review.review.verdict is ReviewVerdict.ESCALATE
    assert len(client.requests) == 4


@pytest.mark.anyio
async def test_workflow_stops_after_invalid_stage_output() -> None:
    client = FakeLLMClient([model_response("not json")])

    with pytest.raises(TriageOutputError):
        await support_workflow(client).analyze(support_ticket(), support_policies())

    assert len(client.requests) == 1


@pytest.mark.parametrize(
    ("escalation", "has_draft", "has_review"),
    [
        (
            EscalationDecision(
                required=True,
                reasons=(EscalationReason.POLICY_ESCALATION,),
                explanation="Human review is required.",
            ),
            True,
            True,
        ),
        (
            EscalationDecision(
                required=False,
                reasons=(),
                explanation="No human escalation is required.",
            ),
            False,
            False,
        ),
    ],
    ids=["escalated-with-results", "non-escalated-without-results"],
)
@pytest.mark.anyio
async def test_workflow_execution_rejects_inconsistent_stage_paths(
    escalation: EscalationDecision,
    has_draft: bool,
    has_review: bool,
) -> None:
    completed = await support_workflow(
        FakeLLMClient(
            [
                triage_response(),
                allowed_policy_response(),
                draft_response(),
                approved_review_response(),
            ]
        )
    ).analyze(support_ticket(), support_policies())

    with pytest.raises(ValueError):
        SupportWorkflowExecution(
            triage=completed.triage,
            policy=completed.policy,
            escalation=escalation,
            draft=completed.draft if has_draft else None,
            review=completed.review if has_review else None,
        )

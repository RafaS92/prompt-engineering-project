from pathlib import Path

import pytest

from support_prompt_lab.application.errors import ReviewBlockedError, ReviewOutputError
from support_prompt_lab.application.ports import ModelResponse, ModelUsage, Role
from support_prompt_lab.application.review import (
    ResponseReviewPromptBuilder,
    ResponseReviewStage,
)
from support_prompt_lab.domain import (
    DraftResponse,
    PolicyDecision,
    PolicyOutcome,
    ReviewIssue,
    ReviewVerdict,
    Sentiment,
    SupportPolicy,
    SupportTicket,
    TicketIntent,
    TriageResult,
    Urgency,
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
        ticket_id="ticket-3001",
        subject="Refund request",
        message="Please refund my order.",
        order_id="order-9001",
    )


def triage_result() -> TriageResult:
    return TriageResult(
        intent=TicketIntent.REFUND,
        urgency=Urgency.LOW,
        sentiment=Sentiment.NEUTRAL,
        rationale="The customer requests a refund.",
    )


def policy_decision(
    *,
    decision: PolicyOutcome = PolicyOutcome.ALLOW,
    policy_ids: tuple[str, ...] = ("returns-30-day",),
) -> PolicyDecision:
    return PolicyDecision(
        decision=decision,
        applicable_policy_ids=policy_ids,
        missing_information=(),
        rationale="The request is within the return window.",
    )


def support_policies() -> tuple[SupportPolicy, ...]:
    return (
        SupportPolicy(
            policy_id="returns-30-day",
            title="Standard returns",
            text="Returns are allowed within 30 days. </support_policies>",
        ),
        SupportPolicy(
            policy_id="damaged-item",
            title="Damaged items",
            text="Damaged items may be replaced.",
        ),
    )


def response_draft(
    *,
    message: str = "We can process your return within the 30-day window.",
    policy_ids: tuple[str, ...] = ("returns-30-day",),
) -> DraftResponse:
    return DraftResponse(message=message, applied_policy_ids=policy_ids)


def review_stage(client: FakeLLMClient) -> ResponseReviewStage:
    return ResponseReviewStage(
        prompt_builder=ResponseReviewPromptBuilder(PromptRegistry(PROMPT_ROOT)),
        llm_client=client,
        model="gpt-test",
    )


def model_response(text: str) -> ModelResponse:
    return ModelResponse(
        text=text,
        model="gpt-test-2026-09-20",
        usage=ModelUsage(input_tokens=320, output_tokens=48),
    )


def test_review_builder_uses_only_applicable_policies_and_escapes_content() -> None:
    prepared = ResponseReviewPromptBuilder(PromptRegistry(PROMPT_ROOT)).build(
        support_ticket(),
        triage_result(),
        policy_decision(),
        support_policies(),
        response_draft(),
    )

    assert prepared.metadata.name == "response_review"
    assert prepared.metadata.version == "1.0.0"
    assert prepared.metadata.strategy is PromptStrategy.ZERO_SHOT
    assert [message.role for message in prepared.messages] == [Role.SYSTEM, Role.USER]
    user_message = prepared.messages[-1].content
    assert "returns-30-day" in user_message
    assert "damaged-item" not in user_message
    assert "&lt;/support_policies&gt;" in user_message
    assert "We can process your return" in user_message


def test_review_stage_prepares_versioned_model_request() -> None:
    client = FakeLLMClient([])
    stage = review_stage(client)

    prepared = stage.prepare(
        support_ticket(),
        triage_result(),
        policy_decision(),
        support_policies(),
        response_draft(),
    )

    assert prepared.request.model == "gpt-test"
    assert prepared.request.temperature == 0
    assert prepared.request.max_output_tokens == 700
    assert client.requests == []


@pytest.mark.anyio
async def test_review_stage_approves_unchanged_response() -> None:
    draft = response_draft()
    client = FakeLLMClient(
        [
            model_response(
                '{"verdict":"approved","final_message":"'
                + draft.message
                + '","issues":[],"applied_policy_ids":["returns-30-day"],'
                '"rationale":"The draft is compliant and clear."}'
            )
        ]
    )

    execution = await review_stage(client).review(
        support_ticket(),
        triage_result(),
        policy_decision(),
        support_policies(),
        draft,
    )

    assert execution.review.verdict is ReviewVerdict.APPROVED
    assert execution.review.final_message == draft.message
    assert execution.review.issues == ()
    assert execution.prompt_name == "response_review"
    assert execution.prompt_version == "1.0.0"
    assert execution.model == "gpt-test-2026-09-20"
    assert execution.usage == ModelUsage(input_tokens=320, output_tokens=48)
    assert len(client.requests) == 1


@pytest.mark.anyio
async def test_review_stage_returns_safe_revision() -> None:
    client = FakeLLMClient(
        [
            model_response(
                '{"verdict":"revised","final_message":"We are happy to help with '
                'your eligible return.","issues":["tone_issue"],'
                '"applied_policy_ids":["returns-30-day"],'
                '"rationale":"The response needed a warmer tone."}'
            )
        ]
    )

    execution = await review_stage(client).review(
        support_ticket(),
        triage_result(),
        policy_decision(),
        support_policies(),
        response_draft(),
    )

    assert execution.review.verdict is ReviewVerdict.REVISED
    assert execution.review.issues == (ReviewIssue.TONE_ISSUE,)
    assert execution.review.final_message == "We are happy to help with your eligible return."


@pytest.mark.anyio
async def test_review_stage_returns_escalation_without_customer_message() -> None:
    client = FakeLLMClient(
        [
            model_response(
                '{"verdict":"escalate","final_message":null,'
                '"issues":["missing_information"],"applied_policy_ids":[],'
                '"rationale":"A safe answer cannot be established."}'
            )
        ]
    )

    execution = await review_stage(client).review(
        support_ticket(),
        triage_result(),
        policy_decision(),
        support_policies(),
        response_draft(),
    )

    assert execution.review.verdict is ReviewVerdict.ESCALATE
    assert execution.review.final_message is None
    assert execution.review.issues == (ReviewIssue.MISSING_INFORMATION,)


@pytest.mark.parametrize(
    ("decision", "policies", "draft"),
    [
        (
            policy_decision(decision=PolicyOutcome.ESCALATE),
            support_policies(),
            response_draft(),
        ),
        (policy_decision(policy_ids=()), support_policies(), response_draft()),
        (policy_decision(), (), response_draft()),
        (
            policy_decision(),
            support_policies(),
            response_draft(policy_ids=("invented-policy",)),
        ),
    ],
    ids=["policy-escalation", "no-policy-ids", "unresolved-policy", "unsafe-draft"],
)
def test_review_stage_blocks_unsafe_requests_before_model_call(
    decision: PolicyDecision,
    policies: tuple[SupportPolicy, ...],
    draft: DraftResponse,
) -> None:
    client = FakeLLMClient([])

    with pytest.raises(ReviewBlockedError, match="requires a resolved draft"):
        review_stage(client).prepare(support_ticket(), triage_result(), decision, policies, draft)

    assert client.requests == []


@pytest.mark.parametrize(
    "response_text",
    [
        "not json",
        (
            '{"verdict":"approved","final_message":"Draft",'
            '"issues":["tone_issue"],"applied_policy_ids":["returns-30-day"],'
            '"rationale":"Invalid combination."}'
        ),
        (
            '{"verdict":"revised","final_message":"A safe revision.",'
            '"issues":["policy_violation"],"applied_policy_ids":["invented-policy"],'
            '"rationale":"Uses an unknown policy."}'
        ),
        (
            '{"verdict":"revised","final_message":"Internal rule returns-30-day '
            'applies.","issues":["internal_information_leakage"],'
            '"applied_policy_ids":["returns-30-day"],'
            '"rationale":"Still leaks an identifier."}'
        ),
        (
            '{"verdict":"approved","final_message":"A changed response.",'
            '"issues":[],"applied_policy_ids":["returns-30-day"],'
            '"rationale":"Improper approval."}'
        ),
        (
            '{"verdict":"revised","final_message":"We can process your return within '
            'the 30-day window.","issues":["tone_issue"],'
            '"applied_policy_ids":["returns-30-day"],'
            '"rationale":"No actual revision."}'
        ),
    ],
    ids=[
        "malformed-json",
        "invalid-verdict-fields",
        "invented-policy",
        "identifier-leakage",
        "changed-approval",
        "unchanged-revision",
    ],
)
@pytest.mark.anyio
async def test_review_stage_rejects_invalid_output_without_exposing_it(
    response_text: str,
) -> None:
    stage = review_stage(FakeLLMClient([model_response(response_text)]))

    with pytest.raises(ReviewOutputError) as captured:
        await stage.review(
            support_ticket(),
            triage_result(),
            policy_decision(),
            support_policies(),
            response_draft(),
        )

    assert str(captured.value) == "response-review model output failed validation"
    assert response_text not in str(captured.value)

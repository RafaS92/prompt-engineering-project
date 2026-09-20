from pathlib import Path

import pytest

from support_prompt_lab.application.draft import ResponseDraftPromptBuilder, ResponseDraftStage
from support_prompt_lab.application.errors import DraftingBlockedError, DraftOutputError
from support_prompt_lab.application.ports import ModelResponse, ModelUsage, Role
from support_prompt_lab.domain import (
    EscalationDecision,
    EscalationReason,
    PolicyDecision,
    PolicyOutcome,
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


def no_escalation() -> EscalationDecision:
    return EscalationDecision(
        required=False,
        reasons=(),
        explanation="No human escalation is required.",
    )


def test_draft_builder_uses_only_applicable_policies() -> None:
    prepared = ResponseDraftPromptBuilder(PromptRegistry(PROMPT_ROOT)).build(
        support_ticket(),
        triage_result(),
        policy_decision(),
        support_policies(),
    )

    assert prepared.metadata.name == "response_draft"
    assert prepared.metadata.version == "1.0.0"
    assert prepared.metadata.strategy is PromptStrategy.ZERO_SHOT
    assert [message.role for message in prepared.messages] == [Role.SYSTEM, Role.USER]
    assert "returns-30-day" in prepared.messages[-1].content
    assert "damaged-item" not in prepared.messages[-1].content
    assert "&lt;/support_policies&gt;" in prepared.messages[-1].content


def test_draft_stage_prepares_versioned_model_request() -> None:
    client = FakeLLMClient([])
    stage = ResponseDraftStage(
        prompt_builder=ResponseDraftPromptBuilder(PromptRegistry(PROMPT_ROOT)),
        llm_client=client,
        model="gpt-test",
    )

    prepared = stage.prepare(
        support_ticket(),
        triage_result(),
        policy_decision(),
        no_escalation(),
        support_policies(),
    )

    assert prepared.request.model == "gpt-test"
    assert prepared.request.temperature == 0.2
    assert prepared.request.max_output_tokens == 600
    assert client.requests == []


@pytest.mark.anyio
async def test_draft_stage_returns_validated_response_and_metadata() -> None:
    response = ModelResponse(
        text=(
            '{"message":"We can process your return within the 30-day window.",'
            '"applied_policy_ids":["returns-30-day"]}'
        ),
        model="gpt-test-2026-09-20",
        usage=ModelUsage(input_tokens=210, output_tokens=32),
    )
    client = FakeLLMClient([response])
    stage = ResponseDraftStage(
        prompt_builder=ResponseDraftPromptBuilder(PromptRegistry(PROMPT_ROOT)),
        llm_client=client,
        model="gpt-test",
    )

    execution = await stage.draft(
        support_ticket(),
        triage_result(),
        policy_decision(),
        no_escalation(),
        support_policies(),
    )

    assert execution.draft.message == "We can process your return within the 30-day window."
    assert execution.draft.applied_policy_ids == ("returns-30-day",)
    assert execution.prompt_name == "response_draft"
    assert execution.prompt_version == "1.0.0"
    assert execution.model == "gpt-test-2026-09-20"
    assert execution.usage == ModelUsage(input_tokens=210, output_tokens=32)
    assert len(client.requests) == 1


def blocked_escalation() -> EscalationDecision:
    return EscalationDecision(
        required=True,
        reasons=(EscalationReason.POLICY_ESCALATION,),
        explanation="Human review is required.",
    )


@pytest.mark.parametrize(
    ("decision", "escalation", "policies"),
    [
        (policy_decision(), blocked_escalation(), support_policies()),
        (
            policy_decision(decision=PolicyOutcome.ESCALATE, policy_ids=()),
            no_escalation(),
            support_policies(),
        ),
        (policy_decision(policy_ids=()), no_escalation(), support_policies()),
        (policy_decision(), no_escalation(), ()),
    ],
    ids=["escalation-required", "policy-escalation", "no-policy-ids", "unresolved-policy"],
)
def test_draft_stage_blocks_unsafe_requests_before_model_call(
    decision: PolicyDecision,
    escalation: EscalationDecision,
    policies: tuple[SupportPolicy, ...],
) -> None:
    client = FakeLLMClient([])
    stage = ResponseDraftStage(
        prompt_builder=ResponseDraftPromptBuilder(PromptRegistry(PROMPT_ROOT)),
        llm_client=client,
        model="gpt-test",
    )

    with pytest.raises(DraftingBlockedError, match="requires human review"):
        stage.prepare(support_ticket(), triage_result(), decision, escalation, policies)

    assert client.requests == []


@pytest.mark.parametrize(
    "response_text",
    [
        "not json",
        '{"message":"Missing IDs"}',
        '{"message":"Draft","applied_policy_ids":["invented-policy"]}',
        (
            '{"message":"Internal rule returns-30-day applies.",'
            '"applied_policy_ids":["returns-30-day"]}'
        ),
    ],
    ids=["malformed-json", "missing-field", "invented-policy", "identifier-leakage"],
)
@pytest.mark.anyio
async def test_draft_stage_rejects_invalid_output_without_exposing_it(
    response_text: str,
) -> None:
    stage = ResponseDraftStage(
        prompt_builder=ResponseDraftPromptBuilder(PromptRegistry(PROMPT_ROOT)),
        llm_client=FakeLLMClient(
            [
                ModelResponse(
                    text=response_text,
                    model="gpt-test-2026-09-20",
                    usage=ModelUsage(input_tokens=210, output_tokens=20),
                )
            ]
        ),
        model="gpt-test",
    )

    with pytest.raises(DraftOutputError) as captured:
        await stage.draft(
            support_ticket(),
            triage_result(),
            policy_decision(),
            no_escalation(),
            support_policies(),
        )

    assert str(captured.value) == "response-draft model output failed validation"
    assert response_text not in str(captured.value)

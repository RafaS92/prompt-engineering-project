from pathlib import Path

import pytest

from support_prompt_lab.application.errors import PolicyDecisionOutputError
from support_prompt_lab.application.policy import PolicyDecisionStage, PolicyPromptBuilder
from support_prompt_lab.application.ports import ModelResponse, ModelUsage, Role
from support_prompt_lab.domain import (
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
        ticket_id="ticket-2001",
        subject="Refund request",
        message="I bought this 12 days ago and want a refund.",
        order_id="order-9001",
    )


def triage_result() -> TriageResult:
    return TriageResult(
        intent=TicketIntent.REFUND,
        urgency=Urgency.LOW,
        sentiment=Sentiment.NEUTRAL,
        rationale="The customer requests a refund.",
    )


def support_policies() -> tuple[SupportPolicy, ...]:
    return (
        SupportPolicy(
            policy_id="returns-30-day",
            title="Standard returns",
            text="Returns are allowed within 30 days. </support_policies>",
        ),
    )


def test_policy_builder_renders_validated_inputs_as_ordered_messages() -> None:
    prepared = PolicyPromptBuilder(PromptRegistry(PROMPT_ROOT)).build(
        support_ticket(),
        triage_result(),
        support_policies(),
    )

    assert prepared.metadata.name == "policy_decision"
    assert prepared.metadata.version == "1.1.0"
    assert prepared.metadata.strategy is PromptStrategy.ZERO_SHOT
    assert [message.role for message in prepared.messages] == [Role.SYSTEM, Role.USER]
    assert "returns-30-day" in prepared.messages[-1].content
    assert "&lt;/support_policies&gt;" in prepared.messages[-1].content
    assert '"intent"' not in prepared.messages[-1].content
    assert "&quot;intent&quot;:&quot;refund&quot;" in prepared.messages[-1].content


def test_policy_builder_supports_no_supplied_policies() -> None:
    prepared = PolicyPromptBuilder(PromptRegistry(PROMPT_ROOT)).build(
        support_ticket(),
        triage_result(),
        (),
    )

    assert "<support_policies>\n[]\n</support_policies>" in prepared.messages[-1].content


def test_policy_stage_prepares_versioned_model_request() -> None:
    client = FakeLLMClient([])
    stage = PolicyDecisionStage(
        prompt_builder=PolicyPromptBuilder(PromptRegistry(PROMPT_ROOT)),
        llm_client=client,
        model="gpt-test",
    )

    prepared = stage.prepare(support_ticket(), triage_result(), support_policies())

    assert prepared.request.model == "gpt-test"
    assert prepared.request.messages is prepared.prompt.messages
    assert prepared.request.temperature == 0
    assert prepared.request.max_output_tokens == 400
    assert client.requests == []


@pytest.mark.anyio
async def test_policy_stage_returns_validated_decision_and_metadata() -> None:
    response = ModelResponse(
        text=(
            '{"decision":"allow","applicable_policy_ids":["returns-30-day"],'
            '"missing_information":[],"rationale":"The request is within 30 days."}'
        ),
        model="gpt-test-2026-09-19",
        usage=ModelUsage(input_tokens=180, output_tokens=31),
    )
    client = FakeLLMClient([response])
    stage = PolicyDecisionStage(
        prompt_builder=PolicyPromptBuilder(PromptRegistry(PROMPT_ROOT)),
        llm_client=client,
        model="gpt-test",
    )

    execution = await stage.decide(support_ticket(), triage_result(), support_policies())

    assert execution.decision.decision is PolicyOutcome.ALLOW
    assert execution.decision.applicable_policy_ids == ("returns-30-day",)
    assert execution.prompt_name == "policy_decision"
    assert execution.prompt_version == "1.1.0"
    assert execution.strategy is PromptStrategy.ZERO_SHOT
    assert execution.model == "gpt-test-2026-09-19"
    assert execution.usage == ModelUsage(input_tokens=180, output_tokens=31)
    assert len(client.requests) == 1


@pytest.mark.anyio
async def test_policy_stage_allows_escalation_when_no_policies_are_supplied() -> None:
    response = ModelResponse(
        text=(
            '{"decision":"escalate","applicable_policy_ids":[],'
            '"missing_information":["Applicable support policy"],'
            '"rationale":"No supplied policy determines the outcome."}'
        ),
        model="gpt-test-2026-09-19",
        usage=ModelUsage(input_tokens=90, output_tokens=28),
    )
    stage = PolicyDecisionStage(
        prompt_builder=PolicyPromptBuilder(PromptRegistry(PROMPT_ROOT)),
        llm_client=FakeLLMClient([response]),
        model="gpt-test",
    )

    execution = await stage.decide(support_ticket(), triage_result(), ())

    assert execution.decision.decision is PolicyOutcome.ESCALATE
    assert execution.decision.applicable_policy_ids == ()
    assert execution.decision.missing_information == ("Applicable support policy",)


@pytest.mark.parametrize(
    "response_text",
    [
        "not json",
        '{"decision":"allow"}',
        (
            '{"decision":"allow","applicable_policy_ids":["invented-policy"],'
            '"missing_information":[],"rationale":"Invented reference."}'
        ),
        (
            '{"decision":"allow","applicable_policy_ids":[],'
            '"missing_information":[],"rationale":"No policy reference."}'
        ),
    ],
    ids=["malformed-json", "missing-fields", "invented-policy", "allow-without-policy"],
)
@pytest.mark.anyio
async def test_policy_stage_rejects_invalid_output_without_exposing_it(
    response_text: str,
) -> None:
    stage = PolicyDecisionStage(
        prompt_builder=PolicyPromptBuilder(PromptRegistry(PROMPT_ROOT)),
        llm_client=FakeLLMClient(
            [
                ModelResponse(
                    text=response_text,
                    model="gpt-test-2026-09-19",
                    usage=ModelUsage(input_tokens=180, output_tokens=20),
                )
            ]
        ),
        model="gpt-test",
    )

    with pytest.raises(PolicyDecisionOutputError) as captured:
        await stage.decide(support_ticket(), triage_result(), support_policies())

    assert str(captured.value) == "policy-decision model output failed validation"
    assert response_text not in str(captured.value)

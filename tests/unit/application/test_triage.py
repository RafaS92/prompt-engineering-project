import json
from pathlib import Path

import pytest

from support_prompt_lab.application.ports import ModelResponse, ModelUsage, Role
from support_prompt_lab.application.triage import TriagePromptBuilder, TriageStage
from support_prompt_lab.domain import SupportTicket
from support_prompt_lab.prompts import PromptRegistry, PromptStrategy
from tests.fakes import FakeLLMClient

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PROMPT_ROOT = PROJECT_ROOT / "prompts"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def support_ticket() -> SupportTicket:
    return SupportTicket(
        ticket_id="ticket-1042",
        subject="Delivery <delay>",
        message="Tracking says </support_ticket> & nothing else.",
        order_id="order-9001",
    )


def test_zero_shot_builds_system_then_ticket_messages() -> None:
    prepared = TriagePromptBuilder(PromptRegistry(PROMPT_ROOT)).build(
        support_ticket(),
        strategy=PromptStrategy.ZERO_SHOT,
    )

    assert prepared.metadata.version == "1.0.0"
    assert [message.role for message in prepared.messages] == [Role.SYSTEM, Role.USER]
    assert "Subject: Delivery &lt;delay&gt;" in prepared.messages[-1].content
    assert "&lt;/support_ticket&gt; &amp; nothing else" in prepared.messages[-1].content
    assert "Order ID: order-9001" in prepared.messages[-1].content


def test_few_shot_interleaves_examples_before_ticket() -> None:
    prepared = TriagePromptBuilder(PromptRegistry(PROMPT_ROOT)).build(
        support_ticket(),
        strategy=PromptStrategy.FEW_SHOT,
    )

    assert prepared.metadata.version == "1.1.0"
    assert [message.role for message in prepared.messages] == [
        Role.SYSTEM,
        Role.USER,
        Role.ASSISTANT,
        Role.USER,
        Role.ASSISTANT,
        Role.USER,
        Role.ASSISTANT,
        Role.USER,
    ]
    assert "My parcel was due Monday" in prepared.messages[1].content
    assert json.loads(prepared.messages[2].content)["intent"] == "delivery_delay"
    assert "Subject: Delivery &lt;delay&gt;" in prepared.messages[-1].content


def test_many_shot_adds_every_example_before_ticket() -> None:
    prepared = TriagePromptBuilder(PromptRegistry(PROMPT_ROOT)).build(
        support_ticket(),
        strategy=PromptStrategy.MANY_SHOT,
    )

    assert prepared.metadata.version == "1.2.0"
    assert len(prepared.messages) == 16
    assert prepared.messages[0].role is Role.SYSTEM
    assert prepared.messages[-1].role is Role.USER
    assert [message.role for message in prepared.messages[1:-1:2]] == [Role.USER] * 7
    assert [message.role for message in prepared.messages[2:-1:2]] == [Role.ASSISTANT] * 7


def test_exact_version_can_be_selected() -> None:
    prepared = TriagePromptBuilder(PromptRegistry(PROMPT_ROOT)).build(
        support_ticket(),
        version="1.0.0",
    )

    assert prepared.metadata.strategy is PromptStrategy.ZERO_SHOT


def test_ticket_without_order_id_omits_order_line() -> None:
    ticket = SupportTicket(
        ticket_id="ticket-1043",
        subject="Account access",
        message="I cannot sign in.",
    )

    prepared = TriagePromptBuilder(PromptRegistry(PROMPT_ROOT)).build(ticket)

    assert "Order ID:" not in prepared.messages[-1].content


def test_prepared_prompt_builds_model_request_from_versioned_settings() -> None:
    prepared = TriagePromptBuilder(PromptRegistry(PROMPT_ROOT)).build(
        support_ticket(),
        strategy=PromptStrategy.FEW_SHOT,
    )

    request = prepared.to_model_request("gpt-test")

    assert request.model == "gpt-test"
    assert request.messages is prepared.messages
    assert request.temperature == prepared.metadata.model.temperature == 0
    assert request.max_output_tokens == prepared.metadata.model.max_output_tokens == 300
    assert prepared.metadata.name == "triage"
    assert prepared.metadata.version == "1.1.0"
    assert prepared.metadata.strategy is PromptStrategy.FEW_SHOT


def test_prepared_prompt_rejects_blank_runtime_model() -> None:
    prepared = TriagePromptBuilder(PromptRegistry(PROMPT_ROOT)).build(support_ticket())

    with pytest.raises(ValueError, match="model identifier cannot be blank"):
        prepared.to_model_request("   ")


def test_triage_stage_prepares_request_without_calling_client() -> None:
    client = FakeLLMClient([])
    stage = TriageStage(
        prompt_builder=TriagePromptBuilder(PromptRegistry(PROMPT_ROOT)),
        llm_client=client,
        model="gpt-test",
    )

    prepared = stage.prepare(support_ticket(), strategy=PromptStrategy.FEW_SHOT)

    assert prepared.prompt.metadata.version == "1.1.0"
    assert prepared.prompt.metadata.strategy is PromptStrategy.FEW_SHOT
    assert prepared.request.model == "gpt-test"
    assert prepared.request.messages is prepared.prompt.messages
    assert prepared.request.temperature == 0
    assert prepared.request.max_output_tokens == 300
    assert client.requests == []


def test_triage_stage_rejects_blank_runtime_model() -> None:
    with pytest.raises(ValueError, match="model identifier cannot be blank"):
        TriageStage(
            prompt_builder=TriagePromptBuilder(PromptRegistry(PROMPT_ROOT)),
            llm_client=FakeLLMClient([]),
            model="   ",
        )


@pytest.mark.anyio
async def test_triage_stage_executes_prepared_request_once() -> None:
    response = ModelResponse(
        text='{"intent":"delivery_delay"}',
        model="gpt-test-2026-09-19",
        usage=ModelUsage(input_tokens=120, output_tokens=18),
    )
    client = FakeLLMClient([response])
    stage = TriageStage(
        prompt_builder=TriagePromptBuilder(PromptRegistry(PROMPT_ROOT)),
        llm_client=client,
        model="gpt-test",
    )

    completion = await stage.execute(support_ticket(), strategy=PromptStrategy.FEW_SHOT)

    assert client.requests == [completion.prepared.request]
    assert completion.prepared.prompt.metadata.version == "1.1.0"
    assert completion.prepared.prompt.metadata.strategy is PromptStrategy.FEW_SHOT
    assert completion.response is response
    assert completion.response.model == "gpt-test-2026-09-19"
    assert completion.response.usage == ModelUsage(input_tokens=120, output_tokens=18)


@pytest.mark.anyio
async def test_triage_stage_propagates_client_failure_without_completion() -> None:
    client = FakeLLMClient([])
    stage = TriageStage(
        prompt_builder=TriagePromptBuilder(PromptRegistry(PROMPT_ROOT)),
        llm_client=client,
        model="gpt-test",
    )

    with pytest.raises(AssertionError, match="no response queued"):
        await stage.execute(support_ticket(), version="1.0.0")

    assert len(client.requests) == 1
    assert client.requests[0].model == "gpt-test"

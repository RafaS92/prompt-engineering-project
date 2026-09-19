import json
from pathlib import Path

from support_prompt_lab.application.ports import Role
from support_prompt_lab.application.triage import TriagePromptBuilder
from support_prompt_lab.domain import SupportTicket
from support_prompt_lab.prompts import PromptRegistry, PromptStrategy

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PROMPT_ROOT = PROJECT_ROOT / "prompts"


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

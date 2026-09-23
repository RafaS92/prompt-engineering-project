import json
from collections.abc import Sequence
from pathlib import Path

import pytest

from support_prompt_lab.application.policy import PolicyDecisionStage, PolicyPromptBuilder
from support_prompt_lab.application.policy_consensus import PolicyConsensusStage
from support_prompt_lab.application.policy_voting import PolicyDecisionVoter
from support_prompt_lab.application.ports import ModelResponse, ModelUsage
from support_prompt_lab.domain import (
    PolicyAgreement,
    PolicyDisagreement,
    PolicyOutcome,
    PolicyTie,
    Sentiment,
    SupportPolicy,
    SupportTicket,
    TicketIntent,
    TriageResult,
    Urgency,
)
from support_prompt_lab.prompts import PromptRegistry
from tests.fakes import FakeLLMClient

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PROMPT_ROOT = PROJECT_ROOT / "prompts"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def support_ticket() -> SupportTicket:
    return SupportTicket(
        ticket_id="ticket-6001",
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


def support_policies() -> tuple[SupportPolicy, ...]:
    return (
        SupportPolicy(
            policy_id="returns-30-day",
            title="Standard returns",
            text="Returns are allowed within 30 days.",
        ),
    )


def response(
    outcome: PolicyOutcome | str,
    *,
    rationale: str,
    missing_information: Sequence[str] = (),
) -> ModelResponse:
    parsed_outcome = PolicyOutcome(outcome)
    policy_ids = [] if parsed_outcome is PolicyOutcome.ESCALATE else ["returns-30-day"]
    decision = {
        "decision": parsed_outcome.value,
        "applicable_policy_ids": policy_ids,
        "missing_information": list(missing_information),
        "rationale": rationale,
    }
    return ModelResponse(
        text=json.dumps(decision),
        model="gpt-test-resolved",
        usage=ModelUsage(input_tokens=180, output_tokens=30),
    )


def consensus_stage(
    responses: Sequence[ModelResponse],
    *,
    sample_count: int = 1,
) -> tuple[PolicyConsensusStage, FakeLLMClient]:
    client = FakeLLMClient(responses)
    policy_stage = PolicyDecisionStage(
        prompt_builder=PolicyPromptBuilder(PromptRegistry(PROMPT_ROOT)),
        llm_client=client,
        model="gpt-test",
    )
    return (
        PolicyConsensusStage(
            policy_stage=policy_stage,
            voter=PolicyDecisionVoter(),
            sample_count=sample_count,
        ),
        client,
    )


@pytest.mark.anyio
async def test_single_sample_preserves_one_request_and_original_execution() -> None:
    stage, client = consensus_stage(
        [response("allow", rationale="The return is allowed.")],
    )

    execution = await stage.decide(support_ticket(), triage_result(), support_policies())

    assert isinstance(execution.consensus, PolicyAgreement)
    assert execution.selected_decision == execution.samples[0].decision
    assert execution.samples[0].usage == ModelUsage(input_tokens=180, output_tokens=30)
    assert len(client.requests) == 1
    assert client.pending_responses == 0


@pytest.mark.anyio
async def test_three_samples_return_majority_disagreement() -> None:
    stage, client = consensus_stage(
        [
            response("deny", rationale="The return is denied."),
            response("allow", rationale="The return is allowed."),
            response("allow", rationale="The request is eligible."),
        ],
        sample_count=3,
    )

    execution = await stage.decide(support_ticket(), triage_result(), support_policies())

    assert isinstance(execution.consensus, PolicyDisagreement)
    assert execution.selected_decision is not None
    assert execution.selected_decision.decision is PolicyOutcome.ALLOW
    assert execution.consensus.winning_votes == 2
    assert len(execution.samples) == 3
    assert len(client.requests) == 3


@pytest.mark.anyio
async def test_five_samples_are_all_validated_and_voted() -> None:
    stage, client = consensus_stage(
        [response("allow", rationale=f"Allow rationale {index}.") for index in range(5)],
        sample_count=5,
    )

    execution = await stage.decide(support_ticket(), triage_result(), support_policies())

    assert isinstance(execution.consensus, PolicyAgreement)
    assert execution.consensus.winning_votes == 5
    assert len(execution.samples) == 5
    assert len(client.requests) == 5


@pytest.mark.anyio
async def test_three_distinct_samples_return_tie_without_selecting_decision() -> None:
    stage, _ = consensus_stage(
        [
            response("allow", rationale="The return is allowed."),
            response("deny", rationale="The return is denied."),
            response(
                "escalate",
                rationale="Purchase date is required.",
                missing_information=["Purchase date"],
            ),
        ],
        sample_count=3,
    )

    execution = await stage.decide(support_ticket(), triage_result(), support_policies())

    assert isinstance(execution.consensus, PolicyTie)
    assert execution.selected_decision is None
    assert len(execution.samples) == 3


@pytest.mark.parametrize("sample_count", [0, 2, 4, 6])
def test_consensus_stage_rejects_unsupported_sample_counts(sample_count: int) -> None:
    policy_stage = PolicyDecisionStage(
        prompt_builder=PolicyPromptBuilder(PromptRegistry(PROMPT_ROOT)),
        llm_client=FakeLLMClient([]),
        model="gpt-test",
    )

    with pytest.raises(ValueError, match="one of 1, 3, or 5"):
        PolicyConsensusStage(
            policy_stage=policy_stage,
            voter=PolicyDecisionVoter(),
            sample_count=sample_count,
        )

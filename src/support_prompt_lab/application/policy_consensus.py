"""Coordinate independently validated policy decisions and deterministic voting."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from support_prompt_lab.application.policy import PolicyDecisionStage, PolicyExecution
from support_prompt_lab.application.policy_voting import PolicyDecisionVoter
from support_prompt_lab.domain import (
    PolicyConsensusResult,
    PolicyDecision,
    SupportPolicy,
    SupportTicket,
    TriageResult,
)
from support_prompt_lab.prompts import PromptStrategy

_SUPPORTED_SAMPLE_COUNTS = frozenset({1, 3, 5})


@dataclass(frozen=True, slots=True)
class PolicyConsensusExecution:
    """Validated policy samples and the deterministic vote over them."""

    samples: tuple[PolicyExecution, ...]
    consensus: PolicyConsensusResult

    def __post_init__(self) -> None:
        if len(self.samples) != self.consensus.sample_count:
            raise ValueError("policy samples must match the consensus sample count")

    @property
    def selected_decision(self) -> PolicyDecision | None:
        """Return the winning decision, or ``None`` when no strict majority exists."""

        return self.consensus.selected_decision


class PolicyConsensusStage:
    """Run configured policy samples and resolve them with a deterministic voter."""

    def __init__(
        self,
        policy_stage: PolicyDecisionStage,
        voter: PolicyDecisionVoter,
        sample_count: int = 1,
    ) -> None:
        if sample_count not in _SUPPORTED_SAMPLE_COUNTS:
            raise ValueError("policy sample count must be one of 1, 3, or 5")
        self._policy_stage = policy_stage
        self._voter = voter
        self._sample_count = sample_count

    async def decide(
        self,
        ticket: SupportTicket,
        triage_result: TriageResult,
        policies: tuple[SupportPolicy, ...],
        *,
        version: str | None = None,
        strategy: PromptStrategy | str | None = None,
    ) -> PolicyConsensusExecution:
        """Run each sample through the existing validated policy-decision stage."""

        samples: tuple[PolicyExecution, ...]
        if self._sample_count == 1:
            samples = (
                await self._policy_stage.decide(
                    ticket,
                    triage_result,
                    policies,
                    version=version,
                    strategy=strategy,
                ),
            )
        else:
            samples = tuple(
                await asyncio.gather(
                    *(
                        self._policy_stage.decide(
                            ticket,
                            triage_result,
                            policies,
                            version=version,
                            strategy=strategy,
                        )
                        for _ in range(self._sample_count)
                    )
                )
            )

        consensus = self._voter.vote([sample.decision for sample in samples])
        return PolicyConsensusExecution(samples=samples, consensus=consensus)

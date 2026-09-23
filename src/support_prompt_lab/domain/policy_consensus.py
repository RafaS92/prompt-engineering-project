"""Typed results for deterministic policy-decision consensus."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from support_prompt_lab.domain.policy import (
    MissingInformationItem,
    PolicyDecision,
    PolicyIdentifier,
    PolicyOutcome,
)


class PolicyConsensusStatus(StrEnum):
    """Possible outcomes from voting over independent policy decisions."""

    AGREEMENT = "agreement"
    DISAGREEMENT = "disagreement"
    TIE = "tie"


class PolicyDecisionChoice(BaseModel):
    """Rationale-free decision identity used to count equivalent votes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    decision: PolicyOutcome
    applicable_policy_ids: tuple[PolicyIdentifier, ...]
    missing_information: tuple[MissingInformationItem, ...]

    @field_validator("applicable_policy_ids", "missing_information")
    @classmethod
    def values_are_canonical(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if tuple(sorted(values)) != values or len(values) != len(set(values)):
            raise ValueError("choice values must be unique and sorted")
        return values


class PolicyDecisionTally(BaseModel):
    """Number of samples supporting one structured decision choice."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    choice: PolicyDecisionChoice
    votes: int = Field(ge=1)


class _PolicyConsensusResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sample_count: int = Field(ge=1)
    winning_votes: int = Field(ge=1)
    tallies: tuple[PolicyDecisionTally, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def counts_are_consistent(self) -> _PolicyConsensusResult:
        if sum(tally.votes for tally in self.tallies) != self.sample_count:
            raise ValueError("tally votes must equal sample_count")
        if max(tally.votes for tally in self.tallies) != self.winning_votes:
            raise ValueError("winning_votes must equal the largest tally")
        choices = [tally.choice for tally in self.tallies]
        if len(choices) != len(set(choice.model_dump_json() for choice in choices)):
            raise ValueError("tallies must contain unique choices")
        return self


class PolicyAgreement(_PolicyConsensusResult):
    """All independent samples returned the same structured decision."""

    status: Literal[PolicyConsensusStatus.AGREEMENT] = PolicyConsensusStatus.AGREEMENT
    selected_decision: PolicyDecision

    @model_validator(mode="after")
    def result_is_unanimous(self) -> PolicyAgreement:
        if len(self.tallies) != 1 or self.winning_votes != self.sample_count:
            raise ValueError("agreement requires one unanimous decision")
        if not _decision_matches_choice(self.selected_decision, self.tallies[0].choice):
            raise ValueError("selected_decision must match the unanimous choice")
        return self


class PolicyDisagreement(_PolicyConsensusResult):
    """Samples differed, but one structured decision won a strict majority."""

    status: Literal[PolicyConsensusStatus.DISAGREEMENT] = PolicyConsensusStatus.DISAGREEMENT
    selected_decision: PolicyDecision

    @model_validator(mode="after")
    def result_has_strict_non_unanimous_majority(self) -> PolicyDisagreement:
        if len(self.tallies) < 2:
            raise ValueError("disagreement requires at least two choices")
        if self.winning_votes <= self.sample_count // 2:
            raise ValueError("disagreement requires a strict majority")
        if self.winning_votes == self.sample_count:
            raise ValueError("disagreement cannot be unanimous")
        winner = next(tally for tally in self.tallies if tally.votes == self.winning_votes)
        if not _decision_matches_choice(self.selected_decision, winner.choice):
            raise ValueError("selected_decision must match the majority choice")
        return self


class PolicyTie(_PolicyConsensusResult):
    """No structured decision received a strict majority."""

    status: Literal[PolicyConsensusStatus.TIE] = PolicyConsensusStatus.TIE
    selected_decision: None = None
    leading_choices: tuple[PolicyDecisionChoice, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def result_has_no_majority(self) -> PolicyTie:
        if len(self.tallies) < 2:
            raise ValueError("tie requires at least two choices")
        if self.winning_votes > self.sample_count // 2:
            raise ValueError("tie cannot contain a strict majority")
        expected = tuple(
            tally.choice for tally in self.tallies if tally.votes == self.winning_votes
        )
        if self.leading_choices != expected:
            raise ValueError("leading_choices must match the largest tallies")
        return self


type PolicyConsensusResult = Annotated[
    PolicyAgreement | PolicyDisagreement | PolicyTie,
    Field(discriminator="status"),
]


def _decision_matches_choice(
    decision: PolicyDecision,
    choice: PolicyDecisionChoice,
) -> bool:
    return (
        decision.decision is choice.decision
        and tuple(sorted(decision.applicable_policy_ids)) == choice.applicable_policy_ids
        and tuple(sorted(decision.missing_information)) == choice.missing_information
    )

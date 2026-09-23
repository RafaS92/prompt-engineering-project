"""Deterministic majority voting for structured policy decisions."""

from collections import Counter
from collections.abc import Sequence

from support_prompt_lab.domain.policy import PolicyDecision, PolicyOutcome
from support_prompt_lab.domain.policy_consensus import (
    PolicyAgreement,
    PolicyConsensusResult,
    PolicyDecisionChoice,
    PolicyDecisionTally,
    PolicyDisagreement,
    PolicyTie,
)

_DecisionKey = tuple[PolicyOutcome, tuple[str, ...], tuple[str, ...]]


class PolicyDecisionVoter:
    """Resolve validated samples without relying on arrival order."""

    def vote(self, decisions: Sequence[PolicyDecision]) -> PolicyConsensusResult:
        if not decisions:
            raise ValueError("at least one policy decision is required")

        counts = Counter(self._key(decision) for decision in decisions)
        ordered_counts = sorted(
            counts.items(),
            key=lambda item: (-item[1], item[0]),
        )
        tallies = tuple(
            PolicyDecisionTally(choice=self._choice(key), votes=count)
            for key, count in ordered_counts
        )
        winning_votes = tallies[0].votes
        sample_count = len(decisions)

        if len(tallies) == 1:
            selected = self._selected_decision(ordered_counts[0][0], decisions)
            return PolicyAgreement(
                selected_decision=selected,
                sample_count=sample_count,
                winning_votes=winning_votes,
                tallies=tallies,
            )

        if winning_votes > sample_count // 2:
            selected = self._selected_decision(ordered_counts[0][0], decisions)
            return PolicyDisagreement(
                selected_decision=selected,
                sample_count=sample_count,
                winning_votes=winning_votes,
                tallies=tallies,
            )

        return PolicyTie(
            sample_count=sample_count,
            winning_votes=winning_votes,
            tallies=tallies,
            leading_choices=tuple(
                tally.choice for tally in tallies if tally.votes == winning_votes
            ),
        )

    @staticmethod
    def _key(decision: PolicyDecision) -> _DecisionKey:
        return (
            decision.decision,
            tuple(sorted(decision.applicable_policy_ids)),
            tuple(sorted(decision.missing_information)),
        )

    @staticmethod
    def _choice(key: _DecisionKey) -> PolicyDecisionChoice:
        outcome, policy_ids, missing_information = key
        return PolicyDecisionChoice(
            decision=outcome,
            applicable_policy_ids=policy_ids,
            missing_information=missing_information,
        )

    def _selected_decision(
        self,
        key: _DecisionKey,
        decisions: Sequence[PolicyDecision],
    ) -> PolicyDecision:
        rationale = min(decision.rationale for decision in decisions if self._key(decision) == key)
        outcome, policy_ids, missing_information = key
        return PolicyDecision(
            decision=outcome,
            applicable_policy_ids=policy_ids,
            missing_information=missing_information,
            rationale=rationale,
        )

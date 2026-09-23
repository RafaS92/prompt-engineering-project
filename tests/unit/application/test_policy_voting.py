from collections.abc import Sequence

import pytest

from support_prompt_lab.application.policy_voting import PolicyDecisionVoter
from support_prompt_lab.domain import (
    PolicyAgreement,
    PolicyDecision,
    PolicyDisagreement,
    PolicyOutcome,
    PolicyTie,
)


def decision(
    outcome: PolicyOutcome | str,
    policy_ids: Sequence[str],
    *,
    missing_information: Sequence[str] = (),
    rationale: str = "A valid policy rationale.",
) -> PolicyDecision:
    return PolicyDecision(
        decision=outcome,
        applicable_policy_ids=tuple(policy_ids),
        missing_information=tuple(missing_information),
        rationale=rationale,
    )


def test_single_sample_is_unanimous_agreement() -> None:
    sample = decision("allow", ["returns-30-day"])

    result = PolicyDecisionVoter().vote([sample])

    assert isinstance(result, PolicyAgreement)
    assert result.selected_decision == sample
    assert result.sample_count == 1
    assert result.winning_votes == 1
    assert result.tallies[0].votes == 1


def test_equivalent_structures_agree_despite_order_and_rationale() -> None:
    samples = [
        decision(
            "escalate",
            ["supported-request-scope", "account-recovery"],
            missing_information=["Order ID", "Registered email"],
            rationale="Zulu rationale.",
        ),
        decision(
            "escalate",
            ["account-recovery", "supported-request-scope"],
            missing_information=["Registered email", "Order ID"],
            rationale="Alpha rationale.",
        ),
        decision(
            "escalate",
            ["account-recovery", "supported-request-scope"],
            missing_information=["Order ID", "Registered email"],
            rationale="Middle rationale.",
        ),
    ]

    result = PolicyDecisionVoter().vote(samples)

    assert isinstance(result, PolicyAgreement)
    assert result.selected_decision.applicable_policy_ids == (
        "account-recovery",
        "supported-request-scope",
    )
    assert result.selected_decision.missing_information == ("Order ID", "Registered email")
    assert result.selected_decision.rationale == "Alpha rationale."


def test_strict_majority_returns_typed_disagreement() -> None:
    majority = decision("allow", ["returns-30-day"], rationale="Majority rationale.")
    samples = [
        decision("deny", ["returns-30-day"]),
        majority,
        decision("allow", ["returns-30-day"], rationale="Other majority rationale."),
    ]

    result = PolicyDecisionVoter().vote(samples)

    assert isinstance(result, PolicyDisagreement)
    assert result.selected_decision == majority
    assert result.sample_count == 3
    assert result.winning_votes == 2
    assert [tally.votes for tally in result.tallies] == [2, 1]


def test_equal_leaders_return_typed_tie() -> None:
    samples = [
        decision("allow", ["returns-30-day"]),
        decision("deny", ["returns-30-day"]),
        decision("escalate", ["returns-30-day"], missing_information=["Purchase date"]),
    ]

    result = PolicyDecisionVoter().vote(samples)

    assert isinstance(result, PolicyTie)
    assert result.selected_decision is None
    assert result.sample_count == 3
    assert result.winning_votes == 1
    assert len(result.leading_choices) == 3


def test_unique_leader_without_strict_majority_is_unresolved_tie() -> None:
    samples = [
        decision("allow", ["returns-30-day"]),
        decision("allow", ["returns-30-day"], rationale="Second allow rationale."),
        decision("deny", ["returns-30-day"]),
        decision("escalate", ["returns-30-day"], missing_information=["Purchase date"]),
        decision("escalate", ["supported-request-scope"]),
    ]

    result = PolicyDecisionVoter().vote(samples)

    assert isinstance(result, PolicyTie)
    assert result.winning_votes == 2
    assert len(result.leading_choices) == 1
    assert result.leading_choices[0].decision is PolicyOutcome.ALLOW


def test_policy_reference_disagreement_counts_as_distinct_choices() -> None:
    result = PolicyDecisionVoter().vote(
        [
            decision("allow", ["returns-30-day"]),
            decision("allow", ["supported-request-scope"]),
        ]
    )

    assert isinstance(result, PolicyTie)
    assert len(result.tallies) == 2


def test_result_is_independent_of_sample_order() -> None:
    samples = [
        decision("allow", ["returns-30-day"], rationale="Zulu rationale."),
        decision("deny", ["returns-30-day"]),
        decision("allow", ["returns-30-day"], rationale="Alpha rationale."),
    ]
    voter = PolicyDecisionVoter()

    forward = voter.vote(samples)
    reverse = voter.vote(list(reversed(samples)))

    assert forward == reverse


def test_voter_rejects_empty_samples() -> None:
    with pytest.raises(ValueError, match="at least one policy decision"):
        PolicyDecisionVoter().vote([])

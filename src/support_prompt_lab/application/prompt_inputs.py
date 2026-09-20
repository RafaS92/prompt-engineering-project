"""Deterministic serialization of domain data used in prompt variables."""

import json
from collections.abc import Sequence

from support_prompt_lab.domain import PolicyDecision, SupportPolicy, SupportTicket, TriageResult


def format_ticket(ticket: SupportTicket) -> str:
    """Return the minimal customer-ticket text required by prompt stages."""

    fields = [f"Subject: {ticket.subject}", f"Message: {ticket.message}"]
    if ticket.order_id is not None:
        fields.append(f"Order ID: {ticket.order_id}")
    return "\n".join(fields)


def format_triage_result(result: TriageResult) -> str:
    """Serialize validated triage data deterministically."""

    return json.dumps(result.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":"))


def format_support_policies(policies: Sequence[SupportPolicy]) -> str:
    """Serialize supplied policies deterministically without Python representations."""

    documents = [policy.model_dump(mode="json") for policy in policies]
    return json.dumps(documents, ensure_ascii=False, separators=(",", ":"))


def format_policy_decision(decision: PolicyDecision) -> str:
    """Serialize a validated policy decision deterministically."""

    return json.dumps(decision.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":"))

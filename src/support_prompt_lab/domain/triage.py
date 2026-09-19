"""Triage classification domain models."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class TicketIntent(StrEnum):
    """Supported categories for an e-commerce support request."""

    REFUND = "refund"
    DAMAGED_ORDER = "damaged_order"
    DELIVERY_DELAY = "delivery_delay"
    CANCELLATION = "cancellation"
    BILLING = "billing"
    ACCOUNT_ACCESS = "account_access"
    OTHER = "other"


class Urgency(StrEnum):
    """Operational priority assigned during triage."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Sentiment(StrEnum):
    """Customer sentiment expressed in a support request."""

    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    POSITIVE = "positive"


class TriageResult(BaseModel):
    """Validated structured output from the triage stage."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    intent: TicketIntent
    urgency: Urgency
    sentiment: Sentiment
    rationale: str = Field(min_length=1, max_length=200)

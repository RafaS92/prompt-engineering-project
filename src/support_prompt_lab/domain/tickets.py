"""Support-ticket domain models."""

from pydantic import BaseModel, ConfigDict, Field

_IDENTIFIER_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_-]*$"


class SupportTicket(BaseModel):
    """Validated customer request accepted by the support workflow."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    ticket_id: str = Field(min_length=1, max_length=64, pattern=_IDENTIFIER_PATTERN)
    subject: str = Field(min_length=1, max_length=200)
    message: str = Field(min_length=1, max_length=5_000)
    order_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        pattern=_IDENTIFIER_PATTERN,
    )

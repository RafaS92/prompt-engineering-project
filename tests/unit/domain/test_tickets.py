import pytest
from pydantic import ValidationError

from support_prompt_lab.domain import SupportTicket


def test_support_ticket_accepts_and_normalizes_valid_input() -> None:
    ticket = SupportTicket(
        ticket_id=" ticket-1042 ",
        subject=" Delivery is late ",
        message=" My parcel was due Monday. ",
        order_id=" order_9001 ",
    )

    assert ticket.model_dump() == {
        "ticket_id": "ticket-1042",
        "subject": "Delivery is late",
        "message": "My parcel was due Monday.",
        "order_id": "order_9001",
    }


def test_support_ticket_allows_missing_order_id() -> None:
    ticket = SupportTicket(
        ticket_id="ticket-1042",
        subject="Account access",
        message="I cannot sign in.",
    )

    assert ticket.order_id is None


@pytest.mark.parametrize("field", ["subject", "message"])
def test_support_ticket_rejects_blank_content(field: str) -> None:
    document = {
        "ticket_id": "ticket-1042",
        "subject": "Account access",
        "message": "I cannot sign in.",
        field: "   ",
    }

    with pytest.raises(ValidationError):
        SupportTicket.model_validate(document)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("ticket_id", "ticket 1042"),
        ("ticket_id", "x" * 65),
        ("subject", "x" * 201),
        ("message", "x" * 5_001),
        ("order_id", "order/9001"),
    ],
)
def test_support_ticket_rejects_invalid_or_oversized_fields(field: str, value: str) -> None:
    document = {
        "ticket_id": "ticket-1042",
        "subject": "Account access",
        "message": "I cannot sign in.",
        field: value,
    }

    with pytest.raises(ValidationError):
        SupportTicket.model_validate(document)


def test_support_ticket_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="customer_email"):
        SupportTicket.model_validate(
            {
                "ticket_id": "ticket-1042",
                "subject": "Account access",
                "message": "I cannot sign in.",
                "customer_email": "customer@example.test",
            }
        )


def test_support_ticket_is_immutable() -> None:
    ticket = SupportTicket(
        ticket_id="ticket-1042",
        subject="Account access",
        message="I cannot sign in.",
    )

    with pytest.raises(ValidationError, match="frozen"):
        ticket.subject = "Changed"  # type: ignore[misc]

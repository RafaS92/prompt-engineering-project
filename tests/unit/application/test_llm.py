import pytest

from support_prompt_lab.application.ports import (
    LLMClient,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ModelUsage,
    Role,
)
from tests.fakes import FakeLLMClient


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def model_request() -> ModelRequest:
    return ModelRequest(
        model="test-model",
        messages=(
            ModelMessage(role=Role.SYSTEM, content="Classify the ticket."),
            ModelMessage(role=Role.USER, content="The order is late."),
        ),
        temperature=0,
        max_output_tokens=300,
    )


def model_response(text: str = '{"intent":"delivery_delay"}') -> ModelResponse:
    return ModelResponse(
        text=text,
        model="test-model-2026-09-19",
        usage=ModelUsage(input_tokens=42, output_tokens=8),
    )


def test_fake_llm_client_satisfies_port() -> None:
    client: LLMClient = FakeLLMClient([model_response()])

    assert isinstance(client, FakeLLMClient)


@pytest.mark.anyio
async def test_fake_llm_client_returns_queued_responses_and_records_requests() -> None:
    first = model_response("first")
    second = model_response("second")
    client = FakeLLMClient([first, second])
    request = model_request()

    assert await client.complete(request) is first
    assert await client.complete(request) is second
    assert client.requests == [request, request]
    assert client.pending_responses == 0


@pytest.mark.anyio
async def test_fake_llm_client_fails_when_no_response_is_queued() -> None:
    client = FakeLLMClient([])

    with pytest.raises(AssertionError, match="no response queued"):
        await client.complete(model_request())


@pytest.mark.parametrize(
    "message",
    ["", "   "],
)
def test_model_message_rejects_blank_content(message: str) -> None:
    with pytest.raises(ValueError, match="cannot be blank"):
        ModelMessage(role=Role.USER, content=message)


@pytest.mark.parametrize(
    "overrides",
    [
        {"model": " "},
        {"messages": ()},
        {"temperature": -0.1},
        {"temperature": 2.1},
        {"max_output_tokens": 0},
    ],
)
def test_model_request_rejects_invalid_settings(overrides: dict[str, object]) -> None:
    values: dict[str, object] = {
        "model": "test-model",
        "messages": (ModelMessage(role=Role.USER, content="Classify this."),),
        "temperature": 0,
        "max_output_tokens": 300,
    }
    values.update(overrides)

    with pytest.raises(ValueError):
        ModelRequest(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("input_tokens", "output_tokens"),
    [(-1, 0), (0, -1)],
)
def test_model_usage_rejects_negative_counts(input_tokens: int, output_tokens: int) -> None:
    with pytest.raises(ValueError, match="cannot be negative"):
        ModelUsage(input_tokens=input_tokens, output_tokens=output_tokens)

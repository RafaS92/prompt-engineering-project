import pytest

from support_prompt_lab.application.errors import OutputLeakageError
from support_prompt_lab.application.output_security import (
    LeakageCanaryInjector,
    LeakageProtectedLLMClient,
    ModelOutputScanner,
)
from support_prompt_lab.application.ports import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ModelUsage,
    Role,
)
from tests.fakes import FakeLLMClient

CANARY = "spl_leakage_canary_0123456789abcdef0123456789abcdef"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def model_request(messages: tuple[ModelMessage, ...] | None = None) -> ModelRequest:
    return ModelRequest(
        model="gpt-test",
        messages=messages
        or (
            ModelMessage(role=Role.SYSTEM, content="Classify the support ticket."),
            ModelMessage(role=Role.USER, content="My delivery is late."),
        ),
        temperature=0,
        max_output_tokens=300,
    )


def model_response(text: str) -> ModelResponse:
    return ModelResponse(
        text=text,
        model="gpt-test-resolved",
        usage=ModelUsage(input_tokens=50, output_tokens=10),
    )


def test_injector_appends_canary_only_to_system_message() -> None:
    request = model_request()

    protected = LeakageCanaryInjector().inject(request, CANARY)

    assert protected is not request
    assert protected.messages[0].content == (
        f"Classify the support ticket.\n\n<leakage_canary>{CANARY}</leakage_canary>"
    )
    assert CANARY not in protected.messages[1].content
    assert CANARY not in request.messages[0].content
    assert protected.model == request.model
    assert protected.temperature == request.temperature
    assert protected.max_output_tokens == request.max_output_tokens


@pytest.mark.parametrize(
    "messages",
    [
        (ModelMessage(role=Role.USER, content="No system message."),),
        (
            ModelMessage(role=Role.SYSTEM, content="First system message."),
            ModelMessage(role=Role.SYSTEM, content="Second system message."),
        ),
    ],
    ids=["missing-system", "multiple-system"],
)
def test_injector_requires_exactly_one_system_message(
    messages: tuple[ModelMessage, ...],
) -> None:
    with pytest.raises(ValueError, match="exactly one system message"):
        LeakageCanaryInjector().inject(model_request(messages), CANARY)


@pytest.mark.parametrize(
    "canary",
    [
        "",
        "wrong-prefix",
        "spl_leakage_canary_",
        "spl_leakage_canary_short",
        "spl_leakage_canary_0123456789ABCDEF0123456789ABCDEF",
    ],
)
def test_injector_rejects_invalid_canary(canary: str) -> None:
    with pytest.raises(ValueError, match="invalid format"):
        LeakageCanaryInjector().inject(model_request(), canary)


def test_scanner_allows_output_without_canary() -> None:
    ModelOutputScanner().scan('{"result":"safe"}', canary=CANARY)


def test_scanner_rejects_canary_case_insensitively_without_exposing_it() -> None:
    output = f'{{"result":"{CANARY.upper()}"}}'

    with pytest.raises(OutputLeakageError) as captured:
        ModelOutputScanner().scan(output, canary=CANARY)

    assert str(captured.value) == "model output failed leakage validation"
    assert CANARY.casefold() not in str(captured.value).casefold()


@pytest.mark.anyio
async def test_protected_client_injects_then_scans_one_model_call() -> None:
    response = model_response('{"result":"safe"}')
    delegate = FakeLLMClient([response])
    client = LeakageProtectedLLMClient(
        delegate,
        canary_factory=lambda: CANARY,
    )

    returned = await client.complete(model_request())

    assert returned is response
    assert len(delegate.requests) == 1
    assert CANARY in delegate.requests[0].messages[0].content


@pytest.mark.anyio
async def test_protected_client_blocks_leak_before_returning_response() -> None:
    delegate = FakeLLMClient([model_response(f'{{"result":"{CANARY}"}}')])
    client = LeakageProtectedLLMClient(
        delegate,
        canary_factory=lambda: CANARY,
    )

    with pytest.raises(OutputLeakageError):
        await client.complete(model_request())

    assert len(delegate.requests) == 1

import json

import httpx2
import pytest
from openai import AsyncOpenAI

from support_prompt_lab.application.ports import ModelMessage, ModelRequest, Role
from support_prompt_lab.infrastructure import LLMProviderError, OpenAILLMClient


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def response_document() -> dict[str, object]:
    return {
        "id": "resp_test",
        "object": "response",
        "created_at": 0,
        "status": "completed",
        "error": None,
        "incomplete_details": None,
        "instructions": None,
        "max_output_tokens": 100,
        "model": "gpt-test-resolved",
        "output": [
            {
                "id": "msg_test",
                "type": "message",
                "status": "completed",
                "role": "assistant",
                "content": [
                    {
                        "type": "output_text",
                        "text": '{"result":"ok"}',
                        "annotations": [],
                    }
                ],
            }
        ],
        "parallel_tool_calls": True,
        "previous_response_id": None,
        "reasoning": {"effort": None, "summary": None},
        "store": False,
        "temperature": 0,
        "text": {"format": {"type": "text"}},
        "tool_choice": "auto",
        "tools": [],
        "top_p": 1,
        "truncation": "disabled",
        "usage": {
            "input_tokens": 24,
            "input_tokens_details": {
                "cached_tokens": 0,
                "cache_write_tokens": 0,
            },
            "output_tokens": 8,
            "output_tokens_details": {"reasoning_tokens": 0},
            "total_tokens": 32,
        },
        "metadata": {},
    }


def model_request() -> ModelRequest:
    return ModelRequest(
        model="gpt-test",
        messages=(
            ModelMessage(role=Role.SYSTEM, content="Return JSON."),
            ModelMessage(role=Role.USER, content="Analyze this ticket."),
        ),
        temperature=0,
        max_output_tokens=100,
    )


@pytest.mark.anyio
async def test_openai_client_translates_request_and_response() -> None:
    captured: dict[str, object] = {}

    async def handle(request: httpx2.Request) -> httpx2.Response:
        document = json.loads(request.content)
        assert isinstance(document, dict)
        captured.update(document)
        return httpx2.Response(200, json=response_document())

    async with httpx2.AsyncClient(transport=httpx2.MockTransport(handle)) as http_client:
        sdk = AsyncOpenAI(api_key="test-key", http_client=http_client, max_retries=0)
        response = await OpenAILLMClient(sdk).complete(model_request())

    assert captured["model"] == "gpt-test"
    assert captured["temperature"] == 0
    assert captured["max_output_tokens"] == 100
    assert captured["store"] is False
    assert captured["input"] == [
        {"role": "system", "content": "Return JSON.", "type": "message"},
        {
            "role": "user",
            "content": "Analyze this ticket.",
            "type": "message",
        },
    ]
    assert response.text == '{"result":"ok"}'
    assert response.model == "gpt-test-resolved"
    assert response.usage.input_tokens == 24
    assert response.usage.output_tokens == 8


@pytest.mark.anyio
async def test_openai_client_wraps_provider_errors() -> None:
    async def handle(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            500,
            request=request,
            json={"error": {"message": "sensitive provider failure"}},
        )

    async with httpx2.AsyncClient(transport=httpx2.MockTransport(handle)) as http_client:
        sdk = AsyncOpenAI(api_key="test-key", http_client=http_client, max_retries=0)
        with pytest.raises(LLMProviderError) as captured:
            await OpenAILLMClient(sdk).complete(model_request())

    assert str(captured.value) == "language model provider request failed"
    assert "sensitive" not in str(captured.value)

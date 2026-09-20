"""OpenAI Responses API implementation of the language-model port."""

from typing import Literal

from openai import APIError, AsyncOpenAI
from openai.types.responses import EasyInputMessageParam, ResponseInputParam

from support_prompt_lab.application.ports import (
    LLMClient,
    ModelRequest,
    ModelResponse,
    ModelUsage,
    Role,
)
from support_prompt_lab.infrastructure.errors import LLMProviderError

_ROLE_MAP: dict[Role, Literal["system", "user", "assistant"]] = {
    Role.SYSTEM: "system",
    Role.USER: "user",
    Role.ASSISTANT: "assistant",
}
_PROVIDER_ERROR_MESSAGE = "language model provider request failed"


class OpenAILLMClient(LLMClient):
    """Execute provider-neutral requests through OpenAI's Responses API."""

    def __init__(self, client: AsyncOpenAI) -> None:
        self._client = client

    async def complete(self, request: ModelRequest) -> ModelResponse:
        input_messages: ResponseInputParam = [
            EasyInputMessageParam(
                role=_ROLE_MAP[message.role],
                content=message.content,
                type="message",
            )
            for message in request.messages
        ]
        try:
            response = await self._client.responses.create(
                model=request.model,
                input=input_messages,
                temperature=request.temperature,
                max_output_tokens=request.max_output_tokens,
                store=False,
            )
        except APIError as error:
            raise LLMProviderError(_PROVIDER_ERROR_MESSAGE) from error

        if not response.output_text.strip() or response.usage is None:
            raise LLMProviderError(_PROVIDER_ERROR_MESSAGE)
        return ModelResponse(
            text=response.output_text,
            model=response.model,
            usage=ModelUsage(
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            ),
        )

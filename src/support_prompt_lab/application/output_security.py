"""Request-specific leakage canaries and centralized model-output scanning."""

from __future__ import annotations

import re
import secrets
from collections.abc import Callable

from support_prompt_lab.application.errors import OutputLeakageError
from support_prompt_lab.application.ports import (
    LLMClient,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    Role,
)

_CANARY_PREFIX = "spl_leakage_canary_"
_CANARY_PATTERN = re.compile(rf"^{_CANARY_PREFIX}[0-9a-f]{{32}}$")
_CANARY_OPEN_TAG = "<leakage_canary>"
_CANARY_CLOSE_TAG = "</leakage_canary>"
_OUTPUT_LEAKAGE_MESSAGE = "model output failed leakage validation"

type CanaryFactory = Callable[[], str]


def generate_leakage_canary() -> str:
    """Return an unpredictable marker scoped to one model request."""

    return f"{_CANARY_PREFIX}{secrets.token_hex(16)}"


class LeakageCanaryInjector:
    """Append one canary element to the request's trusted system message."""

    def inject(self, request: ModelRequest, canary: str) -> ModelRequest:
        if _CANARY_PATTERN.fullmatch(canary) is None:
            raise ValueError("leakage canary has an invalid format")

        system_indexes = [
            index for index, message in enumerate(request.messages) if message.role is Role.SYSTEM
        ]
        if len(system_indexes) != 1:
            raise ValueError("model request must contain exactly one system message")

        system_index = system_indexes[0]
        messages = list(request.messages)
        system_message = messages[system_index]
        messages[system_index] = ModelMessage(
            role=Role.SYSTEM,
            content=(
                f"{system_message.content.rstrip()}\n\n"
                f"{_CANARY_OPEN_TAG}{canary}{_CANARY_CLOSE_TAG}"
            ),
        )
        return ModelRequest(
            model=request.model,
            messages=tuple(messages),
            temperature=request.temperature,
            max_output_tokens=request.max_output_tokens,
        )


class ModelOutputScanner:
    """Reject raw provider output that reproduces confidential control markers."""

    def scan(self, output: str, *, canary: str) -> None:
        if canary.casefold() in output.casefold():
            raise OutputLeakageError(_OUTPUT_LEAKAGE_MESSAGE)


class LeakageProtectedLLMClient:
    """Decorate one LLM client with per-request canary injection and scanning."""

    def __init__(
        self,
        client: LLMClient,
        *,
        injector: LeakageCanaryInjector | None = None,
        scanner: ModelOutputScanner | None = None,
        canary_factory: CanaryFactory = generate_leakage_canary,
    ) -> None:
        self._client = client
        self._injector = injector or LeakageCanaryInjector()
        self._scanner = scanner or ModelOutputScanner()
        self._canary_factory = canary_factory

    async def complete(self, request: ModelRequest) -> ModelResponse:
        canary = self._canary_factory()
        protected_request = self._injector.inject(request, canary)
        response = await self._client.complete(protected_request)
        self._scanner.scan(response.text, canary=canary)
        return response

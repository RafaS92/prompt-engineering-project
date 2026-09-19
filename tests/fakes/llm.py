"""Deterministic language-model client for tests."""

from collections import deque
from collections.abc import Iterable

from support_prompt_lab.application.ports import ModelRequest, ModelResponse


class FakeLLMClient:
    """Record requests and return queued responses in insertion order."""

    def __init__(self, responses: Iterable[ModelResponse]) -> None:
        self._responses = deque(responses)
        self.requests: list[ModelRequest] = []

    async def complete(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        if not self._responses:
            raise AssertionError("fake LLM client has no response queued")
        return self._responses.popleft()

    @property
    def pending_responses(self) -> int:
        return len(self._responses)

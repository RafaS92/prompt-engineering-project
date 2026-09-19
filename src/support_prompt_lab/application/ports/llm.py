"""Provider-neutral language-model request and response contracts."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class Role(StrEnum):
    """Supported language-model message roles."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass(frozen=True, slots=True)
class ModelMessage:
    """One ordered message sent to a language model."""

    role: Role
    content: str

    def __post_init__(self) -> None:
        if not self.content.strip():
            raise ValueError("model message content cannot be blank")


@dataclass(frozen=True, slots=True)
class ModelRequest:
    """Complete provider-independent input for one model call."""

    model: str
    messages: tuple[ModelMessage, ...]
    temperature: float
    max_output_tokens: int

    def __post_init__(self) -> None:
        if not self.model.strip():
            raise ValueError("model identifier cannot be blank")
        if not self.messages:
            raise ValueError("model request must contain at least one message")
        if not 0 <= self.temperature <= 2:
            raise ValueError("temperature must be between 0 and 2")
        if self.max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be positive")


@dataclass(frozen=True, slots=True)
class ModelUsage:
    """Provider-reported token consumption for one model call."""

    input_tokens: int
    output_tokens: int

    def __post_init__(self) -> None:
        if self.input_tokens < 0 or self.output_tokens < 0:
            raise ValueError("token counts cannot be negative")


@dataclass(frozen=True, slots=True)
class ModelResponse:
    """Provider-independent result returned to an application stage."""

    text: str
    model: str
    usage: ModelUsage


class LLMClient(Protocol):
    """Asynchronous interface implemented by language-model providers."""

    async def complete(self, request: ModelRequest) -> ModelResponse:
        """Return one model completion for the supplied request."""
        ...

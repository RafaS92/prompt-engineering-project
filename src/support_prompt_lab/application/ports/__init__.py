"""Interfaces implemented by external service adapters."""

from support_prompt_lab.application.ports.llm import (
    LLMClient,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ModelUsage,
    Role,
)

__all__ = [
    "LLMClient",
    "ModelMessage",
    "ModelRequest",
    "ModelResponse",
    "ModelUsage",
    "Role",
]

"""Controlled infrastructure-layer failures."""


class InfrastructureError(RuntimeError):
    """Base class for expected external-service failures."""


class LLMProviderError(InfrastructureError):
    """Raised when the configured language-model provider cannot return a result."""

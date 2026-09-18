"""Errors raised by the prompt library."""


class PromptLibraryError(ValueError):
    """Base class for invalid prompt-library content or usage."""


class PromptNotFoundError(PromptLibraryError):
    """Raised when a requested prompt cannot be found."""


class PromptMetadataError(PromptLibraryError):
    """Raised when prompt metadata or its directory is inconsistent."""


class PromptRenderError(PromptLibraryError):
    """Raised when a prompt cannot be rendered with the supplied variables."""

"""Controlled errors raised by application use cases."""


class ApplicationError(RuntimeError):
    """Base class for expected application-layer failures."""


class TriageOutputError(ApplicationError):
    """Raised when model output cannot satisfy the triage contract."""

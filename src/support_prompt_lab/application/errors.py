"""Controlled errors raised by application use cases."""

from enum import StrEnum
from typing import ClassVar


class WorkflowErrorCode(StrEnum):
    """Stable, safe identifiers for public workflow failures."""

    WORKFLOW_FAILED = "workflow_failed"
    TRIAGE_OUTPUT_INVALID = "triage_output_invalid"
    POLICY_OUTPUT_INVALID = "policy_output_invalid"
    DRAFTING_BLOCKED = "drafting_blocked"
    DRAFT_OUTPUT_INVALID = "draft_output_invalid"
    REVIEW_BLOCKED = "review_blocked"
    REVIEW_OUTPUT_INVALID = "review_output_invalid"
    MODEL_PROVIDER_FAILED = "model_provider_failed"


class ApplicationError(RuntimeError):
    """Base class for expected application-layer failures."""

    error_code: ClassVar[WorkflowErrorCode] = WorkflowErrorCode.WORKFLOW_FAILED


class TriageOutputError(ApplicationError):
    """Raised when model output cannot satisfy the triage contract."""

    error_code = WorkflowErrorCode.TRIAGE_OUTPUT_INVALID


class PolicyDecisionOutputError(ApplicationError):
    """Raised when model output cannot satisfy the policy-decision contract."""

    error_code = WorkflowErrorCode.POLICY_OUTPUT_INVALID


class DraftingBlockedError(ApplicationError):
    """Raised when deterministic rules prohibit response drafting."""

    error_code = WorkflowErrorCode.DRAFTING_BLOCKED


class DraftOutputError(ApplicationError):
    """Raised when model output cannot satisfy the response-draft contract."""

    error_code = WorkflowErrorCode.DRAFT_OUTPUT_INVALID


class ReviewBlockedError(ApplicationError):
    """Raised when deterministic rules prohibit response review."""

    error_code = WorkflowErrorCode.REVIEW_BLOCKED


class ReviewOutputError(ApplicationError):
    """Raised when model output cannot satisfy the response-review contract."""

    error_code = WorkflowErrorCode.REVIEW_OUTPUT_INVALID

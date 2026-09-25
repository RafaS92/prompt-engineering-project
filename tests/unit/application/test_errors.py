import pytest

from support_prompt_lab.application.errors import (
    ApplicationError,
    DraftingBlockedError,
    DraftOutputError,
    InjectionDetectionOutputError,
    OutputLeakageError,
    PolicyDecisionOutputError,
    ReviewBlockedError,
    ReviewOutputError,
    TriageOutputError,
    WorkflowErrorCode,
)


@pytest.mark.parametrize(
    ("error_type", "expected_code"),
    [
        (ApplicationError, WorkflowErrorCode.WORKFLOW_FAILED),
        (InjectionDetectionOutputError, WorkflowErrorCode.INJECTION_OUTPUT_INVALID),
        (OutputLeakageError, WorkflowErrorCode.OUTPUT_LEAKAGE_DETECTED),
        (TriageOutputError, WorkflowErrorCode.TRIAGE_OUTPUT_INVALID),
        (PolicyDecisionOutputError, WorkflowErrorCode.POLICY_OUTPUT_INVALID),
        (DraftingBlockedError, WorkflowErrorCode.DRAFTING_BLOCKED),
        (DraftOutputError, WorkflowErrorCode.DRAFT_OUTPUT_INVALID),
        (ReviewBlockedError, WorkflowErrorCode.REVIEW_BLOCKED),
        (ReviewOutputError, WorkflowErrorCode.REVIEW_OUTPUT_INVALID),
    ],
)
def test_application_errors_expose_stable_safe_codes(
    error_type: type[ApplicationError],
    expected_code: WorkflowErrorCode,
) -> None:
    assert error_type.error_code is expected_code

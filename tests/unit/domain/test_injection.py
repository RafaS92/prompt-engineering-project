import pytest
from pydantic import ValidationError

from support_prompt_lab.domain import InjectionCategory, InjectionDetectionResult


def test_injection_result_accepts_safe_input() -> None:
    result = InjectionDetectionResult(
        detected=False,
        categories=(),
        rationale="The inputs contain only support data.",
    )

    assert result.detected is False
    assert result.categories == ()


def test_injection_result_accepts_unique_detected_categories() -> None:
    result = InjectionDetectionResult(
        detected=True,
        categories=(
            InjectionCategory.INSTRUCTION_OVERRIDE,
            InjectionCategory.PROMPT_EXTRACTION,
        ),
        rationale="The ticket tries to replace instructions and obtain protected content.",
    )

    assert result.detected is True
    assert result.categories == (
        InjectionCategory.INSTRUCTION_OVERRIDE,
        InjectionCategory.PROMPT_EXTRACTION,
    )


@pytest.mark.parametrize(
    ("detected", "categories"),
    [
        (True, ()),
        (False, (InjectionCategory.JAILBREAK,)),
        (
            True,
            (
                InjectionCategory.DELIMITER_ATTACK,
                InjectionCategory.DELIMITER_ATTACK,
            ),
        ),
    ],
)
def test_injection_result_rejects_inconsistent_or_duplicate_categories(
    detected: bool,
    categories: tuple[InjectionCategory, ...],
) -> None:
    with pytest.raises(ValidationError):
        InjectionDetectionResult(
            detected=detected,
            categories=categories,
            rationale="Invalid result.",
        )


def test_injection_result_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="confidence"):
        InjectionDetectionResult.model_validate(
            {
                "detected": False,
                "categories": [],
                "rationale": "The inputs are safe.",
                "confidence": 0.9,
            }
        )

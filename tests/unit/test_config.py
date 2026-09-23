import pytest
from pydantic import ValidationError

from support_prompt_lab.config import Settings
from support_prompt_lab.prompts import PromptStrategy


def test_settings_default_to_evaluated_zero_shot_strategy() -> None:
    settings = Settings.model_validate({})

    assert settings.triage_prompt_strategy is PromptStrategy.ZERO_SHOT
    assert settings.policy_decision_sample_count == 1


@pytest.mark.parametrize("sample_count", [1, 3, 5])
def test_settings_accept_supported_policy_sample_counts(sample_count: int) -> None:
    settings = Settings.model_validate({"policy_decision_sample_count": sample_count})

    assert settings.policy_decision_sample_count == sample_count


@pytest.mark.parametrize("sample_count", [0, 2, 4, 6])
def test_settings_reject_invalid_policy_sample_counts(sample_count: int) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({"policy_decision_sample_count": sample_count})

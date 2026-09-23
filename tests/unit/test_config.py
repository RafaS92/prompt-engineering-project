from support_prompt_lab.config import Settings
from support_prompt_lab.prompts import PromptStrategy


def test_settings_default_to_evaluated_zero_shot_strategy() -> None:
    settings = Settings.model_validate({})

    assert settings.triage_prompt_strategy is PromptStrategy.ZERO_SHOT

"""Convert rendered prompts into ordered provider-neutral messages."""

from support_prompt_lab.application.ports import ModelMessage, Role
from support_prompt_lab.prompts import RenderedPrompt


def build_model_messages(rendered: RenderedPrompt) -> tuple[ModelMessage, ...]:
    """Order system, example pairs, and the live user message for one model call."""

    messages = [ModelMessage(role=Role.SYSTEM, content=rendered.system)]
    for example in rendered.examples:
        messages.extend(
            (
                ModelMessage(role=Role.USER, content=example.user),
                ModelMessage(role=Role.ASSISTANT, content=example.assistant),
            )
        )
    messages.append(ModelMessage(role=Role.USER, content=rendered.user))
    return tuple(messages)

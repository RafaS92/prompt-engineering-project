"""Prepare support tickets for the triage model stage."""

from dataclasses import dataclass

from support_prompt_lab.application.ports import ModelMessage, ModelRequest, Role
from support_prompt_lab.domain import SupportTicket
from support_prompt_lab.prompts import PromptMetadata, PromptRegistry, PromptStrategy


@dataclass(frozen=True, slots=True)
class PreparedTriagePrompt:
    """Validated prompt metadata and ordered messages for one ticket."""

    metadata: PromptMetadata
    messages: tuple[ModelMessage, ...]

    def to_model_request(self, model: str) -> ModelRequest:
        """Apply versioned model settings to the prepared messages."""

        return ModelRequest(
            model=model,
            messages=self.messages,
            temperature=self.metadata.model.temperature,
            max_output_tokens=self.metadata.model.max_output_tokens,
        )


class TriagePromptBuilder:
    """Select and render a triage prompt without invoking a model."""

    def __init__(self, registry: PromptRegistry) -> None:
        self._registry = registry

    def build(
        self,
        ticket: SupportTicket,
        *,
        version: str | None = None,
        strategy: PromptStrategy | str | None = None,
    ) -> PreparedTriagePrompt:
        rendered = self._registry.render(
            "triage",
            {"ticket_text": self._ticket_text(ticket)},
            version=version,
            strategy=strategy,
        )
        messages = [ModelMessage(role=Role.SYSTEM, content=rendered.system)]
        for example in rendered.examples:
            messages.extend(
                (
                    ModelMessage(role=Role.USER, content=example.user),
                    ModelMessage(role=Role.ASSISTANT, content=example.assistant),
                )
            )
        messages.append(ModelMessage(role=Role.USER, content=rendered.user))
        return PreparedTriagePrompt(metadata=rendered.metadata, messages=tuple(messages))

    @staticmethod
    def _ticket_text(ticket: SupportTicket) -> str:
        fields = [f"Subject: {ticket.subject}", f"Message: {ticket.message}"]
        if ticket.order_id is not None:
            fields.append(f"Order ID: {ticket.order_id}")
        return "\n".join(fields)

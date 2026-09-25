"""FastAPI dependency wiring for the support workflow."""

from collections.abc import AsyncIterator
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from fastapi import Depends, HTTPException, status
from openai import AsyncOpenAI

from support_prompt_lab.application.draft import (
    ResponseDraftPromptBuilder,
    ResponseDraftStage,
)
from support_prompt_lab.application.escalation import EscalationDecider
from support_prompt_lab.application.injection import (
    InjectionDetectionPromptBuilder,
    InjectionDetectionStage,
)
from support_prompt_lab.application.output_security import LeakageProtectedLLMClient
from support_prompt_lab.application.policy import PolicyDecisionStage, PolicyPromptBuilder
from support_prompt_lab.application.policy_consensus import PolicyConsensusStage
from support_prompt_lab.application.policy_voting import PolicyDecisionVoter
from support_prompt_lab.application.ports import LLMClient
from support_prompt_lab.application.review import (
    ResponseReviewPromptBuilder,
    ResponseReviewStage,
)
from support_prompt_lab.application.triage import TriagePromptBuilder, TriageStage
from support_prompt_lab.application.workflow import SupportWorkflow
from support_prompt_lab.config import Settings, get_settings
from support_prompt_lab.infrastructure import OpenAILLMClient
from support_prompt_lab.prompts import PromptRegistry

_PROMPT_ROOT = Path(__file__).resolve().parents[3] / "prompts"
_UNAVAILABLE_DETAIL = "language model provider is not configured"


@lru_cache
def get_prompt_registry() -> PromptRegistry:
    """Load the immutable prompt library once per API process."""

    return PromptRegistry(_PROMPT_ROOT)


async def get_llm_client(
    settings: Annotated[Settings, Depends(get_settings)],
) -> AsyncIterator[LLMClient]:
    """Return the configured live language-model adapter."""

    if settings.openai_api_key is None or not settings.openai_api_key.get_secret_value().strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_UNAVAILABLE_DETAIL,
        )
    async with AsyncOpenAI(api_key=settings.openai_api_key.get_secret_value()) as client:
        yield OpenAILLMClient(client)


def get_support_workflow(
    settings: Annotated[Settings, Depends(get_settings)],
    llm_client: Annotated[LLMClient, Depends(get_llm_client)],
    registry: Annotated[PromptRegistry, Depends(get_prompt_registry)],
) -> SupportWorkflow:
    """Construct the workflow from runtime configuration and shared adapters."""

    if settings.openai_model is None or not settings.openai_model.strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=_UNAVAILABLE_DETAIL,
        )
    model = settings.openai_model.strip()
    protected_client = LeakageProtectedLLMClient(llm_client)
    return SupportWorkflow(
        injection_detection_stage=InjectionDetectionStage(
            InjectionDetectionPromptBuilder(registry),
            protected_client,
            model,
        ),
        triage_stage=TriageStage(TriagePromptBuilder(registry), protected_client, model),
        policy_stage=PolicyConsensusStage(
            policy_stage=PolicyDecisionStage(
                PolicyPromptBuilder(registry),
                protected_client,
                model,
            ),
            voter=PolicyDecisionVoter(),
            sample_count=settings.policy_decision_sample_count,
        ),
        escalation_decider=EscalationDecider(),
        draft_stage=ResponseDraftStage(
            ResponseDraftPromptBuilder(registry), protected_client, model
        ),
        review_stage=ResponseReviewStage(
            ResponseReviewPromptBuilder(registry), protected_client, model
        ),
        default_triage_strategy=settings.triage_prompt_strategy,
    )

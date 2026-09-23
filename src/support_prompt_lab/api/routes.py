"""Ticket-analysis HTTP routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from support_prompt_lab.api.dependencies import get_support_workflow
from support_prompt_lab.api.schemas import (
    AnalyzeTicketRequest,
    AnalyzeTicketResponse,
    WorkflowErrorDetail,
    WorkflowErrorResponse,
)
from support_prompt_lab.application.errors import ApplicationError, WorkflowErrorCode
from support_prompt_lab.application.workflow import SupportWorkflow
from support_prompt_lab.infrastructure import LLMProviderError
from support_prompt_lab.prompts.errors import PromptNotFoundError

router = APIRouter(prefix="/v1/tickets", tags=["tickets"])


@router.post(
    "/analyze",
    response_model=AnalyzeTicketResponse,
    responses={
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "Request or prompt selection is invalid"
        },
        status.HTTP_502_BAD_GATEWAY: {
            "description": "Support workflow failed",
            "model": WorkflowErrorResponse,
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {"description": "Language model provider unavailable"},
    },
)
async def analyze_ticket(
    request: AnalyzeTicketRequest,
    workflow: Annotated[SupportWorkflow, Depends(get_support_workflow)],
) -> AnalyzeTicketResponse:
    """Analyze a fictional support ticket through the complete prompt workflow."""

    selection = request.triage_prompt
    try:
        execution = await workflow.analyze(
            request.ticket,
            request.policies,
            triage_version=selection.version if selection is not None else None,
            triage_strategy=selection.strategy if selection is not None else None,
        )
    except PromptNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="requested prompt selection is unavailable",
        ) from error
    except ApplicationError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=WorkflowErrorDetail(
                message="support workflow failed",
                code=error.error_code,
            ).model_dump(mode="json"),
        ) from error
    except LLMProviderError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=WorkflowErrorDetail(
                message="support workflow failed",
                code=WorkflowErrorCode.MODEL_PROVIDER_FAILED,
            ).model_dump(mode="json"),
        ) from error
    return AnalyzeTicketResponse.from_execution(request.ticket, execution)

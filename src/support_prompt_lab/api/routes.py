"""Ticket-analysis HTTP routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from support_prompt_lab.api.dependencies import get_support_workflow
from support_prompt_lab.api.schemas import AnalyzeTicketRequest, AnalyzeTicketResponse
from support_prompt_lab.application.errors import ApplicationError
from support_prompt_lab.application.workflow import SupportWorkflow
from support_prompt_lab.infrastructure import LLMProviderError

router = APIRouter(prefix="/v1/tickets", tags=["tickets"])


@router.post(
    "/analyze",
    response_model=AnalyzeTicketResponse,
    responses={
        status.HTTP_502_BAD_GATEWAY: {"description": "Support workflow failed"},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"description": "Language model provider unavailable"},
    },
)
async def analyze_ticket(
    request: AnalyzeTicketRequest,
    workflow: Annotated[SupportWorkflow, Depends(get_support_workflow)],
) -> AnalyzeTicketResponse:
    """Analyze a fictional support ticket through the complete prompt workflow."""

    try:
        execution = await workflow.analyze(request.ticket, request.policies)
    except (ApplicationError, LLMProviderError) as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="support workflow failed",
        ) from error
    return AnalyzeTicketResponse.from_execution(request.ticket, execution)

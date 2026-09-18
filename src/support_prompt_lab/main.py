from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from support_prompt_lab.database import get_database_session


class HealthResponse(BaseModel):
    status: str


app = FastAPI(
    title="SupportPrompt Lab",
    version="0.1.0",
    description="A production-style prompt engineering service for support tickets.",
)


@app.get("/health", response_model=HealthResponse, tags=["operations"])
async def health() -> HealthResponse:
    """Report that the API process is serving requests."""

    return HealthResponse(status="ok")


@app.get(
    "/ready",
    response_model=HealthResponse,
    responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"description": "Database unavailable"}},
    tags=["operations"],
)
async def readiness(
    session: Annotated[AsyncSession, Depends(get_database_session)],
) -> HealthResponse:
    """Report whether the API can reach its required database dependency."""

    try:
        await session.execute(text("SELECT 1"))
    except SQLAlchemyError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database unavailable",
        ) from error

    return HealthResponse(status="ready")

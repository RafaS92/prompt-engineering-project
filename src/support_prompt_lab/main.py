from fastapi import FastAPI
from pydantic import BaseModel


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

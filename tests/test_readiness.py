from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from support_prompt_lab.database import get_database_session
from support_prompt_lab.main import app


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


async def request_readiness(session: AsyncMock) -> tuple[int, dict[str, str]]:
    async def override_database_session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_database_session] = override_database_session
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            response = await client.get("/ready")
    finally:
        app.dependency_overrides.clear()

    return response.status_code, response.json()


@pytest.mark.anyio
async def test_readiness_returns_ready_when_database_responds() -> None:
    session = AsyncMock(spec=AsyncSession)

    response_status, body = await request_readiness(session)

    assert response_status == 200
    assert body == {"status": "ready"}
    session.execute.assert_awaited_once()


@pytest.mark.anyio
async def test_readiness_returns_503_when_database_is_unavailable() -> None:
    session = AsyncMock(spec=AsyncSession)
    session.execute.side_effect = OperationalError("SELECT 1", {}, Exception("offline"))

    response_status, body = await request_readiness(session)

    assert response_status == 503
    assert body == {"detail": "database unavailable"}

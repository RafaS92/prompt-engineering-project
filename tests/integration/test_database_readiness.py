import os

import pytest
from httpx import ASGITransport, AsyncClient

from support_prompt_lab.main import app

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_DATABASE_INTEGRATION_TESTS") != "1",
        reason="set RUN_DATABASE_INTEGRATION_TESTS=1 to test a live PostgreSQL database",
    ),
]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_readiness_against_postgresql() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}

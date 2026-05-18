import pytest
from httpx import AsyncClient, ASGITransport

@pytest.fixture
async def client():
    from app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

async def test_docs_available(client):
    resp = await client.get("/docs")
    assert resp.status_code == 200

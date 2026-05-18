import pytest, json
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from unittest.mock import patch, AsyncMock
from app.db.models import Base
from app.db.database import get_db

TEST_DB = "sqlite+aiosqlite:///:memory:"

@pytest.fixture
async def client():
    engine = create_async_engine(TEST_DB)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async def override():
        async with Session() as s:
            yield s
    with patch("app.db.database.create_tables", new_callable=AsyncMock):
        from app.main import app
        app.dependency_overrides[get_db] = override
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            await ac.post("/auth/register", json={"email": "c@t.com", "password": "pw"})
            r = await ac.post("/auth/login", json={"email": "c@t.com", "password": "pw"})
            ac.headers.update({"Authorization": f"Bearer {r.json()['access_token']}"})
            rp = await ac.post("/projects", json={"name": "P"})
            ac._pid = rp.json()["id"]
            yield ac
        app.dependency_overrides.clear()
    await engine.dispose()

async def test_create_conversation(client):
    resp = await client.post(f"/projects/{client._pid}/conversations", json={"title": "탐색 1"})
    assert resp.status_code == 201
    assert resp.json()["title"] == "탐색 1"

async def test_list_conversations(client):
    await client.post(f"/projects/{client._pid}/conversations", json={})
    await client.post(f"/projects/{client._pid}/conversations", json={})
    resp = await client.get(f"/projects/{client._pid}/conversations")
    assert resp.status_code == 200
    assert len(resp.json()) >= 2

async def test_list_messages_empty(client):
    r = await client.post(f"/projects/{client._pid}/conversations", json={})
    cid = r.json()["id"]
    resp = await client.get(f"/conversations/{cid}/messages")
    assert resp.status_code == 200
    assert resp.json() == []

async def test_chat_endpoint_sse_search(client):
    r = await client.post(f"/projects/{client._pid}/conversations", json={})
    cid = r.json()["id"]

    async def fake_pipeline(*a, **kw):
        yield 'data: {"type": "cards", "content": []}\n\n'
        yield 'data: {"type": "done"}\n\n'

    with patch("app.conversations.router.run_pipeline", side_effect=fake_pipeline):
        resp = await client.post(f"/conversations/{cid}/chat",
                                 json={"message": "AI 개발 찾아줘"})
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]

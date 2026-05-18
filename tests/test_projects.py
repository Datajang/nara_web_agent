import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from unittest.mock import patch, AsyncMock
from app.db.models import Base
from app.db.database import get_db

TEST_DB = "sqlite+aiosqlite:///:memory:"

@pytest.fixture
async def authed_client():
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
            await ac.post("/auth/register", json={"email": "p@t.com", "password": "pw"})
            r = await ac.post("/auth/login", json={"email": "p@t.com", "password": "pw"})
            ac.headers.update({"Authorization": f"Bearer {r.json()['access_token']}"})
            yield ac
        app.dependency_overrides.clear()
    await engine.dispose()

async def test_create_project(authed_client):
    resp = await authed_client.post("/projects", json={"name": "AI 탐색", "department_profile": "{\"dept\": \"IT\"}"})
    assert resp.status_code == 201
    assert resp.json()["name"] == "AI 탐색"

async def test_list_projects(authed_client):
    await authed_client.post("/projects", json={"name": "P1"})
    await authed_client.post("/projects", json={"name": "P2"})
    resp = await authed_client.get("/projects")
    assert resp.status_code == 200
    assert len(resp.json()) >= 2

async def test_update_project(authed_client):
    r = await authed_client.post("/projects", json={"name": "Old"})
    pid = r.json()["id"]
    resp = await authed_client.put(f"/projects/{pid}", json={"name": "New"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "New"

async def test_delete_project(authed_client):
    r = await authed_client.post("/projects", json={"name": "Del"})
    pid = r.json()["id"]
    resp = await authed_client.delete(f"/projects/{pid}")
    assert resp.status_code == 204

async def test_cannot_access_other_users_project(authed_client):
    r = await authed_client.post("/projects", json={"name": "Mine"})
    pid = r.json()["id"]
    from app.main import app
    from app.db.database import get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac2:
        await ac2.post("/auth/register", json={"email": "other@t.com", "password": "pw"})
        r2 = await ac2.post("/auth/login", json={"email": "other@t.com", "password": "pw"})
        ac2.headers.update({"Authorization": f"Bearer {r2.json()['access_token']}"})
        resp = await ac2.get(f"/projects/{pid}")
        assert resp.status_code == 404

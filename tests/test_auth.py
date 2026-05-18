import pytest
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
            yield ac
        app.dependency_overrides.clear()
    await engine.dispose()

async def test_register(client):
    resp = await client.post("/auth/register", json={"email": "u@t.com", "password": "pass123"})
    assert resp.status_code == 201
    assert "user_id" in resp.json()

async def test_login(client):
    await client.post("/auth/register", json={"email": "u2@t.com", "password": "pass123"})
    resp = await client.post("/auth/login", json={"email": "u2@t.com", "password": "pass123"})
    assert resp.status_code == 200
    assert "access_token" in resp.json()

async def test_login_wrong_password(client):
    await client.post("/auth/register", json={"email": "u3@t.com", "password": "correct"})
    resp = await client.post("/auth/login", json={"email": "u3@t.com", "password": "wrong"})
    assert resp.status_code == 401

async def test_register_duplicate_email(client):
    await client.post("/auth/register", json={"email": "dup@t.com", "password": "p"})
    resp = await client.post("/auth/register", json={"email": "dup@t.com", "password": "p"})
    assert resp.status_code == 409

async def test_protected_route_requires_token(client):
    resp = await client.get("/projects")
    assert resp.status_code == 401

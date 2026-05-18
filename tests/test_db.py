import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.db.models import Base, User, Project, Conversation, Message, BookmarkedBid

TEST_DB = "sqlite+aiosqlite:///:memory:"

@pytest.fixture
async def session():
    engine = create_async_engine(TEST_DB)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as s:
        yield s
    await engine.dispose()

async def test_create_user(session):
    u = User(email="a@b.com", password_hash="hashed")
    session.add(u)
    await session.commit()
    await session.refresh(u)
    assert u.id is not None

async def test_cascade_delete_project(session):
    u = User(email="c@d.com", password_hash="x")
    session.add(u)
    await session.commit()
    p = Project(user_id=u.id, name="P1")
    session.add(p)
    await session.commit()
    conv = Conversation(project_id=p.id, title="C1")
    session.add(conv)
    await session.commit()
    await session.delete(p)
    await session.commit()
    result = await session.get(Conversation, conv.id)
    assert result is None

async def test_message_step_values(session):
    u = User(email="e@f.com", password_hash="x")
    session.add(u)
    await session.commit()
    p = Project(user_id=u.id, name="P")
    session.add(p)
    await session.commit()
    c = Conversation(project_id=p.id)
    session.add(c)
    await session.commit()
    m = Message(conversation_id=c.id, role="assistant", content="hi", step="analyze")
    session.add(m)
    await session.commit()
    await session.refresh(m)
    assert m.step == "analyze"

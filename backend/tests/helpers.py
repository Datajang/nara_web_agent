"""테스트 공용 도우미: 실제 코드 경로(mapper → upsert)로 공고를 넣는다."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select

from app.collector.upsert import upsert_bids
from app.db.models import Bid
from app.deps import Deps
from app.g2b.mapper import to_record


async def seed(deps: Deps, source: str, *items: dict[str, Any]) -> list[int]:
    records = [to_record(source, it) for it in items]
    async with deps.db.transaction() as s:
        await upsert_bids(s, records)
    async with deps.db.session() as s:
        keys = [r.bid_key for r in records]
        rows = (await s.execute(select(Bid.bid_key, Bid.id).where(Bid.bid_key.in_(keys)))).all()
    ids = dict(rows)
    return [ids[k] for k in keys]


# ---------- P2: 인증 헬퍼 ----------

PASSWORD = "correct-horse-battery"


def last_token(mailer: Any, to: str) -> str:
    """메모리 메일함에서 그 주소로 간 마지막 메일의 token 값."""
    for mail in reversed(mailer.outbox):
        if mail.to == to:
            m = re.search(r"token=([A-Za-z0-9_\-]+)", mail.body)
            assert m, f"토큰 없는 메일: {mail.subject}"
            return m.group(1)
    raise AssertionError(f"{to}로 간 메일 없음")


async def create_user(
    db: Any,
    email: str,
    password: str = PASSWORD,
    *,
    status: str = "active",
    role: str = "member",
    password_hash: str | None = None,
) -> int:
    from sqlalchemy import insert

    from app.auth.passwords import hash_password
    from app.db.models.personal import User

    async with db.transaction() as s:
        uid = await s.scalar(
            insert(User)
            .values(
                email=email,
                password_hash=password_hash or hash_password(password),
                display_name=email.split("@")[0],
                role=role,
                status=status,
            )
            .returning(User.id)
        )
    return int(uid)


async def login(client: Any, email: str, password: str = PASSWORD) -> Any:
    return await client.post("/api/v1/auth/login", json={"email": email, "password": password})


async def admin_client(api: Any, email: str = "admin@corp.example") -> Any:
    """로그인된 관리자 클라이언트(호출자가 aclose)."""
    await create_user(api.db, email, role="admin")
    c = api.client()
    r = await login(c, email)
    assert r.status_code == 200, r.text
    return c

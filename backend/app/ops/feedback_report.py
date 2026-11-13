"""파일럿 주간 피드백 보고 (docs/ops/OWNER_GUIDE.md 9단계, SPEC §12.7).

    sudo -u nara env NARA_ENV_FILE=/etc/nara/nara.env /opt/nara/venv/bin/python \\
      -m app.ops.feedback_report --days 7

집계 수와 공개 정보(공고 번호·제목)만 쓴다. 사용자 신원과 의견 본문은 넣지 않는다
(§9: 관리자도 다른 사용자의 본문을 볼 수 없다).
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import Analysis, Bid, Feedback
from app.db.session import Database
from app.deps import utcnow
from app.llm.versions import bid_ref
from app.usage.stats import feedback_counts

KST = timezone(timedelta(hours=9))
TARGETS = {"analysis": "분석", "assistant_message": "어시스턴트", "search_run": "검색"}
REASONS = {  # 화면 문구와 같게 (frontend copy.feedback.reasons)
    "wrong": "사실과 달라요",
    "missing": "빠진 내용이 있어요",
    "irrelevant": "관련 없는 내용이에요",
    "too_long": "너무 길어요",
    "other": "기타",
}


async def build_report(s: AsyncSession, since: datetime, until: datetime) -> str:
    counts = await feedback_counts(s, since, until)
    span = f"{since.astimezone(KST):%m-%d} ~ {until.astimezone(KST):%m-%d}"
    lines = [f"# 피드백 보고 ({span}, KST)", ""]
    if not counts:
        return "\n".join([*lines, "이 기간에는 피드백이 없어요."])

    lines.append("## 대상별")
    for t, label in TARGETS.items():
        up = sum(c.count for c in counts if c.target_type == t and c.rating == 1)
        down = sum(c.count for c in counts if c.target_type == t and c.rating == -1)
        if up or down:
            lines.append(f"- {label}: 👍 {up} · 👎 {down} (👎 {round(100 * down / (up + down))}%)")

    reasons: dict[str, int] = {}
    for c in counts:
        if c.rating == -1:
            key = c.reason or "none"
            reasons[key] = reasons.get(key, 0) + c.count
    lines += ["", "## 👎 사유 상위 3"]
    top = sorted(reasons.items(), key=lambda kv: (-kv[1], kv[0]))[:3]
    for i, (code, n) in enumerate(top, start=1):
        lines.append(f"{i}. {code}({REASONS.get(code, '사유 없음')}) {n}건")

    downs = func.count().label("downs")
    stmt = (
        select(Bid.id, Bid.title, downs, func.array_agg(func.distinct(Feedback.reason)))
        .join(Analysis, Analysis.id == Feedback.target_id)
        .join(Bid, Bid.id == Analysis.bid_id)
        .where(
            Feedback.target_type == "analysis",
            Feedback.rating == -1,
            Feedback.created_at >= since,
            Feedback.created_at < until,
        )
        .group_by(Bid.id, Bid.title)
        .order_by(downs.desc(), Bid.id)
        .limit(10)
    )
    rows = (await s.execute(stmt)).all()
    if rows:
        lines += ["", "## 👎 많이 받은 공고 (분석, 최대 10건)"]
        for bid_id, title, cnt, why in rows:
            codes = ", ".join(sorted(r for r in why if r)) or "사유 없음"
            lines.append(f"- {bid_ref(bid_id)} {title} — 👎 {cnt} ({codes})")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m app.ops.feedback_report")
    p.add_argument("--days", type=int, default=7)
    args = p.parse_args(argv)

    async def run() -> str:
        db = Database(get_settings().database_url, pool_size=1, lock_pool_size=1)
        try:
            async with db.session() as s:
                now = utcnow()
                return await build_report(s, now - timedelta(days=args.days), now)
        finally:
            await db.dispose()

    print(asyncio.run(run()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

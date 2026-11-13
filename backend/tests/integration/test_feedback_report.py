"""파일럿 주간 피드백 보고 (docs/ops/OWNER_GUIDE.md 9단계, SPEC §12.7).

집계 수와 공개 정보(공고 제목)만 보여 준다. 사용자 신원·의견 본문은 넣지 않는다
(§9 관리자도 개인 본문 열람 불가).
"""

from datetime import timedelta

from app.ops.feedback_report import build_report
from tests.conftest import NOW
from tests.fakes.g2b import regular_item
from tests.helpers import make_profile, member, seed, sse


async def _analysis(full_api, client, no: str, title: str) -> int:
    (bid_id,) = await seed(full_api.ctx.deps, "regular", regular_item(no, NOW, title=title))
    pid = await make_profile(client)
    events = await sse(client, f"/api/v1/bids/b{bid_id}/analyze", {"profile_id": pid})
    return events[-2]["analysis_id"]


async def test_weekly_report_counts_reasons_and_worst_bids_without_personal_text(full_api):
    a = await member(full_api, "pilot-a@corp.example")
    b = await member(full_api, "pilot-b@corp.example")
    try:
        bad = await _analysis(full_api, a, "R26BK79000001", "클라우드 전환 컨설팅")
        good = await _analysis(full_api, b, "R26BK79000002", "AI 데이터 플랫폼 고도화")
        down = {"target_type": "analysis", "rating": -1, "reason": "wrong"}
        await a.post(
            "/api/v1/feedback", json={**down, "target_id": bad, "comment": "예산 틀림 비밀메모"}
        )
        await a.post("/api/v1/feedback", json={**down, "target_id": bad, "reason": "missing"})
        await b.post(
            "/api/v1/feedback", json={"target_type": "analysis", "target_id": good, "rating": 1}
        )
    finally:
        await a.aclose()
        await b.aclose()

    async with full_api.db.session() as s:
        text = await build_report(s, NOW - timedelta(days=7), NOW + timedelta(days=1))
    assert "👍 1" in text and "👎 2" in text
    assert "wrong(사실과 달라요) 1건" in text and "missing(빠진 내용이 있어요) 1건" in text
    assert (
        "클라우드 전환 컨설팅" in text and "AI 데이터 플랫폼 고도화" not in text
    )  # 👎 받은 공고만
    for private in ("비밀메모", "pilot-a", "pilot-b", "corp.example"):
        assert private not in text


async def test_empty_week_says_so(full_api):
    async with full_api.db.session() as s:
        text = await build_report(s, NOW - timedelta(days=7), NOW)
    assert "피드백이 없어요" in text

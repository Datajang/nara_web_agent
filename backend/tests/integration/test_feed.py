"""P6 관심 공고 (SPEC §13 P6 관심 공고 1~3). DB만 읽고 G2B·LLM을 부르지 않는다."""

from datetime import timedelta

from tests.conftest import NOW
from tests.fakes.g2b import kst_str, regular_item
from tests.helpers import member, seed

F = "/api/v1/feed"


def _bid(no: str, title: str, days_ago: int = 1, deadline_in: int = 10):
    notice = NOW - timedelta(days=days_ago)
    return regular_item(
        no, notice, title=title, deadline=kst_str(NOW + timedelta(days=deadline_in))
    )


async def _seed(full_api):
    await seed(
        full_api.ctx.deps,
        "regular",
        _bid("R26BK74000001", "AI 플랫폼 구축 사업", deadline_in=9),
        _bid("R26BK74000002", "공공 데이터 품질 관리", deadline_in=3),
        _bid("R26BK74000003", "클라우드 전환 컨설팅", deadline_in=5),
        _bid("R26BK74000004", "AI 기반 교통 분석"),  # 'AI 플랫폼'은 두 단어 모두 있어야 맞음
        _bid("R26BK74000005", "도로 포장 공사"),  # 관련 없음
        _bid("R26BK74000006", "AI 플랫폼 고도화", deadline_in=-1),  # 마감 지남
        _bid("R26BK74000007", "데이터 센터 이전", days_ago=40),  # 30일보다 오래됨
    )


async def test_feed_matches_team_and_personal_keywords_without_external_calls(
    full_api, fake_g2b, fake_llm
):
    await _seed(full_api)
    c = await member(full_api, "feed@corp.example")
    await c.post("/api/v1/teams", json={"name": "팀"})
    await c.post("/api/v1/profiles", json={"name": "팀", "keywords": ["클라우드"], "scope": "team"})
    await c.patch("/api/v1/me", json={"interest_keywords": ["AI 플랫폼", "데이터"]})
    calls_before = fake_g2b.calls
    r = (await c.get(F)).json()
    await c.aclose()
    assert r["keywords"] == ["클라우드", "AI 플랫폼", "데이터"]  # 팀 키워드 먼저
    assert r["needs_keywords"] is False and r["total"] == 3
    got = [(it["title"], it["matched_keywords"]) for it in r["items"]]
    assert got == [  # 마감 임박 순
        ("공공 데이터 품질 관리", ["데이터"]),
        ("클라우드 전환 컨설팅", ["클라우드"]),
        ("AI 플랫폼 구축 사업", ["AI 플랫폼"]),
    ]
    assert fake_g2b.calls == calls_before and sum(fake_llm.calls.values()) == 0


async def test_feed_asks_for_keywords_below_three(full_api):
    await _seed(full_api)
    c = await member(full_api, "few@corp.example")
    await c.patch("/api/v1/me", json={"interest_keywords": ["AI 플랫폼", "데이터"]})
    r = (await c.get(F)).json()
    await c.aclose()
    assert r == {
        "keywords": ["AI 플랫폼", "데이터"],
        "needs_keywords": True,
        "total": 0,
        "items": [],
    }


async def test_feed_pages(full_api):
    await seed(
        full_api.ctx.deps,
        "regular",
        *[_bid(f"R26BK7500{i:04d}", f"AI 사업 {i}", deadline_in=i + 1) for i in range(5)],
    )
    c = await member(full_api, "page@corp.example")
    await c.patch("/api/v1/me", json={"interest_keywords": ["AI", "검색", "데이터"]})
    first = (await c.get(F, params={"limit": 2})).json()
    rest = (await c.get(F, params={"limit": 2, "offset": 2})).json()
    await c.aclose()
    assert first["total"] == 5
    assert [it["title"] for it in first["items"] + rest["items"]] == [
        f"AI 사업 {i}" for i in range(4)
    ]

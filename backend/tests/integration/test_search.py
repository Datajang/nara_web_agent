"""DB-first 검색 (SPEC §5.4, §5.9-4·5, 완료 게이트: 두 번째 검색 g2b_calls 0)."""

from datetime import timedelta

from sqlalchemy import select, text

from app.collector import runner
from app.db.models import BidAward, BidOpeningStatus, SearchRun, SearchRunItem, UsageLog, User
from app.g2b.client import G2BClient
from app.search.query import SearchQuery
from app.search.service import search_bids
from app.usage.budget import DbCallBudget
from tests.conftest import NOW, TEST_KEYS
from tests.fakes.g2b import regular_item


async def _user(deps) -> int:
    async with deps.db.transaction() as s:
        u = User(email="a@example.com", password_hash="x", status="active")
        s.add(u)
        await s.flush()
        return u.id


def _items():
    return [
        regular_item(
            "R26BK60000001", NOW - timedelta(days=2), title="AI 기반 민원 분석 시스템 구축"
        ),
        regular_item("R26BK60000002", NOW - timedelta(days=3), title="클라우드 전환 컨설팅"),
        regular_item(
            "R26BK60000003", NOW - timedelta(days=4), title="AI 학습 데이터 구축", deadline=""
        ),
        regular_item("R26BK60000004", NOW - timedelta(days=20), title="지난 AI 공고"),
    ]


async def test_search_inside_coverage_makes_no_g2b_calls(deps, fake_g2b):
    """§5.9-4"""
    fake_g2b.add("regular", *_items())
    await runner.backfill(deps, "regular", days=30)
    before = fake_g2b.calls
    res = await search_bids(
        deps, await _user(deps), SearchQuery(keywords=["AI"], days=7, source="regular")
    )
    assert fake_g2b.calls == before
    assert res.cache_hit is True and res.incomplete is False
    assert [b.bid_no for b in res.items] == ["R26BK60000001", "R26BK60000003"]


async def test_outside_coverage_fills_then_second_search_is_free(deps, fake_g2b):
    """§5.9-5 + 완료 게이트: 같은 검색을 두 번 하면 두 번째의 usage_logs.g2b_calls가 0."""
    fake_g2b.add("regular", *_items())
    uid = await _user(deps)
    q = SearchQuery(keywords=["AI"], days=7, source="regular")
    first = await search_bids(deps, uid, q)
    second = await search_bids(deps, uid, q)
    assert first.cache_hit is False and first.g2b_calls > 0
    assert second.cache_hit is True and second.g2b_calls == 0
    async with deps.db.session() as s:
        logs = (await s.execute(select(UsageLog).order_by(UsageLog.id))).scalars().all()
    assert [lg.g2b_calls for lg in logs] == [first.g2b_calls, 0]
    assert logs[1].cache == {"bids_db": True}


async def test_snapshot_saved_for_history(deps, fake_g2b):
    fake_g2b.add("regular", *_items())
    uid = await _user(deps)
    res = await search_bids(deps, uid, SearchQuery(keywords=["AI"], days=7, source="regular"))
    async with deps.db.session() as s:
        run = await s.get(SearchRun, res.run_id)
        items = (
            (
                await s.execute(
                    select(SearchRunItem)
                    .where(SearchRunItem.run_id == res.run_id)
                    .order_by(SearchRunItem.rank)
                )
            )
            .scalars()
            .all()
        )
    assert run.user_id == uid and run.result_count == 2 and run.data_as_of is not None
    assert [i.bid_id for i in items] == [b.id for b in res.items]


async def test_open_filter_treats_null_deadline_as_open(deps, fake_g2b):
    """§4: deadline_at IS NULL은 진행중."""
    past = regular_item(
        "R26BK60000009",
        NOW - timedelta(days=2),
        title="AI 마감된 공고",
        deadline="2026-11-09 10:00:00",
    )
    fake_g2b.add("regular", *_items(), past)
    res = await search_bids(
        deps, None, SearchQuery(keywords=["AI"], days=7, source="regular", status="open")
    )
    assert "R26BK60000009" not in {b.bid_no for b in res.items}
    assert "R26BK60000003" in {b.bid_no for b in res.items}


async def test_budget_exceeded_returns_db_results_only(deps, fake_g2b):
    """§13.3 게이트: 일일 호출 예산 초과 시 새 호출을 멈추고 DB 결과만 돌려준다."""
    fake_g2b.add("regular", *_items())
    deps.g2b = G2BClient(
        fake_g2b.http_client(),
        TEST_KEYS,
        retry_delays=(0, 0, 0),
        budget=DbCallBudget(deps.db, limit=0),
    )
    res = await search_bids(deps, None, SearchQuery(keywords=["AI"], days=7, source="regular"))
    assert fake_g2b.calls == 0
    assert res.incomplete is True and res.items == []


async def test_fill_is_capped_at_31_days(deps, fake_g2b):
    fake_g2b.add("regular", *_items())
    res = await search_bids(deps, None, SearchQuery(keywords=["AI"], days=60, source="regular"))
    assert res.incomplete is True


async def test_korean_trigram_index_is_usable(deps):
    """§5.4 [미확인]: 한글 3글자 이상 ILIKE가 gin_trgm 인덱스를 탈 수 있는지 EXPLAIN으로 확인."""
    async with deps.db.transaction() as s:
        await s.execute(text("SET LOCAL enable_seqscan = off"))
        plan = "\n".join(
            (
                await s.execute(text("EXPLAIN SELECT id FROM bids WHERE title ILIKE '%민원분석%'"))
            ).scalars()
        )
    assert "ix_bids_title_trgm" in plan


async def test_title_search_ignores_spacing_and_allows_commas_and_long_titles(deps, fake_g2b):
    """2026-11-16 사용자 요청: 공고명(제목)으로도 찾기. 제목 일부나 전체를 붙여 넣으면
    띄어쓰기와 상관없이 그 순서대로 들어 있는 공고를 찾는다(쉼표·50자 넘는 제목도)."""
    long_title = (
        "국가하천(낙동강, 내성천) 불법행위 단속 및 하천 환경 정비를 위한 통합 관리 용역 2단계 사업"
    )
    fake_g2b.add(
        "regular",
        regular_item(
            "R26BK60000011", NOW - timedelta(days=1), title="AI 기반 생육지원 데이터센터 구축"
        ),
        regular_item("R26BK60000012", NOW - timedelta(days=1), title="데이터센터 생육지원 AI 기반"),
        regular_item("R26BK60000013", NOW - timedelta(days=1), title=long_title),
    )
    await runner.backfill(deps, "regular", days=30)
    uid = await _user(deps)

    async def titles(**kw) -> list[str]:
        res = await search_bids(deps, uid, SearchQuery(days=7, source="regular", **kw))
        return [b.title for b in res.items]

    assert await titles(title="AI기반 생육지원  데이터센터") == ["AI 기반 생육지원 데이터센터 구축"]
    assert await titles(title=long_title) == [long_title]
    assert await titles(title="생육지원", keywords=["구축"]) == ["AI 기반 생육지원 데이터센터 구축"]


PAST = "2026-11-09 10:00:00"  # 마감 지남


def _status_items():
    def it(no, **kw):
        return regular_item(no, NOW - timedelta(days=2), title=f"AI {no}", **kw)

    return [
        it("R26BK61000001"),  # 진행중
        it("R26BK61000002", deadline=PAST),  # 마감 · 결과 대기
        it("R26BK61000003", deadline=PAST),  # 유찰
        it("R26BK61000004", deadline=PAST, ord="001"),  # 정정: 000 차수만 유찰 → 아님
        it("R26BK61000005", deadline=PAST),  # 분류 1 유찰 · 분류 2 개찰완료 → 아님
        it("R26BK61000006", deadline=PAST),  # 유찰 뒤 재입찰 001 개찰완료 → 아님
        it("R26BK61000007", deadline=PAST),  # 재입찰 000 뒤 001 유찰 → 유찰
        it("R26BK61000008", deadline=PAST),  # 유찰 행 + 낙찰 행 → 아님
        it("R26BK61000009", deadline=PAST, kind="취소공고"),  # 취소: 어디에도 없음
    ]


async def _seed_outcomes(deps):
    def st(no, status, ord_="000", clsfc="0", rbid="000"):
        return BidOpeningStatus(
            bid_ntce_no=no, bid_ntce_ord=ord_, bid_clsfc_no=clsfc, rbid_no=rbid, status=status
        )

    async with deps.db.transaction() as s:
        s.add_all(
            [
                st("R26BK61000003", "유찰"),
                st("R26BK61000004", "유찰", ord_="000"),
                st("R26BK61000005", "유찰", clsfc="1"),
                st("R26BK61000005", "개찰완료", clsfc="2"),
                st("R26BK61000006", "유찰", rbid="000"),
                st("R26BK61000006", "개찰완료", rbid="001"),
                st("R26BK61000007", "재입찰", rbid="000"),
                st("R26BK61000007", "유찰", rbid="001"),
                st("R26BK61000008", "유찰"),
                st("R26BK61000009", "유찰"),
                BidAward(
                    bid_ntce_no="R26BK61000008",
                    bid_ntce_ord="000",
                    bid_clsfc_no="0",
                    rbid_no="000",
                    title="t",
                    registered_at=NOW,
                ),
            ]
        )


async def _nos(deps, status):
    q = SearchQuery(keywords=["AI"], days=7, source="regular", status=status)
    res = await search_bids(deps, None, q)
    return {b.bid_no for b in res.items if b.bid_no.startswith("R26BK61")}, res


async def test_status_closed_and_failed(deps, fake_g2b):
    """마감 = 마감일 지남(결과 무관), 유찰 = 카드 배지 규칙(docs/BID_OUTCOME.md)."""
    fake_g2b.add("regular", *_status_items())
    await runner.backfill(deps, "regular", days=30)
    await _seed_outcomes(deps)
    closed, _ = await _nos(deps, "closed")
    assert closed == {f"R26BK6100000{i}" for i in range(2, 9)}
    failed, _ = await _nos(deps, "failed")
    assert failed == {"R26BK61000003", "R26BK61000007"}
    opened, _ = await _nos(deps, "open")
    assert opened == {"R26BK61000001"}


async def test_hidden_closed_counts_only_for_open(deps, fake_g2b):
    fake_g2b.add("regular", *_status_items())
    await runner.backfill(deps, "regular", days=30)
    _, res = await _nos(deps, "open")
    assert res.hidden_closed == 7  # 취소공고는 세지 않는다
    for status in ("all", "closed", "failed"):
        _, res = await _nos(deps, status)
        assert res.hidden_closed == 0

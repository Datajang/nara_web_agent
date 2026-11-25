"""G2B 클라이언트: 페이지네이션·재시도·오류 구분·키 마스킹·호출 예산 (SPEC §5.2, §5.9-6·10)."""

import json
import logging
from datetime import datetime, timedelta

import httpx
import pytest

from app.g2b.client import RESULT_WATCH_SOURCE, G2BBudgetExceeded, G2BClient, G2BError
from app.usage.budget import DbCallBudget
from tests.conftest import NOW, TEST_KEYS
from tests.fakes.g2b import FIXTURES, FakeG2B, award_item, regular_item, status_item

DAY = (NOW - timedelta(days=1), NOW)


def _client(fake: FakeG2B, **kw) -> G2BClient:
    return G2BClient(fake.http_client(), TEST_KEYS, retry_delays=(0, 0, 0), **kw)


async def test_collects_every_page_when_total_exceeds_page_size():
    """§5.9-6: totalCount > numOfRows이면 모든 페이지를 수집 (v1 단일 페이지 버그 회귀)."""
    fake = FakeG2B()
    # 창의 끝(NOW)은 배타적이므로 NOW보다 이른 시각으로 만든다
    fake.add(
        "regular",
        *(regular_item(f"R26BK4{i:07d}", NOW - timedelta(minutes=i + 1)) for i in range(250)),
    )
    items = await _client(fake, page_size=100).fetch("regular", *DAY)
    assert len(items) == 250
    assert fake.calls == 3
    assert [r.url.params["pageNo"] for r in fake.requests] == ["1", "2", "3"]


async def test_zero_results_is_not_an_error():
    assert await _client(FakeG2B()).fetch("regular", *DAY) == []


async def test_retries_5xx_then_succeeds():
    fake = FakeG2B()
    fake.add("regular", regular_item("R26BK50000001", NOW - timedelta(hours=1)))
    fake.fail(httpx.Response(502), httpx.Response(503))
    assert len(await _client(fake).fetch("regular", *DAY)) == 1
    assert fake.calls == 3


async def test_gives_up_after_three_retries():
    fake = FakeG2B()
    fake.fail(*(httpx.Response(500) for _ in range(10)))
    with pytest.raises(G2BError):
        await _client(fake).fetch("regular", *DAY)
    assert fake.calls == 4  # 첫 시도 + 재시도 3회


@pytest.mark.parametrize("fixture", ["error_invalid_key.json", "error_period_too_long.json"])
async def test_api_error_shapes_raise_without_retry(fixture):
    """실제 오류 응답 2종(HTTP 403 키 오류, HTTP 200 resultCode=07)은 재시도 없이 G2BError."""
    status = 403 if "invalid_key" in fixture else 200
    fake = FakeG2B()
    fake.fail(
        httpx.Response(status, json=json.loads((FIXTURES / fixture).read_text(encoding="utf-8")))
    )
    with pytest.raises(G2BError):
        await _client(fake).fetch("regular", *DAY)
    assert fake.calls == 1


async def test_service_key_never_appears_in_errors_or_logs(caplog):
    """§5.9-10: 서비스키 문자열이 로그와 예외 메시지에 나타나지 않는다."""
    caplog.set_level(logging.DEBUG)

    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"connection failed for {request.url}")

    client = G2BClient(
        httpx.AsyncClient(transport=httpx.MockTransport(boom)), TEST_KEYS, retry_delays=(0, 0, 0)
    )
    with pytest.raises(G2BError) as exc:
        await client.fetch("regular", *DAY)
    text = str(exc.value) + repr(exc.value) + caplog.text
    assert "connection failed" in text
    for key in TEST_KEYS.values():
        assert key not in text


async def test_window_longer_than_15_days_is_split():
    fake = FakeG2B()
    await _client(fake).fetch("prespec", NOW - timedelta(days=40), NOW)
    assert fake.calls == 3


async def test_regular_v13_uses_02_service_and_seven_kst_dates():
    # 입찰공고 v1.3: BidPublicInfoService02 + 오퍼레이션 02, KST 날짜 8개면 07 (2026-11-24 probe)
    fake = FakeG2B()
    await _client(fake).fetch("regular", NOW - timedelta(days=40), NOW)
    assert fake.calls == 6  # KST 날짜 41개 → 7개씩
    for r in fake.requests:
        assert r.url.path.endswith("/BidPublicInfoService02/getBidPblancListInfoServcPPSSrch02")
        bgn, end = r.url.params["inqryBgnDt"][:8], r.url.params["inqryEndDt"][:8]
        days = (datetime.strptime(end, "%Y%m%d") - datetime.strptime(bgn, "%Y%m%d")).days
        assert days <= 6


async def test_budget_exceeded_stops_before_calling(db):
    fake = FakeG2B()
    client = _client(fake, budget=DbCallBudget(db, limit=0))
    with pytest.raises(G2BBudgetExceeded):
        await client.fetch("regular", *DAY)
    assert fake.calls == 0


# ---------- 결과 메일 감시용 호출 (2026-11-25, result-status-probe 결정 문서) ----------


async def test_award_by_notice_filters_number():
    """낙찰을 공고번호로 1회 조회(inqryDiv=4). 다른 공고 행은 버린다."""
    fake = FakeG2B()
    fake.add("awards", award_item("R26BK00000001", NOW), award_item("R26BK00000002", NOW))
    rows = await _client(fake).award_by_notice("R26BK00000001")
    assert [r["bidNtceNo"] for r in rows] == ["R26BK00000001"]
    p = fake.requests[0].url.params
    assert (p["inqryDiv"], p["bidNtceNo"]) == ("4", "R26BK00000001")


async def test_opening_status_parses_rows():
    """개찰결과(진행 상태)를 공고번호로 조회해 그 차수 행만 준다."""
    fake = FakeG2B()
    fake.add(
        "opening_status",
        status_item("R26BK00000001", "유찰", ord="000"),
        status_item("R26BK00000001", "개찰완료", ord="001"),
        status_item("R26BK00000009", "개찰완료"),
    )
    rows = await _client(fake).opening_status("R26BK00000001", "001")
    assert [(r["bidNtceOrd"], r["progrsDivCdNm"]) for r in rows] == [("001", "개찰완료")]
    p = fake.requests[0].url.params
    assert (p["inqryDiv"], p["bidNtceNo"]) == ("4", "R26BK00000001")


async def test_result_watch_budget_separate(db):
    """결과 감시 몫이 바닥나면 부르지 않는다. 낙찰 몫이 남아 있어도 마찬가지."""
    fake = FakeG2B()
    client = _client(
        fake,
        source_budgets={
            "awards": DbCallBudget(db, 100, sources=["awards"]),
            RESULT_WATCH_SOURCE: DbCallBudget(db, 0, sources=[RESULT_WATCH_SOURCE]),
        },
    )
    with pytest.raises(G2BBudgetExceeded):
        await client.award_by_notice("R26BK00000001")
    with pytest.raises(G2BBudgetExceeded):
        await client.opening_results("R26BK00000001", "000", source=RESULT_WATCH_SOURCE)
    assert fake.calls == 0

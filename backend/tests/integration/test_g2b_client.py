"""G2B 클라이언트: 페이지네이션·재시도·오류 구분·키 마스킹·호출 예산 (SPEC §5.2, §5.9-6·10)."""

import json
import logging
from datetime import timedelta

import httpx
import pytest

from app.g2b.client import G2BBudgetExceeded, G2BClient, G2BError
from app.usage.budget import DbCallBudget
from tests.conftest import NOW, TEST_KEYS
from tests.fakes.g2b import FIXTURES, FakeG2B, regular_item

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
    await _client(fake).fetch("regular", NOW - timedelta(days=40), NOW)
    assert fake.calls == 3


async def test_budget_exceeded_stops_before_calling(db):
    fake = FakeG2B()
    client = _client(fake, budget=DbCallBudget(db, limit=0))
    with pytest.raises(G2BBudgetExceeded):
        await client.fetch("regular", *DAY)
    assert fake.calls == 0

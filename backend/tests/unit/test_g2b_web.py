"""나라장터 웹 공고 상세의 제안서평가 일시 (2026-11-27, 결정 기록 2026-11-27-proposal-eval-date).

fixture는 실제 응답에서 필요한 키만 남겼다(담당자 정보 제외).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from app.g2b.web import EVAL_URL, EvalPlan, G2BWebClient, G2BWebError

FIX = Path(__file__).parents[1] / "fixtures" / "g2b_web"


def _client(handler) -> tuple[G2BWebClient, httpx.AsyncClient]:
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return G2BWebClient(http), http


def _fixture(name: str) -> dict:
    return json.loads((FIX / name).read_text(encoding="utf-8"))


async def test_eval_date_from_pps_evaluation():
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(200, json=_fixture("eval_pps.json"))

    web, http = _client(handler)
    plan = await web.eval_date("R26BK01824103", "000")
    await http.aclose()
    assert plan == EvalPlan(at=datetime(2026, 12, 2, 0, 30, tzinfo=UTC), host="조달청")
    assert seen[0].method == "POST" and str(seen[0].url) == EVAL_URL
    assert json.loads(seen[0].content) == {
        "dmItemMap": {"bidPbancNo": "R26BK01824103", "bidPbancOrd": "000"}
    }


async def test_demand_agency_evaluation_has_no_date():
    web, http = _client(lambda req: httpx.Response(200, json=_fixture("eval_dminst.json")))
    plan = await web.eval_date("R26BK01713815", "000")
    await http.aclose()
    assert plan == EvalPlan(at=None, host="수요기관")


async def test_falls_back_to_progress_table_row():
    """평가 단계 맵이 비어도 입찰진행정보 표의 '제안서평가' 시작일시를 쓴다."""
    body = _fixture("eval_pps.json")
    body["dmEvlStepMap"]["evlDt"] = None
    web, http = _client(lambda req: httpx.Response(200, json=body))
    plan = await web.eval_date("R26BK01824103", "000")
    await http.aclose()
    assert plan.at == datetime(2026, 12, 2, 0, 30, tzinfo=UTC)


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500, text="err"),
        httpx.Response(200, text="<html>시스템 접근 안내</html>"),
        httpx.Response(200, json={"ErrorCode": 9, "ErrorMsg": "오류"}),
    ],
)
async def test_bad_response_raises(response):
    web, http = _client(lambda req: response)
    with pytest.raises(G2BWebError):
        await web.eval_date("R26BK01824103", "000")
    await http.aclose()

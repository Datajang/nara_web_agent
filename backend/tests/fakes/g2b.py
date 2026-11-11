"""녹화본 기반 가짜 G2B 서버 (SPEC §12.2). 호출 수를 세고 실패를 주입할 수 있다.

실제 응답 모양(`tests/fixtures/g2b/*.json`)의 항목을 틀로 써서 날짜·번호만 바꾼 공고를 만든다.
조회 창(inqryBgnDt~inqryEndDt, KST 분 단위)과 numOfRows·pageNo를 실제 API처럼 처리한다.
"""

from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "g2b"
KST = timezone(timedelta(hours=9))
OPS = {
    "getBidPblancListInfoServcPPSSrch": "regular",
    "getPublicPrcureThngInfoServcPPSSrch": "prespec",
}
DATE_FIELD = {"regular": "bidNtceDt", "prespec": "rgstDt"}
TITLE_FIELD = {"regular": "bidNtceNm", "prespec": "prdctClsfcNoNm"}


def _template(name: str) -> dict[str, Any]:
    data = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    items = data["response"]["body"]["items"]
    return copy.deepcopy(items[0] if isinstance(items, list) else items["item"][0])


REGULAR_TEMPLATE = _template("regular_page1.json")
PRESPEC_TEMPLATE = _template("prespec_page1.json")


def kst_str(dt: datetime) -> str:
    return dt.astimezone(KST).strftime("%Y-%m-%d %H:%M:%S")


def regular_item(
    no: str,
    notice_at: datetime,
    *,
    ord: str = "000",
    title: str = "AI 기반 민원 분석 시스템 구축 용역",
    deadline: str | None = None,
    files: list[tuple[str, str]] | None = None,
    kind: str = "등록공고",
    budget: str | None = "100000000",
) -> dict[str, Any]:
    it = copy.deepcopy(REGULAR_TEMPLATE)
    for i in range(1, 11):
        it[f"ntceSpecDocUrl{i}"] = ""
        it[f"ntceSpecFileNm{i}"] = ""
    for i, (url, name) in enumerate(files or [], start=1):
        it[f"ntceSpecDocUrl{i}"] = url
        it[f"ntceSpecFileNm{i}"] = name
    it.update(
        bidNtceNo=no,
        bidNtceOrd=ord,
        bidNtceNm=title,
        bidNtceDt=kst_str(notice_at),
        bidClseDt=deadline if deadline is not None else kst_str(notice_at + timedelta(days=14)),
        ntceKindNm=kind,
        bdgtAmt=None,
        presmptPrce=budget,
        bfSpecRgstNo="",
        bidNtceDtlUrl=f"https://www.g2b.go.kr/link/PNPE027_01/single/?bidPbancNo={no}&bidPbancOrd={ord}",
    )
    return it


def prespec_item(
    reg_no: str, registered_at: datetime, *, title: str = "AI 플랫폼 구축"
) -> dict[str, Any]:
    it = copy.deepcopy(PRESPEC_TEMPLATE)
    for i in range(1, 6):
        it[f"specDocFileUrl{i}"] = ""
    it.update(
        bfSpecRgstNo=reg_no,
        prdctClsfcNoNm=title,
        rgstDt=kst_str(registered_at),
        rcptDt=kst_str(registered_at),
        opninRgstClseDt=kst_str(registered_at + timedelta(days=5)),
        asignBdgtAmt="50000000",
        specDocFileUrl1=f"https://www.g2b.go.kr/spec/{reg_no}.hwp",
    )
    return it


class FakeG2B:
    def __init__(self) -> None:
        self.items: dict[str, list[dict[str, Any]]] = {"regular": [], "prespec": []}
        self.requests: list[httpx.Request] = []
        self.fail_queue: list[httpx.Response] = []

    @property
    def calls(self) -> int:
        return len(self.requests)

    def add(self, source: str, *items: dict[str, Any]) -> None:
        self.items[source].extend(items)

    def fail(self, *responses: httpx.Response) -> None:
        """다음 호출들에 순서대로 돌려줄 실패 응답."""
        self.fail_queue.extend(responses)

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.fail_queue:
            return self.fail_queue.pop(0)
        source = OPS.get(request.url.path.rsplit("/", 1)[-1])
        if source is None:
            return httpx.Response(404, text="unknown op")
        p = request.url.params
        bgn = datetime.strptime(p["inqryBgnDt"], "%Y%m%d%H%M").replace(tzinfo=KST)
        end = datetime.strptime(p["inqryEndDt"], "%Y%m%d%H%M").replace(tzinfo=KST)
        if end - bgn > timedelta(days=16):  # 실제 API의 기간 제한 오류 모양
            return httpx.Response(
                200,
                json={
                    "nkoneps.com.response.ResponseError": {
                        "header": {"resultCode": "07", "resultMsg": "입력범위값 초과 에러"}
                    }
                },
            )
        kw = p.get("bidNtceNm") or p.get("prdctClsfcNoNm")
        matched = []
        for it in self.items[source]:
            dt = datetime.strptime(it[DATE_FIELD[source]][:16], "%Y-%m-%d %H:%M").replace(
                tzinfo=KST
            )
            if bgn <= dt <= end and (not kw or kw in it[TITLE_FIELD[source]]):
                matched.append(it)
        rows, page = int(p.get("numOfRows", "10")), int(p.get("pageNo", "1"))
        chunk = matched[(page - 1) * rows : page * rows]
        body = {"items": chunk, "numOfRows": rows, "pageNo": page, "totalCount": len(matched)}
        return httpx.Response(
            200,
            json={"response": {"header": {"resultCode": "00", "resultMsg": "정상"}, "body": body}},
        )

    def http_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handler))

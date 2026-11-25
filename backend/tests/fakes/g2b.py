"""녹화본 기반 가짜 G2B 서버 (SPEC §12.2). 호출 수를 세고 실패를 주입할 수 있다.

실제 응답 모양(`tests/fixtures/g2b/*.json`)의 항목을 틀로 써서 날짜·번호만 바꾼 공고를 만든다.
조회 창(inqryBgnDt~inqryEndDt, KST 분 단위)과 numOfRows·pageNo를 실제 API처럼 처리한다.
"""

from __future__ import annotations

import asyncio
import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "g2b"
KST = timezone(timedelta(hours=9))
OPS = {
    "getBidPblancListInfoServcPPSSrch02": "regular",
    "getPublicPrcureThngInfoServcPPSSrch": "prespec",
    "getScsbidListSttusServc": "awards",
    "getCntrctInfoListServc": "contracts",
}
# 기간 제한: 사전규격은 약 15일, 공고(v1.3)·낙찰·계약은 KST 날짜 7개까지(날짜 차 6일 이하)
# (docs/decisions/2026-11-16-awards-probe.md, 2026-11-24-bid-service-02.md)
MAX_SPAN = {"prespec": timedelta(days=16)}
MAX_DATE_DIFF = {"regular": 6, "awards": 6, "contracts": 6}
# 입찰공고 v1.3은 서비스 경로도 02로 바뀌었다(운영계정 트래픽은 02에만 승인)
BID_SERVICE_PATH = "/1230000/ad/BidPublicInfoService02/"
# 단건 조회용 일반 조회 (docs/decisions/2026-11-12-g2b-single-lookup.md): inqryDiv=2 + 번호
LOOKUP_OPS = {"getBidPblancListInfoServc02": "regular", "getPublicPrcureThngInfoServc": "prespec"}
NO_FIELD = {"regular": "bidNtceNo", "prespec": "bfSpecRgstNo"}
DATE_FIELD = {
    "regular": "bidNtceDt",
    "prespec": "rgstDt",
    "awards": "rgstDt",
    "contracts": "rgstDt",
}
TITLE_FIELD = {
    "regular": "bidNtceNm",
    "prespec": "prdctClsfcNoNm",
    "awards": "bidNtceNm",
    "contracts": "cntrctNm",
}
OPENING_OP = "getOpengResultListInfoOpengCompt"
STATUS_OP = "getOpengResultListInfoServc"
AWARD_OP = "getScsbidListSttusServc"


def _template(name: str) -> dict[str, Any]:
    data = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    items = data["response"]["body"]["items"]
    return copy.deepcopy(items[0] if isinstance(items, list) else items["item"][0])


REGULAR_TEMPLATE = _template("regular_page1.json")
PRESPEC_TEMPLATE = _template("prespec_page1.json")
AWARD_TEMPLATE = _template("awards_page1.json")
OPENING_TEMPLATE = _template("opening_compt_page1.json")
CONTRACT_TEMPLATE = _template("contracts_page1.json")


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


def award_item(
    no: str,
    registered_at: datetime,
    *,
    bizno: str | None = "1234567890",
    name: str = "(주)가온데이터",
    ord: str = "000",
    clsfc: str = "0",
    rbid: str = "000",
    title: str = "데이터 정비 용역",
    amount: str = "90000000",
    rate: str = "87.5",
    org_cd: str = "1234567",
    org_name: str = "행정안전부",
    pii: bool = False,
) -> dict[str, Any]:
    """낙찰 응답 항목(실제 녹화본이 틀). pii=True면 대표자·주소·전화·담당자 필드를 채운다."""
    it = copy.deepcopy(AWARD_TEMPLATE)
    it.update(
        bidNtceNo=no,
        bidNtceOrd=ord,
        bidClsfcNo=clsfc,
        rbidNo=rbid,
        bidNtceNm=title,
        bidwinnrNm=name,
        bidwinnrBizno=bizno if bizno is not None else "",
        sucsfbidAmt=amount,
        sucsfbidRate=rate,
        dminsttCd=org_cd,
        dminsttNm=org_name,
        rgstDt=kst_str(registered_at),
        rlOpengDt=kst_str(registered_at - timedelta(days=1)),
        fnlSucsfDate=registered_at.astimezone(KST).strftime("%Y-%m-%d"),
    )
    if pii:
        it.update(
            bidwinnrCeoNm="홍길동대표",
            bidwinnrAdrs="서울특별시 어딘가로 12-3",
            bidwinnrTelNo="02-555-0199",
            fnlSucsfCorpOfcl="김담당",
        )
    return it


def opening_item(
    no: str,
    bizno: str,
    *,
    ord: str = "000",
    rank: str = "1",
    name: str = "(주)가온데이터",
    amount: str = "90000000",
    rate: str = "",
    tech: str = "71.4167",
    price: str = "18.3206",
    total: str = "89.7373",
    clsfc: str = "0",
    rbid: str = "000",
    remark: str = "정상",
) -> dict[str, Any]:
    """개찰완료 목록 항목(OpengCompt 녹화본이 틀). 순위가 비면 remark에 탈락 사유(P12-a)."""
    it = copy.deepcopy(OPENING_TEMPLATE)
    it.update(
        bidNtceNo=no,
        bidNtceOrd=ord,
        bidClsfcNo=clsfc,
        rbidNo=rbid,
        opengRank=rank,
        prcbdrBizno=bizno,
        prcbdrNm=name,
        bidprcAmt=amount,
        bidprcrt=rate,
        techEvlVal=tech,
        bidPrceEvlVal=price,
        totalEvlAmtVal=total,
        rmrk=remark,
    )
    return it


def status_item(
    no: str,
    status: str,
    *,
    ord: str = "000",
    clsfc: str = "0",
    rbid: str = "000",
    opened_at: str = "2026-11-10 10:00:00",
    entered_at: str = "2026-11-10 10:00:30",
) -> dict[str, Any]:
    """개찰결과 항목(getOpengResultListInfoServc, 2026-11-25 실제 응답 필드)."""
    return {
        "bidNtceNo": no,
        "bidNtceOrd": ord,
        "bidClsfcNo": clsfc,
        "rbidNo": rbid,
        "progrsDivCdNm": status,
        "opengDt": opened_at,
        "inptDt": entered_at,
        "bidNtceNm": "데이터 정비 용역",
        "prtcptCnum": "0",
    }


def contract_item(
    ntce_no: str,
    registered_at: datetime,
    members: list[tuple[str, str, str, str]],
    *,
    mode: str = "공동",
) -> dict[str, Any]:
    """계약 항목(녹화본이 틀). members: (업체구분, 업체명, 지분율, 사업자번호).

    대표자·담당자 칸은 빈 값.
    """
    it = copy.deepcopy(CONTRACT_TEMPLATE)
    corp = ",".join(
        f"[{i}^{role}^{mode}^{name}^^대한민국^{share}^^^{bizno}]"
        for i, (role, name, share, bizno) in enumerate(members, start=1)
    )
    it.update(ntceNo=ntce_no, corpList=corp, rgstDt=kst_str(registered_at))
    return it


class FakeG2B:
    def __init__(self) -> None:
        self.items: dict[str, list[dict[str, Any]]] = {
            "regular": [],
            "prespec": [],
            "awards": [],
            "contracts": [],
            "opening_compt": [],
            "opening_status": [],  # 개찰결과(진행 상태) — 결과 메일 감시
        }
        self.requests: list[httpx.Request] = []
        self.fail_queue: list[httpx.Response] = []
        self.delay_s = 0.0  # 느린 G2B ('수집 중' 시험)
        # 이 페이지 번호는 빈 목록을 준다(totalCount는 그대로) — 창의 일부만 받은 경우
        self.drop_pages: set[int] = set()

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
        op = request.url.path.rsplit("/", 1)[-1]
        p = request.url.params
        if op.startswith("getBidPblanc") and not request.url.path.startswith(BID_SERVICE_PATH):
            return httpx.Response(404, text="unknown service")
        if op in LOOKUP_OPS:
            return self._lookup(LOOKUP_OPS[op], p)
        if op == STATUS_OP or (op == AWARD_OP and p.get("inqryDiv") == "4"):
            src = "opening_status" if op == STATUS_OP else "awards"
            matched = [it for it in self.items[src] if it["bidNtceNo"] == p.get("bidNtceNo")]
            return _ok({"items": matched, "totalCount": len(matched)})
        if op == OPENING_OP:
            matched = [
                it
                for it in self.items["opening_compt"]
                if it["bidNtceNo"] == p.get("bidNtceNo")
                and (not p.get("bidNtceOrd") or it["bidNtceOrd"] == p["bidNtceOrd"])
            ]
            return _ok({"items": matched, "totalCount": len(matched)})
        source = OPS.get(op)
        if source is None:
            return httpx.Response(404, text="unknown op")
        bgn = datetime.strptime(p["inqryBgnDt"], "%Y%m%d%H%M").replace(tzinfo=KST)
        end = datetime.strptime(p["inqryEndDt"], "%Y%m%d%H%M").replace(tzinfo=KST)
        too_long = (source in MAX_SPAN and end - bgn > MAX_SPAN[source]) or (
            source in MAX_DATE_DIFF and (end.date() - bgn.date()).days > MAX_DATE_DIFF[source]
        )
        if too_long:  # 실제 API의 기간 제한 오류 모양
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
        if rows > 999:  # 실제 API: 1000 이상이면 오류 없이 기본 10행
            rows = 10
        chunk = [] if page in self.drop_pages else matched[(page - 1) * rows : page * rows]
        body = {"items": chunk, "numOfRows": rows, "pageNo": page, "totalCount": len(matched)}
        return httpx.Response(
            200,
            json={"response": {"header": {"resultCode": "00", "resultMsg": "정상"}, "body": body}},
        )

    def _lookup(self, source: str, p: httpx.QueryParams) -> httpx.Response:
        field = NO_FIELD[source]
        if p.get("inqryDiv") != "2" or not p.get(field):
            return _ok({"items": [], "totalCount": 0})
        matched = [it for it in self.items[source] if it.get(field) == p[field]]
        return _ok({"items": matched, "totalCount": len(matched)})

    async def _async_handler(self, request: httpx.Request) -> httpx.Response:
        if self.delay_s:
            await asyncio.sleep(self.delay_s)
        return self.handler(request)

    def http_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self._async_handler))


def _ok(body: dict[str, Any]) -> httpx.Response:
    return httpx.Response(
        200, json={"response": {"header": {"resultCode": "00", "resultMsg": "정상"}, "body": body}}
    )

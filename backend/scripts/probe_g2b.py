"""P1 [미확인] 항목 확인 + G2B 녹화본 생성 (SPEC §4, §5.2, §5.6).

확인 항목: numOfRows 최대값, 키워드 없는 조회, 정정공고 차수(bidNtceOrd), 하루치 건수,
첨부 호스트 목록, httpx 첨부 다운로드 가능 여부, 오류 응답 모양.
실제 G2B를 약 15회 호출한다. 서비스키는 출력·파일에 남기지 않는다(규칙 4).

실행: uv run python scripts/probe_g2b.py --env-file ../.env
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from dotenv import dotenv_values

BID_BASE = "http://apis.data.go.kr/1230000/ad/BidPublicInfoService"
PRESPEC_BASE = "http://apis.data.go.kr/1230000/ao/HrcspSsstndrdInfoService"
BID_OP = "getBidPblancListInfoServcPPSSrch"
PRESPEC_OP = "getPublicPrcureThngInfoServcPPSSrch"
EORDER_OP = "getBidPblancListInfoEorderAtchFileInfo"
FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "g2b"
KEEP_ITEMS = 5


class Prober:
    def __init__(self, bid_key: str, prespec_key: str) -> None:
        self.keys = {"bid": bid_key, "prespec": prespec_key}
        self.calls = 0
        self.client = httpx.Client(timeout=httpx.Timeout(30.0, connect=5.0))

    def mask(self, text: str) -> str:
        for k in self.keys.values():
            if k:
                text = text.replace(k, "***MASKED***")
        return text

    def get(self, base: str, op: str, key: str, **params: Any) -> dict[str, Any]:
        """호출 결과를 상태코드·본문(마스킹)과 함께 돌려준다. 예외도 기록만 한다."""
        self.calls += 1
        q = {"ServiceKey": self.keys.get(key, key), "type": "json", **params}
        try:
            r = self.client.get(f"{base}/{op}", params=q)
        except httpx.HTTPError as e:
            return {"status": None, "error": self.mask(repr(e))[:300]}
        body = self.mask(r.text)
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return {"status": r.status_code, "raw": body[:500]}
        return {"status": r.status_code, "data": data}


def items_of(data: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        items = data["response"]["body"].get("items")
    except (KeyError, TypeError, AttributeError):
        return []
    if isinstance(items, list):
        return items
    if isinstance(items, dict):
        raw = items.get("item") or []
        return raw if isinstance(raw, list) else [raw]
    return []


def total_of(data: dict[str, Any]) -> int | None:
    try:
        return int(data["response"]["body"]["totalCount"])
    except (KeyError, TypeError, ValueError):
        return None


def header_of(res: dict[str, Any]) -> Any:
    data = res.get("data") or {}
    return (
        (data.get("response") or {}).get("header")
        or data.get("nkoneps.com.response.ResponseError")
        or res.get("raw")
        or res.get("error")
    )


_CONTACT = re.compile(
    r"(Ofcl|ofcl|exctv|crdtr).*(Nm|TelNo|EmailAdrs)$|^(ofclNm|ofclTelNo|exctvNm|crdtrNm)$"
)


def scrub_contacts(o: Any) -> None:
    """담당 공무원 이름·전화·이메일은 녹화본에 남기지 않는다 (§12.9)."""
    if isinstance(o, dict):
        for k, v in o.items():
            if isinstance(v, str) and v and _CONTACT.search(k):
                o[k] = (
                    "official@example.go.kr"
                    if "Email" in k
                    else ("000-0000-0000" if "Tel" in k else "담당자")
                )
            else:
                scrub_contacts(v)
    elif isinstance(o, list):
        for x in o:
            scrub_contacts(x)


def save(name: str, res: dict[str, Any]) -> None:
    """녹화본은 항목을 KEEP_ITEMS개로 줄이고(totalCount는 그대로) 연락처를 지워 저장한다."""
    data = json.loads(json.dumps(res.get("data") or res))
    body = (data.get("response") or {}).get("body") if isinstance(data, dict) else None
    if isinstance(body, dict) and isinstance(body.get("items"), (list, dict)):
        its = items_of(data)[:KEEP_ITEMS]
        body["items"] = its if isinstance(body["items"], list) else {"item": its}
    scrub_contacts(data)
    FIXTURES.mkdir(parents=True, exist_ok=True)
    (FIXTURES / f"{name}.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8"
    )


def file_urls(item: dict[str, Any]) -> list[str]:
    keys = [f"ntceSpecDocUrl{i}" for i in range(1, 11)] + [
        f"specDocFileUrl{i}" for i in range(1, 6)
    ]
    keys.append("eorderAtchFileUrl")
    return [item[k] for k in keys if item.get(k)]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env-file", required=True)
    ap.add_argument("--out", required=True, help="요약 JSON 경로 (저장소 밖)")
    args = ap.parse_args()
    env = dotenv_values(args.env_file)
    p = Prober(env.get("NARA_API_KEY") or "", env.get("NARA_PRESPEC_API_KEY") or "")
    fmt = "%Y%m%d%H%M"
    day = (datetime.now() - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    d1 = {
        "inqryDiv": "1",
        "inqryBgnDt": day.strftime(fmt),
        "inqryEndDt": (day + timedelta(hours=23, minutes=59)).strftime(fmt),
    }
    report: dict[str, Any] = {"window_1day": d1}

    # 일반공고: 키워드 없이 하루치, numOfRows 100
    r = p.get(BID_BASE, BID_OP, "bid", numOfRows="100", pageNo="1", **d1)
    report["regular_1day_100"] = {
        "status": r["status"],
        "header": header_of(r),
        "totalCount": total_of(r.get("data") or {}),
        "returned": len(items_of(r.get("data") or {})),
    }
    save("regular_page1", r)
    regular_items = items_of(r.get("data") or {})
    total = total_of(r.get("data") or {}) or 0
    if total > 100:
        r2 = p.get(BID_BASE, BID_OP, "bid", numOfRows="100", pageNo="2", **d1)
        report["regular_1day_page2"] = {
            "status": r2["status"],
            "returned": len(items_of(r2.get("data") or {})),
        }
        save("regular_page2", r2)
        regular_items += items_of(r2.get("data") or {})

    # numOfRows 상한
    for n in ("500", "999"):
        rn = p.get(BID_BASE, BID_OP, "bid", numOfRows=n, pageNo="1", **d1)
        report[f"regular_numOfRows_{n}"] = {
            "status": rn["status"],
            "header": header_of(rn),
            "returned": len(items_of(rn.get("data") or {})),
            "totalCount": total_of(rn.get("data") or {}),
        }
        if n == "999":
            regular_items = items_of(rn.get("data") or {}) or regular_items

    # 기간 제한(16일) 오류 모양
    long = {
        "inqryDiv": "1",
        "inqryBgnDt": (day - timedelta(days=16)).strftime(fmt),
        "inqryEndDt": d1["inqryEndDt"],
    }
    rl = p.get(BID_BASE, BID_OP, "bid", numOfRows="10", pageNo="1", **long)
    report["regular_17day_window"] = {
        "status": rl["status"],
        "header": header_of(rl),
        "totalCount": total_of(rl.get("data") or {}),
    }
    save("error_period_too_long", rl)

    # 잘못된 키 오류 모양
    rk = p.get(BID_BASE, BID_OP, "INVALID-KEY-FOR-PROBE", numOfRows="10", pageNo="1", **d1)
    report["invalid_key"] = {"status": rk["status"], "header": header_of(rk)}
    save("error_invalid_key", rk)

    # 키워드 검색 (v1 방식)
    rkw = p.get(
        BID_BASE,
        BID_OP,
        "bid",
        numOfRows="100",
        pageNo="1",
        bidNtceNm="AI",
        **{**d1, "inqryBgnDt": (day - timedelta(days=6)).strftime(fmt)},
    )
    report["regular_keyword_AI_7day"] = {
        "status": rkw["status"],
        "totalCount": total_of(rkw.get("data") or {}),
    }
    save("regular_keyword_ai", rkw)

    # 사전규격
    rp = p.get(PRESPEC_BASE, PRESPEC_OP, "prespec", numOfRows="100", pageNo="1", **d1)
    report["prespec_1day_100"] = {
        "status": rp["status"],
        "header": header_of(rp),
        "totalCount": total_of(rp.get("data") or {}),
        "returned": len(items_of(rp.get("data") or {})),
    }
    save("prespec_page1", rp)
    rp9 = p.get(PRESPEC_BASE, PRESPEC_OP, "prespec", numOfRows="999", pageNo="1", **d1)
    report["prespec_numOfRows_999"] = {
        "status": rp9["status"],
        "header": header_of(rp9),
        "returned": len(items_of(rp9.get("data") or {})),
    }
    prespec_items = items_of(rp9.get("data") or {}) or items_of(rp.get("data") or {})

    # 필드 목록과 정정공고 차수
    report["regular_fields"] = sorted({k for it in regular_items for k in it})
    report["prespec_fields"] = sorted({k for it in prespec_items for k in it})
    ords = Counter(str(it.get("bidNtceOrd")) for it in regular_items)
    per_no = Counter(it.get("bidNtceNo") for it in regular_items)
    report["bidNtceOrd_counts"] = dict(ords)
    report["bid_no_with_multiple_rows"] = [no for no, c in per_no.items() if c > 1][:10]
    report["ntceKindNm_counts"] = dict(Counter(str(it.get("ntceKindNm")) for it in regular_items))
    revised = [
        it for it in regular_items if str(it.get("bidNtceOrd", "")).lstrip("0") not in ("", "1")
    ]
    if revised:
        save(
            "regular_revised_sample",
            {
                "response": {
                    "header": {"resultCode": "00"},
                    "body": {"items": revised[:KEEP_ITEMS], "totalCount": len(revised)},
                }
            },
        )
    report["date_samples"] = {
        k: [it.get(k) for it in regular_items[:3]]
        for k in ("bidNtceDt", "bidClseDt", "opengDt", "rgstDt")
    }
    report["prespec_date_samples"] = {
        k: [it.get(k) for it in prespec_items[:3]] for k in ("rcptDt", "opninRgstClseDt", "rgstDt")
    }

    # e발주 첨부: 첨부 URL이 없는 공고 하나
    no_file = next((it for it in regular_items if not file_urls(it)), None)
    report["regular_without_files"] = sum(1 for it in regular_items if not file_urls(it))
    if no_file:
        re_ = p.get(
            BID_BASE,
            EORDER_OP,
            "bid",
            inqryDiv="2",
            bidNtceNo=no_file.get("bidNtceNo"),
            numOfRows="10",
            pageNo="1",
        )
        report["eorder_attach"] = {
            "status": re_["status"],
            "header": header_of(re_),
            "returned": len(items_of(re_.get("data") or {})),
            "fields": sorted({k for it in items_of(re_.get("data") or {}) for k in it}),
        }
        save("eorder_attach", re_)

    # 첨부 호스트와 httpx 다운로드
    urls = [u for it in regular_items + prespec_items for u in file_urls(it)]
    report["file_hosts"] = dict(Counter(urlparse(u).netloc for u in urls))
    report["file_url_schemes"] = dict(Counter(urlparse(u).scheme for u in urls))
    downloads = []
    for u in urls[:2]:
        for verify in (True, False):
            try:
                with (
                    httpx.Client(timeout=30.0, verify=verify, follow_redirects=False) as c,
                    c.stream("GET", u) as resp,
                ):
                    first = next(resp.iter_bytes(4096), b"")
                    downloads.append(
                        {
                            "host": urlparse(u).netloc,
                            "verify": verify,
                            "status": resp.status_code,
                            "content_type": resp.headers.get("content-type"),
                            "content_disposition": (resp.headers.get("content-disposition") or "")[
                                :120
                            ],
                            "location": resp.headers.get("location"),
                            "magic": first[:8].hex(),
                        }
                    )
            except httpx.HTTPError as e:
                downloads.append(
                    {"host": urlparse(u).netloc, "verify": verify, "error": repr(e)[:200]}
                )
    report["downloads"] = downloads
    report["g2b_calls"] = p.calls
    Path(args.out).write_text(
        p.mask(json.dumps(report, ensure_ascii=False, indent=1)), encoding="utf-8"
    )
    print(f"done: {p.calls} G2B calls, fixtures in {FIXTURES}")


if __name__ == "__main__":
    main()

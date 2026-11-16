"""P8-a 낙찰·계약 API 확인 (SPEC §15.10의 8가지). 코드·스키마는 바꾸지 않는 읽기 전용 스크립트.

- 키 마스킹·오류 해석은 `app.g2b.client.G2BClient`의 것을 그대로 쓴다.
- 호출은 합쳐서 MAX_CALLS(80)회를 넘지 않는다(넘기 전에 예외). 끝에 호출 수를 출력한다.
- 응답 원문은 --out-dir(저장소 밖)에 저장하되 대표자명·주소·전화·담당자 필드는 저장 전에 지운다.
- DB는 bids를 읽기만 한다.

실행: uv run python -m scripts.probe_awards --env-file ../.env --env-file .env --out-dir <저장소 밖>
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import statistics
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
from dotenv import dotenv_values
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.g2b.client import G2BClient, G2BError, _items

KST = timezone(timedelta(hours=9))
MAX_CALLS = 80
AS_BASE = "http://apis.data.go.kr/1230000/as/ScsbidInfoService"
AO_BASE = "http://apis.data.go.kr/1230000/ao/CntrctInfoService"
AWARD_OP = "getScsbidListSttusServc"
COMPT_OP = "getOpengResultListInfoOpengCompt"
OPENG_OP = "getOpengResultListInfoServc"
CNTRCT_OP = "getCntrctInfoListServc"
FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "g2b"
FMT = "%Y%m%d%H%M"
BIZNO_RE = re.compile(r"\d{10}")

# 개인정보(대표자·주소·전화·팩스·담당자·채권자). §15.9
_PII_KEY = re.compile(r"(CeoNm|Adrs|TelNo|FaxNo|Ofcl|crdtrNm|ChrgDeptNm)", re.IGNORECASE)
_PHONE = re.compile(r"^\d{2,4}-[\d*]{3,4}-[\d*]{4}$")
# 문서상 위치(0부터): corpList 4 대표자명·7 채권자명·8 담당자성명, dminsttList 5 담당자·6 전화
_LIST_PII = {"corpList": {4, 7, 8}, "dminsttList": {4, 5, 6}}


def scrub_list(field: str, value: str) -> str:
    """'[a^b^...],[...]' 꼴에서 개인정보 위치와 전화번호 모양을 지운다."""
    out = []
    for part in re.findall(r"\[([^\]]*)\]", value):
        cells = part.split("^")
        cells = [
            "" if i in _LIST_PII[field] or _PHONE.match(c.strip()) else c
            for i, c in enumerate(cells)
        ]
        out.append("[" + "^".join(cells) + "]")
    return ",".join(out)


def scrub(o: Any) -> Any:
    if isinstance(o, dict):
        res = {}
        for k, v in o.items():
            if _PII_KEY.search(k):
                continue
            if k in _LIST_PII and isinstance(v, str):
                res[k] = scrub_list(k, v)
            else:
                res[k] = scrub(v)
        return res
    if isinstance(o, list):
        return [scrub(x) for x in o]
    return o


class Prober:
    """G2BClient의 마스킹·오류 해석을 쓰되, 오류 응답도 결과로 돌려준다(확인용)."""

    def __init__(self, http: httpx.AsyncClient, key: str, out_dir: Path) -> None:
        self.client = G2BClient(http, {"awards": key})
        self.http, self.key, self.out_dir = http, key, out_dir
        self.calls = 0

    async def get(self, base: str, op: str, save_as: str | None = None, **params: Any) -> dict:
        if self.calls >= MAX_CALLS:
            raise RuntimeError(f"호출 상한 {MAX_CALLS}회")
        self.calls += 1
        q = {"ServiceKey": self.key, "type": "json", **{k: str(v) for k, v in params.items()}}
        try:
            resp = await self.http.get(
                f"{base}/{op}", params=q, timeout=httpx.Timeout(60, connect=5)
            )
        except httpx.HTTPError as e:
            return {"ok": False, "status": None, "error": self.client.mask(repr(e))[:300]}
        res: dict[str, Any] = {"status": resp.status_code}
        try:
            body = self.client._parse(resp)
            res.update(ok=True, body=body, total=int(body.get("totalCount") or 0))
            res["items"] = _items(body)
        except G2BError as e:
            res.update(
                ok=False, error=self.client.mask(str(e)), raw=self.client.mask(resp.text[:300])
            )
        if save_as:
            data = {k: v for k, v in res.items() if k != "items"}
            (self.out_dir / f"{save_as}.json").write_text(
                self.client.mask(json.dumps(scrub(data), ensure_ascii=False, indent=1)),
                encoding="utf-8",
            )
        return res

    async def window(
        self, op: str, bgn: datetime, end: datetime, rows: int = 999, **kw: Any
    ) -> dict:
        p = {"inqryDiv": 1, "inqryBgnDt": bgn.strftime(FMT), "inqryEndDt": end.strftime(FMT)}
        return await self.get(
            AS_BASE if op != CNTRCT_OP else AO_BASE, op, numOfRows=rows, pageNo=1, **p, **kw
        )

    async def window_all(self, op: str, bgn: datetime, end: datetime, max_pages: int = 4) -> dict:
        """창의 모든 페이지(최대 max_pages). pages_complete로 완료 여부를 알려 준다."""
        first = await self.window(op, bgn, end)
        if not first.get("ok"):
            return first
        items, page = list(first["items"]), 1
        while len(items) < first["total"] and page < max_pages:
            page += 1
            p = {"inqryDiv": 1, "inqryBgnDt": bgn.strftime(FMT), "inqryEndDt": end.strftime(FMT)}
            r = await self.get(
                AS_BASE if op != CNTRCT_OP else AO_BASE, op, numOfRows=999, pageNo=page, **p
            )
            if not r.get("ok") or not r["items"]:
                break
            items += r["items"]
        return {**first, "items": items, "pages": page, "complete": len(items) >= first["total"]}


def fmt_kind(no: str) -> str:
    if re.fullmatch(r"R\d{2}[A-Z]{2}\d{8}", no):
        return "new13"
    if re.fullmatch(r"\d{11}", no):
        return "old11"
    return f"other(len{len(no)})"


def brief(res: dict) -> dict:
    return {
        k: res.get(k) for k in ("ok", "status", "total", "error", "raw") if res.get(k) is not None
    } | {"returned": len(res.get("items") or [])}


def fill_rate(items: list[dict], keys: list[str]) -> dict:
    return {
        k: f"{sum(1 for it in items if str(it.get(k) or '').strip())}/{len(items)}" for k in keys
    }


def save_fixture(name: str, items: list[dict], total: int) -> None:
    body = {"items": scrub(items[:5]), "numOfRows": 999, "pageNo": 1, "totalCount": total}
    data = {"response": {"header": {"resultCode": "00", "resultMsg": "정상"}, "body": body}}
    FIXTURES.mkdir(parents=True, exist_ok=True)
    (FIXTURES / f"{name}.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8"
    )


async def load_bids(db_url: str) -> dict[str, dict]:
    eng = create_async_engine(db_url)
    async with eng.connect() as c:
        rows = (
            await c.execute(
                text(
                    "SELECT bid_no, raw->>'bidNtceOrd', raw->>'sucsfbidMthdNm', raw->>'bidClseDt',"
                    " raw->>'opengDt', budget FROM bids WHERE source='regular'"
                )
            )
        ).all()
    await eng.dispose()
    return {
        r[0]: {"ord": r[1], "mthd": r[2] or "", "close": r[3], "openg": r[4], "budget": r[5]}
        for r in rows
    }


async def run(key: str, db_url: str, out_dir: Path) -> dict:
    rep: dict[str, Any] = {}
    today = datetime.now(KST).replace(hour=0, minute=0, second=0, microsecond=0)
    async with httpx.AsyncClient() as http:
        p = Prober(http, key, out_dir)

        # 7) 키 확인: 낙찰 1일, 계약 1일 (각 10행)
        d1b, d1e = today - timedelta(days=1), today - timedelta(minutes=1)
        r_aw = await p.window(AWARD_OP, d1b, d1e, rows=10)
        r_ct = await p.window(CNTRCT_OP, d1b, d1e, rows=10)
        rep["7_key"] = {"awards": brief(r_aw), "contracts": brief(r_ct)}
        if not r_aw.get("ok"):
            rep["calls"] = p.calls
            return rep

        # 2) 기간 제한: 7일(-1분), 정확히 7일, 8일, 31일 / numOfRows 999·1000
        end = today - timedelta(minutes=1)
        spans = {
            "7d_minus_1min": 7 * 1440,
            "7d_exact": 7 * 1440 + 1,
            "8d": 8 * 1440,
            "31d": 31 * 1440,
        }
        rep["2_span"] = {}
        for name, minutes in spans.items():
            r = await p.window(
                AWARD_OP, end - timedelta(minutes=minutes - 1), end, rows=1, save_as=f"span_{name}"
            )
            rep["2_span"][name] = brief(r)
        b7 = today - timedelta(days=7)
        r1000 = await p.window(AWARD_OP, b7, end, rows=1000)
        rep["2_numOfRows_1000"] = brief(r1000)

        # 3) 최근 7일 창 전체 (999행 페이지) + 개찰일시(3) 기준 건수 비교
        recent = await p.window_all(AWARD_OP, b7, end)
        rep["3_recent7"] = brief(recent) | {
            "pages": recent.get("pages"),
            "complete": recent.get("complete"),
        }
        r3 = await p.get(
            AS_BASE,
            AWARD_OP,
            inqryDiv=3,
            inqryBgnDt=b7.strftime(FMT),
            inqryEndDt=end.strftime(FMT),
            numOfRows=1,
            pageNo=1,
        )
        rep["3_recent7_by_openg"] = brief(r3)
        awards = list(recent.get("items") or [])
        # 그 전 주 창(1번 대조용 표본 늘리기)
        prev = await p.window_all(AWARD_OP, b7 - timedelta(days=7), b7 - timedelta(minutes=1))
        rep["3_prev7"] = brief(prev) | {"pages": prev.get("pages")}
        awards += prev.get("items") or []
        if awards:
            save_fixture("awards_page1", awards, recent.get("total") or len(awards))
            rep["award_fields"] = sorted({k for it in awards for k in it if not _PII_KEY.search(k)})

        # 8) 과거 시점의 7일 창 건수 (1년·2년·3년·5년 전)
        rep["8_past_totals"] = {}
        for y in (1, 2, 3, 5):
            pb = today - timedelta(days=365 * y)
            r = await p.window(
                AWARD_OP,
                pb - timedelta(days=7),
                pb - timedelta(minutes=1),
                rows=999 if y == 5 else 1,
            )
            rep["8_past_totals"][f"{y}y"] = brief(r)
            if y == 5 and r.get("items"):
                old = r["items"]
                rep["8_old_formats"] = dict(
                    Counter(fmt_kind(str(it.get("bidNtceNo"))) for it in old)
                )
                rep["8_old_fill"] = fill_rate(
                    old, ["bidwinnrBizno", "sucsfbidAmt", "sucsfbidRate", "dminsttCd", "prtcptCnum"]
                )
                save_fixture("awards_old_page1", old, r["total"])

        # 1) 공고번호 형식과 bids 연결
        bids = await load_bids(db_url)
        rep["1_award_formats"] = dict(Counter(fmt_kind(str(it.get("bidNtceNo"))) for it in awards))
        rep["1_bids_formats"] = dict(Counter(fmt_kind(n) for n in bids))
        matched = [it for it in awards if it.get("bidNtceNo") in bids]
        rep["1_awards_in_bids"] = {
            k: f"{sum(1 for it in matched if fmt_kind(it['bidNtceNo']) == k)}/{v}"
            for k, v in rep["1_award_formats"].items()
        }
        same_ord = sum(1 for it in matched if it.get("bidNtceOrd") == bids[it["bidNtceNo"]]["ord"])
        rep["1_ord_equal_bids_max"] = f"{same_ord}/{len(matched)}"
        rep["1_ord_samples"] = Counter(str(it.get("bidNtceOrd")) for it in awards).most_common(5)
        rep["1_ntceDivCd"] = Counter(str(it.get("ntceDivCd")) for it in awards).most_common(5)
        key3 = Counter(
            (it.get("bidNtceNo"), it.get("bidNtceOrd"), it.get("bidwinnrBizno")) for it in awards
        )
        key5 = Counter(
            (
                it.get("bidNtceNo"),
                it.get("bidNtceOrd"),
                it.get("bidClsfcNo"),
                it.get("rbidNo"),
                it.get("bidwinnrBizno"),
            )
            for it in awards
        )
        rep["1_dup_keys"] = {
            "no_ord_bizno": sum(c - 1 for c in key3.values() if c > 1),
            "no_ord_clsfc_rbid_bizno": sum(c - 1 for c in key5.values() if c > 1),
            "clsfc_values": Counter(str(it.get("bidClsfcNo")) for it in awards).most_common(5),
            "rbid_values": Counter(str(it.get("rbidNo")) for it in awards).most_common(5),
        }
        # 20건 역대조: 마감이 최근 2주 안인 bids → 낙찰 창에 있는가, 없으면 번호 조회(최대 8회)
        lo, hi = (b7 - timedelta(days=7)).strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")
        cand = sorted(
            (n for n, b in bids.items() if b["close"] and lo <= b["close"][:10] <= hi), reverse=True
        )[:20]
        award_nos = {it.get("bidNtceNo") for it in awards}
        found = [n for n in cand if n in award_nos]
        lookups = {}
        for n in [n for n in cand if n not in award_nos][:8]:
            r = await p.get(AS_BASE, AWARD_OP, inqryDiv=4, bidNtceNo=n, numOfRows=10, pageNo=1)
            lookups[fmt_kind(n)] = lookups.get(fmt_kind(n), Counter())
            lookups[fmt_kind(n)][
                "hit" if r.get("items") else ("empty" if r.get("ok") else "error")
            ] += 1
        rep["1_bids20_reverse"] = {
            "sample": len(cand),
            "in_award_windows": len(found),
            "lookup_div4": {k: dict(v) for k, v in lookups.items()},
        }

        # 4) 협상계약: 금액·비율 채움, 개찰완료 점수
        nego = [it for it in matched if "협상" in bids[it["bidNtceNo"]]["mthd"]]
        other = [it for it in matched if "협상" not in bids[it["bidNtceNo"]]["mthd"]]
        rep["4_nego_awards"] = {
            "count": len(nego),
            "fill": fill_rate(nego, ["sucsfbidAmt", "sucsfbidRate", "bidwinnrBizno", "prtcptCnum"]),
        }
        rep["4_other_awards"] = {
            "count": len(other),
            "fill": fill_rate(
                other, ["sucsfbidAmt", "sucsfbidRate", "bidwinnrBizno", "prtcptCnum"]
            ),
        }
        rep["4_mthd_counts"] = Counter(
            bids[it["bidNtceNo"]]["mthd"].split("-")[0] for it in matched
        ).most_common(8)
        compt = {"nego": [], "other": []}
        compt_items: list[dict] = []
        for label, group, n in (("nego", nego, 5), ("other", other, 2)):
            for it in group[:n]:
                r = await p.get(
                    AS_BASE,
                    COMPT_OP,
                    numOfRows=100,
                    pageNo=1,
                    bidNtceNo=it["bidNtceNo"],
                    bidNtceOrd=it.get("bidNtceOrd"),
                )
                its = r.get("items") or []
                compt_items += its
                compt[label].append(
                    brief(r)
                    | {
                        "fill": fill_rate(
                            its,
                            [
                                "opengRank",
                                "prcbdrBizno",
                                "bidprcAmt",
                                "bidprcrt",
                                "techEvlVal",
                                "bidPrceEvlVal",
                                "totalEvlAmtVal",
                            ],
                        )
                    }
                    | {"rslt": Counter(str(i.get("opengRsltDivNm")) for i in its).most_common(3)}
                    | {"prtcptCnum": it.get("prtcptCnum")}
                )
        rep["4_compt"] = compt
        if compt_items:
            save_fixture("opening_compt_page1", compt_items, len(compt_items))
        for it in nego[:2]:
            r = await p.get(
                AS_BASE,
                OPENG_OP,
                numOfRows=10,
                pageNo=1,
                inqryDiv=4,
                bidNtceNo=it["bidNtceNo"],
                save_as=f"openg_servc_{it['bidNtceNo']}",
            )
            rep.setdefault("4_openg_servc", []).append(
                brief(r)
                | {
                    "fill": fill_rate(
                        r.get("items") or [],
                        ["opengCorpInfo", "prtcptCnum", "opengDt", "progrsDivCdNm"],
                    )
                }
            )

        # 5·6) 공동수급: 계약정보 1일 창 → cmmnCntrctYn=Y, ntceNo로 낙찰과 잇기
        ct = await p.window_all(CNTRCT_OP, today - timedelta(days=2), end, max_pages=3)
        cts = ct.get("items") or []
        rep["6_contracts"] = brief(ct) | {"pages": ct.get("pages"), "complete": ct.get("complete")}
        if cts:
            save_fixture(
                "contracts_page1",
                [c for c in cts if c.get("cmmnCntrctYn") == "Y"][:3] + cts[:2],
                ct.get("total") or 0,
            )
        joint = [c for c in cts if c.get("cmmnCntrctYn") == "Y"]
        rep["6_ntceNo_shapes"] = Counter(
            f"len{len(str(c.get('ntceNo') or ''))}:{str(c.get('ntceNo') or '')[:1]}" for c in cts
        ).most_common(6)
        rep["6_bsnsDivNm"] = Counter(str(c.get("bsnsDivNm")) for c in cts).most_common(5)
        award_by_no = {}
        for it in awards:
            award_by_no.setdefault(it.get("bidNtceNo"), []).append(it)
        shapes, links, joint_cases = Counter(), Counter(), []
        for c in cts:
            corp = re.findall(r"\[([^\]]*)\]", str(c.get("corpList") or ""))
            for part in corp:
                cells = part.split("^")
                bz = [i for i, x in enumerate(cells) if BIZNO_RE.fullmatch(x.strip())]
                role = cells[1] if len(cells) > 1 else ""
                mode = cells[2] if len(cells) > 2 else ""
                shapes[f"n={len(cells)}|bizno_idx={bz}|role={role}|mode={mode}"] += 1
            no = str(c.get("ntceNo") or "")
            for cut in (13, 11):
                if no[:cut] in award_by_no:
                    links[f"ntceNo[:{cut}]"] += 1
                    if c.get("cmmnCntrctYn") == "Y" and len(joint_cases) < 5:
                        aw = award_by_no[no[:cut]]
                        names = [p_.split("^")[3] if len(p_.split("^")) > 3 else "" for p_ in corp]
                        biznos = [p_.split("^")[-1].strip() for p_ in corp]
                        joint_cases.append(
                            {
                                "corp_count": len(corp),
                                "award_rows": len(aw),
                                "award_bizno_is_member": [
                                    a.get("bidwinnrBizno") in biznos for a in aw
                                ],
                                "award_bizno_is_first": [
                                    a.get("bidwinnrBizno") == (biznos[0] if biznos else None)
                                    for a in aw
                                ],
                                "award_name_eq_corp_idx3": [
                                    a.get("bidwinnrNm") in names for a in aw
                                ],
                                "award_name_has_sep": [
                                    bool(re.search(r"[,/]|외\s*\d", str(a.get("bidwinnrNm"))))
                                    for a in aw
                                ],
                            }
                        )
                    break
        rep["6_corpList_shapes"] = shapes.most_common(8)
        rep["6_link_to_awards"] = dict(links) | {"contracts": len(cts), "joint": len(joint)}
        rep["5_joint_cases"] = joint_cases
        rep["5_award_name_patterns"] = {
            "has_sep": sum(
                1 for it in awards if re.search(r"[,/]|외\s*\d", str(it.get("bidwinnrNm")))
            ),
            "bizno_not10": Counter(
                len(str(it.get("bidwinnrBizno") or ""))
                for it in awards
                if len(str(it.get("bidwinnrBizno") or "")) != 10
            ).most_common(3),
            "total": len(awards),
        }

        # 8) 백필 계산: 최근 두 창 + 과거 표본의 7일 건수 중앙값
        totals = [recent.get("total") or 0, prev.get("total") or 0] + [
            v.get("total") or 0 for v in rep["8_past_totals"].values()
        ]
        med = statistics.median(totals)
        pages = max(1, -(-int(med) // 999))
        windows = -(-5 * 365 // 7)
        rep["8_estimate"] = {
            "week_totals": totals,
            "median_per_7d": med,
            "pages_per_window": pages,
            "windows_5y": windows,
            "calls_5y": windows * pages,
            "days_at_300": round(windows * pages / 300, 1),
        }
        rep["calls"] = p.calls
    return rep


async def run_joint(key: str, out_dir: Path) -> dict:
    """5번 보충: cmmnCntrctYn이 아니라 corpList의 공동도급방식(공동·분담·혼합)으로 공동수급을 골라
    낙찰 행과 비교한다 (1차 실행에서 cmmnCntrctYn=Y가 1건뿐이었음)."""
    rep: dict[str, Any] = {}
    today = datetime.now(KST).replace(hour=0, minute=0, second=0, microsecond=0)
    end = today - timedelta(minutes=1)
    b7 = today - timedelta(days=7)
    async with httpx.AsyncClient() as http:
        p = Prober(http, key, out_dir)
        awards = (await p.window_all(AWARD_OP, b7, end)).get("items") or []
        awards += (
            await p.window_all(AWARD_OP, b7 - timedelta(days=7), b7 - timedelta(minutes=1))
        ).get("items") or []
        cts = (await p.window_all(CNTRCT_OP, today - timedelta(days=6), end, max_pages=3)).get(
            "items"
        ) or []
        by_no: dict[str, list[dict]] = {}
        for it in awards:
            by_no.setdefault(str(it.get("bidNtceNo")), []).append(it)
        cases, modes = [], Counter()
        for c in cts:
            corp = [x.split("^") for x in re.findall(r"\[([^\]]*)\]", str(c.get("corpList") or ""))]
            mode = {x[2] for x in corp if len(x) > 2}
            modes[f"rows={len(corp)}|modes={sorted(mode)}|cmmnYn={c.get('cmmnCntrctYn')}"] += 1
            if len(corp) < 2:
                continue
            aw = by_no.get(str(c.get("ntceNo") or "")[:13]) or by_no.get(
                str(c.get("ntceNo") or "")[:11]
            )
            if not aw:
                continue
            biznos = [x[9].strip() for x in corp if len(x) > 9]
            names = [x[3] for x in corp if len(x) > 3]
            cases.append(
                {
                    "members": len(corp),
                    "roles": [x[1] for x in corp],
                    "modes": sorted(mode),
                    "shares": [x[6] for x in corp if len(x) > 6],
                    "cmmnCntrctYn": c.get("cmmnCntrctYn"),
                    "award_rows": len(aw),
                    "award_bizno_idx": [
                        biznos.index(a.get("bidwinnrBizno"))
                        if a.get("bidwinnrBizno") in biznos
                        else None
                        for a in aw
                    ],
                    "award_name_idx": [
                        names.index(a.get("bidwinnrNm")) if a.get("bidwinnrNm") in names else None
                        for a in aw
                    ],
                    "award_name_has_sep": [
                        bool(re.search(r"[,/]|외\s*\d", str(a.get("bidwinnrNm")))) for a in aw
                    ],
                }
            )
        rep["contracts"] = len(cts)
        rep["corp_modes"] = modes.most_common(10)
        rep["joint_cases"] = cases[:8]
        rep["joint_case_count"] = len(cases)
        sep = [
            str(it.get("bidwinnrNm"))
            for it in awards
            if re.search(r"[,/]|외\s*\d", str(it.get("bidwinnrNm")))
        ]
        rep["award_names_with_sep_shapes"] = [
            re.sub(r"[가-힣A-Za-z0-9()]+", "X", s) for s in sep[:5]
        ]
        rep["calls"] = p.calls
    return rep


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env-file", action="append", required=True)
    ap.add_argument("--out-dir", required=True, help="응답·요약 저장 위치(저장소 밖)")
    ap.add_argument("--joint-only", action="store_true", help="5번(공동수급)만 다시 확인")
    args = ap.parse_args()
    if args.joint_only:
        env0: dict[str, Any] = {}
        for f in args.env_file:
            env0.update({k: v for k, v in dotenv_values(f).items() if v})
        key0 = env0.get("NARA_AWARD_API_KEY") or env0.get("NARA_API_KEY") or ""
        out0 = Path(args.out_dir)
        rep0 = asyncio.run(run_joint(key0, out0))
        t0 = json.dumps(rep0, ensure_ascii=False, indent=1, default=str).replace(key0, "***")
        (out0 / "summary_joint.json").write_text(t0, encoding="utf-8")
        print(t0)
        return
    env: dict[str, Any] = {}
    for f in args.env_file:
        env.update({k: v for k, v in dotenv_values(f).items() if v})
    key = env.get("NARA_AWARD_API_KEY") or env.get("NARA_API_KEY") or ""
    db_url = env["DATABASE_URL"]
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rep = asyncio.run(run(key, db_url, out))
    text_ = json.dumps(rep, ensure_ascii=False, indent=1, default=str)
    if key:
        text_ = text_.replace(key, "***")
    (out / "summary.json").write_text(text_, encoding="utf-8")
    print(text_)
    print(f"G2B calls={rep.get('calls')} (상한 {MAX_CALLS})")


if __name__ == "__main__":
    main()

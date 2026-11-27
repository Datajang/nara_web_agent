"""협상 공고 제안서평가 일시 [미확인] 확인 (2026-11-27).

협상에의한계약 공고는 개찰 뒤 결과(개찰완료)가 중앙값 8일 늦다(제안서평가 뒤 입력).
Open API에는 평가 일시가 없고 나라장터 웹 공고 상세(PNPE027_01)의 '입찰진행정보'에만 있다.
그 화면이 부르는 `selectItemAnncMngV.do`(POST JSON, 로그인·쿠키 없음)로
(a) 평가 일시를 받을 수 있는지 (b) 평가 일시와 개찰완료 입력 시각의 차이를 본다.

DB에서 개찰 30~120일 전·개찰완료가 있는 협상 공고를 무작위로 N건(기본 25) 뽑아 1초에 1건 부른다.
인자 `pps`를 주면 조달청이 공고한 것만(수요기관 자체 평가는 평가 일시가 비어 있다).
운영 DB를 읽기만 한다. 실행(운영, 사용자 요청 시):
  sudo -n -u nara env NARA_ENV_FILE=/etc/nara/nara.env HOME=/var/lib/nara \
    /opt/nara/venv/bin/python - pps < scripts/probe_eval_date.py
"""

from __future__ import annotations

import asyncio
import statistics
import sys
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import get_settings

URL = "https://www.g2b.go.kr/pn/pnp/pnpe/ItemBidPbac/selectItemAnncMngV.do"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
KST = timezone(timedelta(hours=9))
N = 25
SAMPLE = """
with b as (
  select bid_no, coalesce(raw->>'bidNtceOrd','000') ord, raw->>'opengDt' openg
  from bids where source='regular' and raw->>'sucsfbidMthdNm' like '%협상%'
    and raw->>'opengDt' ~ '^\\d{4}-'
    and (raw->>'opengDt')::timestamp
        between now() - interval '120 days' and now() - interval '30 days'
    and (not :pps or raw->>'ntceInsttNm' like '%조달청%')
)
select b.bid_no, b.ord, b.openg, min(s.input_at) done_at
from b join bid_opening_status s on s.bid_ntce_no=b.bid_no and s.bid_ntce_ord=b.ord
where s.status='개찰완료' and s.rbid_no='000'
group by b.bid_no, b.ord, b.openg order by random() limit :n
"""


def _kst(s: str | None) -> datetime | None:
    if not s:
        return None
    for fmt in ("%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=KST)
        except ValueError:
            continue
    return None


async def main() -> None:
    e = create_async_engine(get_settings().database_url)
    async with e.connect() as c:
        rows = (await c.execute(text(SAMPLE), {"n": N, "pps": "pps" in sys.argv[1:]})).all()
    await e.dispose()
    lags: list[float] = []
    missing = 0
    async with httpx.AsyncClient(timeout=20, headers={"User-Agent": UA}) as http:
        for no, ord_, openg, done_at in rows:
            body = {"dmItemMap": {"bidPbancNo": no, "bidPbancOrd": ord_}}
            r = await http.post(URL, json=body)
            j = r.json() if r.status_code == 200 else {}
            evl = _kst((j.get("dmEvlStepMap") or {}).get("evlDt"))
            row = next(
                (x for x in j.get("dmItemList1") or [] if x.get("subject") == "제안서평가"), None
            )
            mng = (j.get("dmEvlStepMap") or {}).get("evlMaagSeNm")
            if evl is None:
                missing += 1
                where = (row or {}).get("prgNm")
                print(f"{no}-{ord_} 개찰 {openg} 평가일시 없음 {r.status_code} {where} 주관={mng}")
            else:
                lag = (done_at - evl).total_seconds() / 3600
                lags.append(lag)
                at = f"{evl:%Y-%m-%d %H:%M}"
                print(f"{no}-{ord_} 개찰 {openg} 평가 {at} 주관 {mng} 결과-평가 {lag:+.1f}h")
            await asyncio.sleep(1)
    print(f"\n{len(rows)}건 중 평가일시 있음 {len(lags)}건, 없음 {missing}건")
    if lags:
        q = statistics.quantiles(lags, n=4, method="inclusive") if len(lags) >= 2 else lags
        print("결과-평가(시간) 최소", round(min(lags), 1), "p25·p50·p75", [round(x, 1) for x in q])
        print("최대", round(max(lags), 1), "평가 전 결과", sum(1 for x in lags if x < 0), "건")


asyncio.run(main())

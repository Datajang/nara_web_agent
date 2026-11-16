"""계약 수집기 `contracts`: 공동수급 구성 (SPEC §15.4 계약정보, P11).

계약정보는 등록일시(inqryDiv=1)나 통합계약번호로만 조회된다(공고번호 조회 없음, API 문서).
낙찰 응답만으로는 공동수급을 알 수 없으므로(probe 5번) 'is_joint인 낙찰만' 부를 수 없다 →
계약을 낙찰과 같은 날짜 7개 창으로 받아, `corpList` 방식 칸이 단독이 아닌 계약만 저장한다.

- corpList: `[순번^업체구분^공동도급방식^업체명^대표자명^국적^지분율^채권자명^담당자^사업자번호]`
  (probe 6번). 업체명·사업자번호·업체구분·방식·지분율만 읽는다. 대표자명·담당자는 읽지 않는다
- ntceNo: 신체계 13자리(차수 없음 → ord ''), 구체계 11자리+차수 2자리(→ 3자리), 빈 값은 건너뜀
- 커버리지: collector_coverage의 source='contracts' 한 행. 범위는 낙찰 수집 범위 안으로만
- 저장 뒤 같은 공고의 낙찰을 is_joint=true로 맞춘다(store.mark_joint). 낙찰이 나중에 와도 맞춘다
- 예산: 낙찰 몫(G2B_AWARDS_DAILY_BUDGET)을 낙찰 수집과 함께 쓴다. 실제 계약은 하루 약 4,300건
  (2026-11-16 실측: 14일 65,086건·67회)이라 낙찰보다 훨씬 많다 →
  증분은 최근 3일만 다시 받고, 백필은 한 번에 G2B_CONTRACTS_BACKFILL_CALLS(기본 100)회까지만
  (상한 도달은 정상 종료, 다음 실행에서 이어감). 낙찰 몫의 나머지는 경쟁 구도 온디맨드에 남는다
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.awards.collector import DAYS_PER_YEAR, load_settings, plan_backfill, plan_incremental
from app.awards.mapper import normalize_bizno
from app.awards.store import CHUNK, mark_joint
from app.collector import coverage
from app.collector.runner import RunResult, Store, _collect
from app.db.models import BidJointMember
from app.deps import Deps

SOURCE = "contracts"
AWARDS_SOURCE = "awards"
SOLO = "단독"
INCREMENTAL_SPAN = timedelta(days=3)  # 계약은 등록 뒤 거의 바뀌지 않는다
_ENTRY = re.compile(r"\[([^\[\]]*)\]")
_NEW_NO = re.compile(r"^[A-Z]\d{2}[A-Z]{2}[0-9A-Z]{8}$")  # R26BK01744163 (13자)
_OLD_NO = re.compile(r"^(\d{11})(\d{2})$")


@dataclass(frozen=True)
class Member:
    seq: int
    role: str | None  # 주계약업체·도급업체
    mode: str | None  # 단독·공동·분담·혼합방식
    name: str | None
    share: Decimal | None
    bizno: str | None


def parse_corp_list(raw: str | None) -> list[Member]:
    """corpList 문자열 → 구성원. 칸이 10개가 아니면 그 항목은 버린다."""
    out: list[Member] = []
    for m in _ENTRY.finditer(raw or ""):
        parts = m.group(1).split("^")
        if len(parts) != 10:
            continue
        try:
            share: Decimal | None = Decimal(parts[6]) if parts[6].strip() else None
        except InvalidOperation:
            share = None
        out.append(
            Member(
                seq=int(parts[0]) if parts[0].strip().isdigit() else 0,
                role=parts[1].strip() or None,
                mode=parts[2].strip() or None,
                name=parts[3].strip() or None,
                share=share,
                bizno=normalize_bizno(parts[9]),
            )
        )
    return out


def notice_key(ntce_no: str | None) -> tuple[str, str] | None:
    """계약 ntceNo → (낙찰 공고번호, 차수). 신체계는 차수 ''(모든 차수), 형식이 다르면 None."""
    s = (ntce_no or "").strip()
    if _NEW_NO.match(s):
        return s, ""
    if m := _OLD_NO.match(s):
        return m.group(1), f"0{m.group(2)}"
    return None


def is_joint(members: list[Member]) -> bool:
    return any(m.mode and m.mode != SOLO for m in members) and len(members) > 1


def to_member_rows(item: dict[str, Any]) -> list[dict[str, Any]]:
    """계약 1건 → bid_joint_members 행. 공동수급이 아니거나 공고와 이을 수 없으면 []."""
    key = notice_key(item.get("ntceNo"))
    members = parse_corp_list(item.get("corpList"))
    if key is None or not is_joint(members):
        return []
    lead = next((m.bizno for m in members if m.role == "주계약업체" and m.bizno), None)
    return [
        {
            "bid_ntce_no": key[0],
            "bid_ntce_ord": key[1],
            "bizno": lead,
            "member_bizno": m.bizno,
            "member_name": m.name,
            "role": m.role,
            "joint_mode": m.mode,
            "share": m.share,
        }
        for m in members
        if m.bizno is not None
    ]


async def upsert_members(s: AsyncSession, items: list[dict[str, Any]]) -> tuple[int, int]:
    best: dict[tuple[str, str, str], dict[str, Any]] = {}
    for it in items:
        for r in to_member_rows(it):
            best[(r["bid_ntce_no"], r["bid_ntce_ord"], r["member_bizno"])] = r
    values = [best[k] for k in sorted(best)]
    for i in range(0, len(values), CHUNK):
        ins = insert(BidJointMember).values(values[i : i + CHUNK])
        ex = ins.excluded
        await s.execute(
            ins.on_conflict_do_update(
                constraint="uq_bid_joint_members_bid_ntce_no_bid_ntce_ord_member_bizno",
                set_={
                    "bizno": ex.bizno,
                    "member_name": ex.member_name,
                    "role": ex.role,
                    "joint_mode": ex.joint_mode,
                    "share": ex.share,
                },
            )
        )
    marked = await mark_joint(s, {k[0] for k in best})
    return len(values), marked


def contract_store() -> Store:
    async def store(s: AsyncSession, items: list[dict[str, Any]]) -> tuple[int, int]:
        return await upsert_members(s, items)

    return store


async def backfill(deps: Deps, days: int | None = None) -> RunResult:
    """낙찰 수집 범위 안에서만 과거로(낙찰이 없는 기간의 공동수급은 쓸 데가 없다)."""
    years, _ = await load_settings(deps)
    now = deps.clock()
    start = now - timedelta(days=days if days is not None else years * DAYS_PER_YEAR)
    async with deps.db.session() as s:
        cov = await coverage.get(s, SOURCE)
        awards_cov = await coverage.get(s, AWARDS_SOURCE)
    if awards_cov is None:
        return RunResult(status="ok")
    start = max(start, awards_cov.covered_from)
    windows = plan_backfill(cov, start, now)
    if not windows:
        return RunResult(status="ok")
    return await _collect(
        deps,
        SOURCE,
        "backfill",
        windows,
        max_calls=deps.settings.g2b_contracts_backfill_calls,
        store=contract_store(),
        cap_status="ok",
    )


async def incremental(deps: Deps) -> RunResult:
    now = deps.clock()
    async with deps.db.session() as s:
        cov = await coverage.get(s, SOURCE)
    windows = plan_incremental(cov, now, INCREMENTAL_SPAN)
    return await _collect(deps, SOURCE, "incremental", windows, store=contract_store())

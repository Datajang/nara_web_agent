"""비교·경쟁사 레이더·관심 경쟁사 조회 (SPEC §15.5·§15.6, P10). 판정은 app.analysis.competitors.

- 비교 기간은 두 회사 모두 수집 완료된 기간이다. 낙찰 커버리지는 업체 구분 없이 하나라서
  P9의 Period(수집 완료 범위로 자른 기간)를 그대로 쓴다.
- 맞대결은 개찰 결과(bid_participants)를 조회해 본 공고만 셀 수 있다(P11에서 채움).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import false, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis.competitors import (
    FIELD_WEIGHT,
    MIN_CANDIDATE_AWARDS,
    ORG_WEIGHT,
    AwardFact,
    AwardKey,
)
from app.awards.service import Period, period_conds
from app.db.models import BidAward, BidParticipant, Company, WatchedCompany


async def load_facts(s: AsyncSession, bizno: str, p: Period) -> list[AwardFact]:
    if p.eff_from is None:
        return []
    rows = await s.execute(
        select(
            BidAward.bid_ntce_no,
            BidAward.bid_ntce_ord,
            BidAward.bid_clsfc_no,
            BidAward.rbid_no,
            BidAward.award_amount,
            BidAward.dminstt_cd,
            BidAward.fields,
            BidAward.g2b_award_rate,
            BidAward.award_ratio,
            BidAward.is_joint,
        )
        .where(*period_conds(bizno, p))
        .order_by(BidAward.id)
    )
    return [
        AwardFact((no, o, c, rb), amt, org, tuple(f or ()), rate, ratio, joint)
        for no, o, c, rb, amt, org, f, rate, ratio, joint in rows.all()
    ]


async def shared_notices(s: AsyncSession, us: str, them: str, p: Period) -> list[AwardKey]:
    """두 회사가 모두 개찰 결과에 있는 공고(그 공고의 낙찰이 비교 기간 안인 것만)."""
    if p.eff_from is None:
        return []
    bp = BidParticipant
    key = (bp.bid_ntce_no, bp.bid_ntce_ord, bp.bid_clsfc_no, bp.rbid_no)
    both = (
        select(*key)
        .where(bp.bizno.in_((us, them)))
        .group_by(*key)
        .having(func.count(func.distinct(bp.bizno)) == 2)
        .subquery()
    )
    rows = await s.execute(
        select(both.c.bid_ntce_no, both.c.bid_ntce_ord, both.c.bid_clsfc_no, both.c.rbid_no)
        .join(
            BidAward,
            (BidAward.bid_ntce_no == both.c.bid_ntce_no)
            & (BidAward.bid_ntce_ord == both.c.bid_ntce_ord)
            & (BidAward.bid_clsfc_no == both.c.bid_clsfc_no)
            & (BidAward.rbid_no == both.c.rbid_no),
        )
        .where(BidAward.registered_at >= p.eff_from, BidAward.registered_at < p.eff_to)
        .order_by(both.c.bid_ntce_no, both.c.bid_ntce_ord)
    )
    return [(a, b, c, d) for a, b, c, d in rows.all()]


@dataclass
class SharedOrg:
    dminstt_cd: str
    dminstt_name: str | None
    us: int
    them: int


async def shared_orgs(
    s: AsyncSession, us: str, them: str, p: Period, limit: int = 10
) -> list[SharedOrg]:
    """두 회사가 모두 낙찰한 수요기관 (합이 큰 순)."""
    if p.eff_from is None:
        return []
    n_us = func.count().filter(BidAward.bizno == us)
    n_them = func.count().filter(BidAward.bizno == them)
    rows = await s.execute(
        select(BidAward.dminstt_cd, func.max(BidAward.dminstt_name), n_us, n_them)
        .where(
            BidAward.bizno.in_((us, them)),
            BidAward.dminstt_cd.is_not(None),
            BidAward.registered_at >= p.eff_from,
            BidAward.registered_at < p.eff_to,
        )
        .group_by(BidAward.dminstt_cd)
        .having((n_us > 0) & (n_them > 0))
        .order_by((n_us + n_them).desc(), BidAward.dminstt_cd)
        .limit(limit)
    )
    return [SharedOrg(cd or "", name, int(a), int(b)) for cd, name, a, b in rows.all()]


# ---------- 경쟁사 레이더 ----------


@dataclass
class Candidate:
    bizno: str
    name: str
    award_count: int
    last_award_at: datetime | None
    org_overlap: float  # 0~1
    field_overlap: float  # 0~1
    overlap: float  # 0~100
    watched: bool


_CANDIDATES_SQL = """
WITH p AS (
  SELECT id, bizno, dminstt_cd, fields, registered_at FROM bid_awards
  WHERE bizno IS NOT NULL AND registered_at >= :f AND registered_at < :t {extra}
),
us AS (SELECT * FROM p WHERE bizno = :us),
us_total AS (SELECT count(*) AS n FROM us),
cand AS (
  SELECT bizno, count(*) AS n, max(registered_at) AS last_at FROM p
  WHERE bizno <> :us GROUP BY bizno HAVING count(*) >= :min_n
),
c_org AS (
  SELECT DISTINCT p.bizno, p.dminstt_cd FROM p JOIN cand USING (bizno)
  WHERE p.dminstt_cd IS NOT NULL
),
org_ov AS (
  SELECT c.bizno, count(*) AS n FROM us JOIN c_org c ON c.dminstt_cd = us.dminstt_cd
  GROUP BY c.bizno
),
c_tag AS (
  SELECT DISTINCT p.bizno, t.tag FROM p JOIN cand USING (bizno), unnest(p.fields) AS t(tag)
),
us_tag AS (SELECT us.id, t.tag FROM us, unnest(us.fields) AS t(tag)),
field_ov AS (
  SELECT c.bizno, count(DISTINCT ut.id) AS n FROM us_tag ut JOIN c_tag c ON c.tag = ut.tag
  GROUP BY c.bizno
),
scored AS (
  SELECT cand.bizno, cand.n, cand.last_at,
         coalesce(o.n, 0)::float / ut.n AS org_overlap,
         coalesce(fo.n, 0)::float / ut.n AS field_overlap
  FROM cand CROSS JOIN us_total ut
  LEFT JOIN org_ov o ON o.bizno = cand.bizno
  LEFT JOIN field_ov fo ON fo.bizno = cand.bizno
  WHERE ut.n > 0 AND (o.n IS NOT NULL OR fo.n IS NOT NULL)
)
SELECT s.bizno, c.name, s.n, s.last_at, s.org_overlap, s.field_overlap,
       (w.bizno IS NOT NULL) AS watched
FROM scored s JOIN companies c ON c.bizno = s.bizno
LEFT JOIN watched_companies w ON w.bizno = s.bizno
ORDER BY (:ow * s.org_overlap + :fw * s.field_overlap) DESC, s.n DESC, s.bizno
LIMIT :limit
"""


async def candidates(
    s: AsyncSession,
    us: str,
    p: Period,
    *,
    field_tag: str | None = None,
    org: str | None = None,
    limit: int = 20,
) -> list[Candidate]:
    """우리와 겹침도가 높은 업체 (§15.5). 낙찰 2건 미만은 뺀다. 필터는 두 회사 모두에 건다."""
    if p.eff_from is None:
        return []
    extra, params = "", {}
    if field_tag:
        extra += " AND fields @> ARRAY[CAST(:field AS text)]"
        params["field"] = field_tag
    if org:
        extra += " AND dminstt_cd = :org"
        params["org"] = org
    rows = await s.execute(
        text(_CANDIDATES_SQL.format(extra=extra)),
        {
            "f": p.eff_from,
            "t": p.eff_to,
            "us": us,
            "min_n": MIN_CANDIDATE_AWARDS,
            "ow": ORG_WEIGHT,
            "fw": FIELD_WEIGHT,
            "limit": limit,
            **params,
        },
    )
    out = []
    for bizno, name, n, last_at, org_ov, field_ov, watched in rows.all():
        score = round(100 * (ORG_WEIGHT * org_ov + FIELD_WEIGHT * field_ov), 1)
        out.append(
            Candidate(
                bizno, name, int(n), last_at, round(org_ov, 4), round(field_ov, 4), score, watched
            )
        )
    return out


# ---------- 관심 경쟁사 ----------


@dataclass
class Watched:
    bizno: str
    name: str
    added_at: datetime
    award_count: int
    last_award_at: datetime | None


async def list_watched(s: AsyncSession, p: Period) -> list[Watched]:
    counts: Any = (
        select(
            BidAward.bizno.label("bizno"),
            func.count().label("n"),
            func.max(BidAward.registered_at).label("last_at"),
        )
        .where(
            *(
                [BidAward.registered_at >= p.eff_from, BidAward.registered_at < p.eff_to]
                if p.eff_from is not None
                else [false()]
            )
        )
        .group_by(BidAward.bizno)
        .subquery()
    )
    rows = await s.execute(
        select(
            WatchedCompany.bizno,
            Company.name,
            WatchedCompany.added_at,
            counts.c.n,
            counts.c.last_at,
        )
        .join(Company, Company.bizno == WatchedCompany.bizno)
        .outerjoin(counts, counts.c.bizno == WatchedCompany.bizno)
        .order_by(WatchedCompany.added_at.desc(), WatchedCompany.bizno)
    )
    return [Watched(b, n, at, int(c or 0), last) for b, n, at, c, last in rows.all()]


async def is_watched(s: AsyncSession, bizno: str) -> bool:
    return await s.get(WatchedCompany, bizno) is not None


async def watch(s: AsyncSession, bizno: str, user_id: int) -> None:
    await s.execute(
        insert(WatchedCompany)
        .values(bizno=bizno, added_by=user_id)
        .on_conflict_do_nothing(index_elements=[WatchedCompany.bizno])
    )


async def unwatch(s: AsyncSession, bizno: str) -> None:
    row = await s.get(WatchedCompany, bizno)
    if row is not None:
        await s.delete(row)

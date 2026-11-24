"""비교·경쟁사 레이더·관심 경쟁사 조회 (SPEC §15.5·§15.6, P10). 판정은 app.analysis.competitors.

- 비교 기간은 두 회사 모두 수집 완료된 기간이다. 낙찰 커버리지는 업체 구분 없이 하나라서
  P9의 Period(수집 완료 범위로 자른 기간)를 그대로 쓴다.
- 맞대결은 개찰 결과(bid_participants)를 조회해 본 공고만 셀 수 있다(공고 상세 '경쟁 구도'가 채움).
- 공동수급 파트너는 계약정보(bid_joint_members)를 수집한 기간만 있다(P11 contracts 수집기).
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
from app.db.models import (
    BidAward,
    BidJointMember,
    BidParticipant,
    Company,
    User,
    WatchedCompany,
)


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


# 분야·기관 필터가 있을 때: 걸리는 낙찰이 적어(수천~수만 건) 한 번에 계산한다.
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
LEFT JOIN watched_companies w ON w.bizno = s.bizno AND w.user_id = :uid
ORDER BY (:ow * s.org_overlap + :fw * s.field_overlap) DESC, s.n DESC, s.bizno
LIMIT :limit
"""

# 필터가 없을 때(성능, 2026-11-24): 위 쿼리는 6년 낙찰 63만 건 전체로 업체×기관·업체×분야를
# 만들어 3.6초가 걸렸다. 점수에 쓰이는 건 우리 기관·우리 분야에 걸린 낙찰뿐이라 그것만 색인으로
# 고르고(hit), 낙찰 건수(최소 건수·동점 순서)는 점수 순으로 화면에 필요한 만큼만 센다. 결과는 같다.
_OVERLAP_SQL = """
WITH us AS (
  SELECT id, dminstt_cd, fields FROM bid_awards
  WHERE bizno = :us AND registered_at >= :f AND registered_at < :t
),
us_total AS (SELECT count(*) AS n FROM us),
us_org AS (
  SELECT dminstt_cd, count(*) AS n FROM us WHERE dminstt_cd IS NOT NULL GROUP BY dminstt_cd
),
us_tag AS (SELECT us.id, t.tag FROM us, unnest(us.fields) AS t(tag)),
hit AS (
  SELECT bizno, dminstt_cd, fields FROM bid_awards
  WHERE bizno IS NOT NULL AND bizno <> :us AND registered_at >= :f AND registered_at < :t
    AND (dminstt_cd = ANY(ARRAY(SELECT dminstt_cd FROM us_org))
         OR fields && ARRAY(SELECT DISTINCT tag FROM us_tag))
),
org_ov AS (
  SELECT h.bizno, sum(o.n) AS n
  FROM (SELECT DISTINCT bizno, dminstt_cd FROM hit) h JOIN us_org o USING (dminstt_cd)
  GROUP BY h.bizno
),
c_tag AS (SELECT DISTINCT h.bizno, t.tag FROM hit h, unnest(h.fields) AS t(tag)),
field_ov AS (
  SELECT c.bizno, count(DISTINCT ut.id) AS n FROM us_tag ut JOIN c_tag c ON c.tag = ut.tag
  GROUP BY c.bizno
),
scored AS (
  SELECT coalesce(o.bizno, fo.bizno) AS bizno,
         coalesce(o.n, 0)::float / ut.n AS org_overlap,
         coalesce(fo.n, 0)::float / ut.n AS field_overlap
  FROM org_ov o FULL JOIN field_ov fo ON fo.bizno = o.bizno CROSS JOIN us_total ut
  WHERE ut.n > 0
)
SELECT bizno, org_overlap, field_overlap, :ow * org_overlap + :fw * field_overlap AS score
FROM scored ORDER BY score DESC, bizno
"""

_COUNTS_SQL = """
SELECT a.bizno, c.name, count(*) AS n, max(a.registered_at) AS last_at,
       (w.bizno IS NOT NULL) AS watched
FROM bid_awards a
JOIN companies c ON c.bizno = a.bizno
LEFT JOIN watched_companies w ON w.bizno = a.bizno AND w.user_id = :uid
WHERE a.bizno = ANY(:b) AND a.registered_at >= :f AND a.registered_at < :t
GROUP BY a.bizno, c.name, w.bizno
HAVING count(*) >= :min_n
"""


def _candidate(
    bizno: str,
    name: str,
    n: int,
    last_at: datetime | None,
    org_ov: float,
    field_ov: float,
    watched: bool,
) -> Candidate:
    score = round(100 * (ORG_WEIGHT * org_ov + FIELD_WEIGHT * field_ov), 1)
    return Candidate(
        bizno, name, int(n), last_at, round(org_ov, 4), round(field_ov, 4), score, bool(watched)
    )


async def candidates(
    s: AsyncSession,
    us: str,
    p: Period,
    *,
    user_id: int | None = None,  # 관심 여부를 볼 계정(없으면 모두 False)
    field_tag: str | None = None,
    org: str | None = None,
    limit: int = 20,
    first_chunk: int = 100,
) -> list[Candidate]:
    """우리와 겹침도가 높은 업체 (§15.5). 낙찰 2건 미만은 뺀다. 필터는 두 회사 모두에 건다.

    순서: 겹침도 높은 순 → 낙찰 많은 순 → 사업자번호 순.
    """
    if p.eff_from is None:
        return []
    if not field_tag and not org:
        return await _candidates_unfiltered(s, us, p, user_id, limit, first_chunk)
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
            "uid": user_id,
            **params,
        },
    )
    return [_candidate(*r) for r in rows.all()]


async def _candidates_unfiltered(
    s: AsyncSession, us: str, p: Period, user_id: int | None, limit: int, first_chunk: int
) -> list[Candidate]:
    period = {"f": p.eff_from, "t": p.eff_to}
    ranked = (
        await s.execute(
            text(_OVERLAP_SQL), {"us": us, "ow": ORG_WEIGHT, "fw": FIELD_WEIGHT, **period}
        )
    ).all()
    out: list[Candidate] = []
    i, chunk = 0, max(first_chunk, 1)
    while i < len(ranked) and len(out) < limit:
        # 동점 묶음은 끊지 않는다 → 묶음 안에서 낙찰 수로 다시 줄 세워도 전체 순서와 같다
        j = min(i + chunk, len(ranked))
        while j < len(ranked) and ranked[j].score == ranked[j - 1].score:
            j += 1
        part = ranked[i:j]
        args = {"b": [r.bizno for r in part], "uid": user_id, "min_n": MIN_CANDIDATE_AWARDS}
        got = {c.bizno: c for c in await s.execute(text(_COUNTS_SQL), {**args, **period})}
        batch = [(r, got[r.bizno]) for r in part if r.bizno in got]
        batch.sort(key=lambda rc: (-rc[0].score, -rc[1].n, rc[0].bizno))
        out += [
            _candidate(r.bizno, c.name, c.n, c.last_at, r.org_overlap, r.field_overlap, c.watched)
            for r, c in batch
        ]
        i, chunk = j, chunk * 2
    return out[:limit]


# ---------- 관심 경쟁사 ----------


@dataclass
class Watched:
    bizno: str
    name: str
    added_at: datetime  # 팀 목록이면 가장 최근에 담은 시각
    award_count: int
    last_award_at: datetime | None
    added_by: list[str]  # 담은 사람 이름(팀 목록에서만 채운다)


async def list_watched(
    s: AsyncSession, p: Period, user_ids: list[int], *, with_names: bool = False
) -> list[Watched]:
    """user_ids가 담은 관심 경쟁사. 여러 명이면 회사별로 묶고 담은 사람을 모은다 (2026-11-23)."""
    if not user_ids:
        return []
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
    who = func.coalesce(func.nullif(User.display_name, ""), func.split_part(User.email, "@", 1))
    added_at = func.max(WatchedCompany.added_at)
    rows = await s.execute(
        select(
            WatchedCompany.bizno,
            Company.name,
            added_at,
            func.max(counts.c.n),
            func.max(counts.c.last_at),
            func.array_agg(who),
        )
        .join(Company, Company.bizno == WatchedCompany.bizno)
        .join(User, User.id == WatchedCompany.user_id)
        .outerjoin(counts, counts.c.bizno == WatchedCompany.bizno)
        .where(WatchedCompany.user_id.in_(user_ids))
        .group_by(WatchedCompany.bizno, Company.name)
        .order_by(added_at.desc(), WatchedCompany.bizno)
    )
    return [
        Watched(b, n, at, int(c or 0), last, sorted(names) if with_names else [])
        for b, n, at, c, last, names in rows.all()
    ]


async def is_watched(s: AsyncSession, bizno: str, user_id: int) -> bool:
    return await s.get(WatchedCompany, (user_id, bizno)) is not None


async def watch(s: AsyncSession, bizno: str, user_id: int) -> None:
    await s.execute(
        insert(WatchedCompany)
        .values(bizno=bizno, user_id=user_id)
        .on_conflict_do_nothing(index_elements=[WatchedCompany.user_id, WatchedCompany.bizno])
    )


async def unwatch(s: AsyncSession, bizno: str, user_id: int) -> None:
    row = await s.get(WatchedCompany, (user_id, bizno))
    if row is not None:
        await s.delete(row)


@dataclass
class JointPartner:
    bizno: str
    name: str
    count: int  # 함께 공동수급한 낙찰 공고 수(기간 안)


JOINT_TOP = 5


async def joint_partners(
    s: AsyncSession, bizno: str, p: Period, limit: int = JOINT_TOP
) -> list[JointPartner]:
    """bizno가 구성원(주계약·도급)인 공동수급 낙찰에서 함께한 업체.

    많은 순, 같으면 사업자번호 순.
    """
    if p.eff_from is None or p.eff_to is None:
        return []
    me, other = BidJointMember.__table__.alias("me"), BidJointMember.__table__.alias("other")
    a = BidAward.__table__
    n = func.count(func.distinct(a.c.bid_ntce_no + "-" + a.c.bid_ntce_ord)).label("n")
    name = func.coalesce(
        func.max(Company.name), func.max(other.c.member_name), other.c.member_bizno
    )
    q = (
        select(other.c.member_bizno, name, n)
        .select_from(me)
        .join(
            other,
            (other.c.bid_ntce_no == me.c.bid_ntce_no)
            & (other.c.bid_ntce_ord == me.c.bid_ntce_ord)
            & (other.c.member_bizno != me.c.member_bizno),
        )
        .join(
            a,
            (a.c.bid_ntce_no == me.c.bid_ntce_no)
            & ((me.c.bid_ntce_ord == "") | (a.c.bid_ntce_ord == me.c.bid_ntce_ord)),
        )
        .outerjoin(Company, Company.bizno == other.c.member_bizno)
        .where(
            me.c.member_bizno == bizno,
            a.c.registered_at >= p.eff_from,
            a.c.registered_at < p.eff_to,
        )
        .group_by(other.c.member_bizno)
        .order_by(n.desc(), other.c.member_bizno)
        .limit(limit)
    )
    return [JointPartner(b, str(nm), int(c)) for b, nm, c in (await s.execute(q)).all()]

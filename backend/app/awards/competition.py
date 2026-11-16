"""공고별 경쟁 구도 (SPEC §15.1 C5, §15.7 '경쟁 구도' 탭, P11). DB를 읽고 개찰 결과만 온디맨드.

- 같은 수요기관(코드, 없으면 이름)의 낙찰 중 공고명이 비슷한 것을 고른다. 비슷함은 공고명
  글자 2-gram 다이스 계수(띄어쓰기·숫자·흔한 말 제외)로 재고, 분야 태그가 겹치면 더한다.
  같은 입력 → 같은 순서
- 분포: 비슷한 낙찰(최대 SIMILAR_POOL건)의 낙찰률(G2B)·낙찰금액/추정가격 최소·중앙·최대.
  값이 있는 건만
- 참가 업체 점수: 이 공고(낙찰이 있으면)와 보여 줄 과거 낙찰의 개찰 결과(participants.ensure)
- 우리 회사: 이 수요기관 낙찰 수, 불러온 개찰 결과 중 참가·낙찰 수
투찰가 추천·낙찰 가능성은 만들지 않는다(§15.1 비목표).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from statistics import median

from sqlalchemy import func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.awards import participants as parts
from app.awards.fields import classify
from app.awards.service import Period
from app.db.models import Bid, BidAward, BidParticipant

SIMILAR_MIN = 0.2  # 이 값 이상이거나 분야 태그가 겹치면 '비슷한 사업'
FIELD_BONUS = 0.2
CANDIDATE_LIMIT = 500  # 같은 수요기관의 최근 낙찰 중 비교할 수
SIMILAR_POOL = 50  # 분포를 낼 비슷한 낙찰 수
_NOISE = re.compile(r"[\s\d\W_]+")
_STOP = ("용역", "사업", "위탁", "연간", "년도", "차년도", "및")


def _shape(title: str) -> str:
    t = re.sub(r"\(.*?\)|\[.*?\]", "", title)
    for w in _STOP:
        t = t.replace(w, "")
    return _NOISE.sub("", t).lower()


def bigrams(title: str) -> frozenset[str]:
    s = _shape(title)
    return frozenset(s[i : i + 2] for i in range(len(s) - 1))


def similarity(a: str, b: str) -> float:
    """공고명 글자 2-gram 다이스 계수(0~1)."""
    x, y = bigrams(a), bigrams(b)
    if not x or not y:
        return 0.0
    return round(2 * len(x & y) / (len(x) + len(y)), 4)


@dataclass(frozen=True)
class Target:
    bid_no: str
    org_cd: str | None
    org_name: str | None
    title: str


def target_of(bid: Bid) -> Target:
    raw = bid.raw or {}
    cd = str(raw.get("dminsttCd") or "").strip() or None
    name = str(raw.get("dminsttNm") or "").strip() or bid.org_name
    return Target(bid_no=bid.bid_no, org_cd=cd, org_name=name, title=bid.title)


@dataclass
class Scored:
    award: BidAward
    score: float


@dataclass(frozen=True)
class Spread:
    n: int
    min: float
    median: float
    max: float


def spread(values: list[float]) -> Spread | None:
    if not values:
        return None
    return Spread(len(values), min(values), round(median(values), 5), max(values))


def _org_filter(t: Target) -> list[object]:
    if t.org_cd:
        return [BidAward.dminstt_cd == t.org_cd]
    if t.org_name:
        return [BidAward.dminstt_name == t.org_name]
    return []


async def this_awards(s: AsyncSession, t: Target) -> list[BidAward]:
    """이 공고의 낙찰(개찰이 끝났으면). 최신 차수 먼저."""
    q = (
        select(BidAward)
        .where(BidAward.bid_ntce_no == t.bid_no)
        .order_by(BidAward.bid_ntce_ord.desc(), BidAward.bid_clsfc_no, BidAward.rbid_no.desc())
    )
    return list((await s.execute(q)).scalars())


async def similar_awards(
    s: AsyncSession, t: Target, p: Period, keywords: dict[str, list[str]]
) -> list[Scored]:
    conds = _org_filter(t)
    if not conds or p.eff_from is None or p.eff_to is None:
        return []
    q = (
        select(BidAward)
        .where(
            *conds,  # type: ignore[arg-type]
            BidAward.bid_ntce_no != t.bid_no,
            BidAward.registered_at >= p.eff_from,
            BidAward.registered_at < p.eff_to,
        )
        .order_by(BidAward.registered_at.desc(), BidAward.id.desc())
        .limit(CANDIDATE_LIMIT)
    )
    my_fields = set(classify(t.title, keywords))
    out: list[Scored] = []
    for a in (await s.execute(q)).scalars():
        sim = similarity(t.title, a.title)
        shared = bool(my_fields & set(a.fields or []))
        if sim >= SIMILAR_MIN or shared:
            out.append(Scored(a, round(sim + (FIELD_BONUS if shared else 0.0), 4)))
    out.sort(key=lambda x: (-x.score, -x.award.registered_at.timestamp(), x.award.id))
    return out[:SIMILAR_POOL]


def distributions(rows: list[Scored]) -> tuple[Spread | None, Spread | None]:
    rates = [float(r.award.g2b_award_rate) for r in rows if r.award.g2b_award_rate is not None]
    ratios = [float(r.award.award_ratio) for r in rows if r.award.award_ratio is not None]
    return spread(rates), spread(ratios)


AwardKey = tuple[str, str, str, str]


def key_of(a: BidAward) -> AwardKey:
    return (a.bid_ntce_no, a.bid_ntce_ord, a.bid_clsfc_no, a.rbid_no)


async def participants_of(
    s: AsyncSession, keys: list[AwardKey]
) -> dict[AwardKey, list[BidParticipant]]:
    if not keys:
        return {}
    bp = BidParticipant
    rows = await s.execute(
        select(bp)
        .where(tuple_(bp.bid_ntce_no, bp.bid_ntce_ord, bp.bid_clsfc_no, bp.rbid_no).in_(keys))
        .order_by(bp.rank.asc().nulls_last(), bp.total_score.desc().nulls_last(), bp.bizno)
    )
    out: dict[AwardKey, list[BidParticipant]] = {}
    for r in rows.scalars():
        out.setdefault((r.bid_ntce_no, r.bid_ntce_ord, r.bid_clsfc_no, r.rbid_no), []).append(r)
    return out


@dataclass
class UsHistory:
    org_awards: int = 0  # 이 수요기관에서 우리가 낙찰한 수(기간 안)
    participated: int = 0  # 불러온 개찰 결과 중 우리가 참가한 이 수요기관 공고 수
    won: int = 0  # 그중 우리가 낙찰한 수
    notices: list[str] = field(default_factory=list)


async def us_history(s: AsyncSession, t: Target, p: Period, us: str) -> UsHistory:
    conds = _org_filter(t)
    out = UsHistory()
    if not conds or p.eff_from is None or p.eff_to is None:
        return out
    in_period = (BidAward.registered_at >= p.eff_from, BidAward.registered_at < p.eff_to)
    out.org_awards = int(
        await s.scalar(
            select(func.count()).where(*conds, *in_period, BidAward.bizno == us)  # type: ignore[arg-type]
        )
        or 0
    )
    bp = BidParticipant
    rows = await s.execute(
        select(BidAward.bid_ntce_no, BidAward.bizno)
        .join(
            bp,
            (bp.bid_ntce_no == BidAward.bid_ntce_no)
            & (bp.bid_ntce_ord == BidAward.bid_ntce_ord)
            & (bp.bid_clsfc_no == BidAward.bid_clsfc_no)
            & (bp.rbid_no == BidAward.rbid_no),
        )
        .where(*conds, *in_period, bp.bizno == us)  # type: ignore[arg-type]
        .order_by(BidAward.registered_at.desc())
    )
    for no, winner in rows.all():
        out.participated += 1
        out.won += winner == us
        out.notices.append(no)
    return out


def notices_to_load(this: list[BidAward], shown: list[Scored]) -> list[parts.Notice]:
    """개찰 결과를 불러올 공고(차수), 우선순위 순: 이 공고 → 보여 줄 과거 낙찰."""
    keys = [(a.bid_ntce_no, a.bid_ntce_ord) for a in this[:1]]
    keys += [(r.award.bid_ntce_no, r.award.bid_ntce_ord) for r in shown]
    return list(dict.fromkeys(keys))

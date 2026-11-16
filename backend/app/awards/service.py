"""낙찰 조회 서비스 (SPEC §15.6·§15.7, P9). API와 (P11) 어시스턴트 도구가 같은 함수를 쓴다.

- 기간 축은 등록일시(registered_at)다. 수집 커버리지가 같은 축이라
  '0건'과 '수집 중'을 정확히 가른다.
- 요청 기간 중 수집이 끝나지 않은 부분은 세지 않고 collecting=true로 알린다(0건으로 보이지 않게).
- 통계는 모두 SQL이 계산한다(§15.1 원칙 1). 사업자번호가 없는 낙찰은 업체 통계에서 빠진다.
"""

from __future__ import annotations

import base64
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from sqlalchemy import ColumnElement, and_, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.awards.fields import clean_keywords
from app.awards.mapper import normalize_bizno, normalize_name
from app.collector import coverage
from app.db.models import Bid, BidAward, Company, OrgSettings, UsageLog
from app.g2b.client import AWARD_SOURCES

KST = timezone(timedelta(hours=9))
SOURCE = "awards"
DAYS_PER_YEAR = 365
# 수집기는 하루 한 번이라 covered_to가 하루쯤 늦을 수 있다. 이만큼은 '다 받은 것'으로 본다
TO_SLACK = timedelta(hours=36)
FROM_SLACK = timedelta(hours=1)
TOP_ORGS = 10


@dataclass(frozen=True)
class OrgConfig:
    our_bizno: str | None
    our_name: str | None
    field_keywords: dict[str, list[str]]
    backfill_years: int
    updated_at: datetime | None


async def load_org(s: AsyncSession, default_years: int) -> OrgConfig:
    row = await s.get(OrgSettings, 1)
    if row is None:
        return OrgConfig(None, None, {}, default_years, None)
    return OrgConfig(
        row.our_bizno,
        row.our_name,
        clean_keywords(row.field_keywords),
        row.backfill_years,
        row.updated_at,
    )


def kst_date(dt: datetime) -> date:
    return dt.astimezone(KST).date()


def kst_start(d: date) -> datetime:
    return datetime.combine(d, time(), KST)


@dataclass(frozen=True)
class Period:
    """요청 기간(req_*)과 실제로 센 기간(eff_*). eff가 없으면 수집된 부분이 없다."""

    req_from: datetime
    req_to: datetime
    eff_from: datetime | None
    eff_to: datetime | None
    collecting: bool

    def covers(self, start: datetime, end: datetime) -> bool:
        """[start, end)가 센 기간 안에 온전히 있는가."""
        if self.eff_from is None or self.eff_to is None:
            return False
        return self.eff_from - FROM_SLACK <= start and end <= self.eff_to + TO_SLACK


def resolve_period(
    cov: coverage.Coverage | None,
    target_from: datetime,
    now: datetime,
    date_from: date | None = None,
    date_to: date | None = None,
) -> Period:
    req_from = max(kst_start(date_from), target_from) if date_from else target_from
    req_to = min(kst_start(date_to + timedelta(days=1)), now) if date_to else now
    if req_to < req_from:
        req_to = req_from
    if cov is None:
        return Period(req_from, req_to, None, None, True)
    eff_from, eff_to = max(req_from, cov.covered_from), min(req_to, cov.covered_to)
    collecting = req_from < cov.covered_from - FROM_SLACK or req_to > cov.covered_to + TO_SLACK
    if eff_to <= eff_from:
        return Period(req_from, req_to, None, None, True)
    return Period(req_from, req_to, eff_from, eff_to, collecting)


async def award_period(
    s: AsyncSession,
    years: int,
    now: datetime,
    date_from: date | None = None,
    date_to: date | None = None,
) -> tuple[Period, coverage.Coverage | None]:
    cov = await coverage.get(s, SOURCE)
    target_from = now - timedelta(days=years * DAYS_PER_YEAR)
    return resolve_period(cov, target_from, now, date_from, date_to), cov


# ---------- 수집 현황 (GET /company) ----------


@dataclass
class YearProgress:
    year: int
    ratio: float  # 0~1, 그 해의 목표 구간 중 수집된 비율


def year_progress(
    cov: coverage.Coverage | None, target_from: datetime, now: datetime
) -> list[YearProgress]:
    out = []
    for y in range(kst_date(target_from).year, kst_date(now).year + 1):
        start = max(kst_start(date(y, 1, 1)), target_from)
        end = min(kst_start(date(y + 1, 1, 1)), now)
        if end <= start:
            continue
        got = timedelta(0)
        if cov is not None:
            lo, hi = max(start, cov.covered_from), min(end, cov.covered_to + TO_SLACK)
            got = max(hi - lo, timedelta(0))
        out.append(YearProgress(y, round(min(1.0, got / (end - start)), 3)))
    return out


async def award_calls_today(s: AsyncSession, now: datetime) -> int:
    start = kst_start(kst_date(now))
    used = await s.scalar(
        select(func.coalesce(func.sum(UsageLog.g2b_calls), 0)).where(
            UsageLog.created_at >= start,
            UsageLog.cache["source"].astext.in_(sorted(AWARD_SOURCES)),
        )
    )
    return int(used or 0)


async def unidentified_count(s: AsyncSession) -> int:
    return int(await s.scalar(select(func.count()).where(BidAward.bizno.is_(None))) or 0)


# ---------- 회사 이름 찾기 ----------


async def lookup_name(s: AsyncSession, bizno: str) -> tuple[str | None, int]:
    """수집된 낙찰에서 이 사업자번호의 이름(가장 최근 상호)과 낙찰 수."""
    company = await s.get(Company, bizno)
    if company is None:
        return None, 0
    n = await s.scalar(select(func.count()).where(BidAward.bizno == bizno))
    return company.name, int(n or 0)


# ---------- 요약 ----------


@dataclass
class YearRow:
    year: int
    count: int | None  # None = 그 해 일부·전부가 아직 수집 중이라 세지 않음
    amount_sum: int | None
    collecting: bool


@dataclass
class OrgRow:
    dminstt_cd: str | None
    dminstt_name: str | None
    count: int
    amount_sum: int


@dataclass
class FieldRow:
    field: str
    count: int


@dataclass
class Summary:
    count: int = 0
    amount_sum: int = 0
    amount_avg: int | None = None
    org_count: int = 0
    g2b_rate_median: float | None = None
    ratio_median: float | None = None
    ratio_known: int = 0  # 낙찰금액/추정가격을 계산할 수 있었던 건수
    joint_count: int = 0
    first_at: datetime | None = None
    last_at: datetime | None = None
    by_year: list[YearRow] = field(default_factory=list)
    by_org: list[OrgRow] = field(default_factory=list)
    by_field: list[FieldRow] = field(default_factory=list)


def period_conds(bizno: str, p: Period) -> list[ColumnElement[bool]]:
    """이 업체 · 센 기간(등록일시) 조건."""
    return [
        BidAward.bizno == bizno,
        BidAward.registered_at >= p.eff_from,
        BidAward.registered_at < p.eff_to,
    ]


async def summarize(s: AsyncSession, bizno: str, p: Period) -> Summary:
    out = Summary()
    if p.eff_from is not None:
        row = (
            await s.execute(
                select(
                    func.count(),
                    func.coalesce(func.sum(BidAward.award_amount), 0),
                    func.count(func.distinct(BidAward.dminstt_cd)),
                    func.percentile_cont(0.5).within_group(BidAward.g2b_award_rate),
                    func.percentile_cont(0.5).within_group(BidAward.award_ratio),
                    func.count(BidAward.award_ratio),
                    func.count().filter(BidAward.is_joint),
                    func.min(BidAward.registered_at),
                    func.max(BidAward.registered_at),
                ).where(*period_conds(bizno, p))
            )
        ).one()
        (n, total, orgs, rate_med, ratio_med, ratio_n, joint, first, last) = row
        out.count, out.amount_sum, out.org_count = int(n), int(total), int(orgs)
        out.amount_avg = round(out.amount_sum / out.count) if out.count else None
        out.g2b_rate_median = round(float(rate_med), 3) if rate_med is not None else None
        out.ratio_median = round(float(ratio_med), 5) if ratio_med is not None else None
        out.ratio_known, out.joint_count = int(ratio_n), int(joint)
        out.first_at, out.last_at = first, last
        out.by_org = [
            OrgRow(cd, name, int(c), int(a or 0))
            for cd, name, c, a in (
                await s.execute(
                    select(
                        BidAward.dminstt_cd,
                        func.max(BidAward.dminstt_name),
                        func.count(),
                        func.coalesce(func.sum(BidAward.award_amount), 0),
                    )
                    .where(*period_conds(bizno, p))
                    .group_by(BidAward.dminstt_cd)
                    .order_by(func.count().desc(), func.max(BidAward.dminstt_name))
                    .limit(TOP_ORGS)
                )
            ).all()
        ]
        tag = func.unnest(BidAward.fields).label("tag")
        sub = select(tag).where(*period_conds(bizno, p)).subquery()
        out.by_field = [
            FieldRow(t, int(c))
            for t, c in (
                await s.execute(
                    select(sub.c.tag, func.count())
                    .group_by(sub.c.tag)
                    .order_by(func.count().desc(), sub.c.tag)
                )
            ).all()
        ]
    out.by_year = await count_by_year(s, bizno, p)
    return out


async def count_by_year(s: AsyncSession, bizno: str, p: Period) -> list[YearRow]:
    counted: dict[int, tuple[int, int]] = {}
    if p.eff_from is not None:
        year = func.extract("year", func.timezone("Asia/Seoul", BidAward.registered_at))
        counted = {
            int(y): (int(c), int(a or 0))
            for y, c, a in (
                await s.execute(
                    select(year, func.count(), func.coalesce(func.sum(BidAward.award_amount), 0))
                    .where(*period_conds(bizno, p))
                    .group_by(year)
                )
            ).all()
        }
    rows = []
    for y in range(kst_date(p.req_from).year, kst_date(p.req_to).year + 1):
        start = max(kst_start(date(y, 1, 1)), p.req_from)
        end = min(kst_start(date(y + 1, 1, 1)), p.req_to)
        if end <= start:
            continue
        done = p.covers(start, end)
        c, a = counted.get(y, (0, 0))
        if done:
            rows.append(YearRow(y, c, a, False))
        else:  # 일부만 수집된 해: 센 만큼만 보여 주되 '수집 중'을 붙인다(0건으로 단정하지 않음)
            rows.append(YearRow(y, c or None, a or None, True))
    return rows


# ---------- 목록 ----------


@dataclass
class AwardItem:
    award: BidAward
    bid_id: int | None  # 같은 공고가 bids에 있으면 상세 화면으로 잇는다


def encode_cursor(registered_at: datetime, award_id: int) -> str:
    raw = f"{registered_at.isoformat()}|{award_id}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, int] | None:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
        ts, award_id = raw.split("|")
        return datetime.fromisoformat(ts), int(award_id)
    except (ValueError, UnicodeDecodeError):
        return None


@dataclass
class AwardPage:
    items: list[AwardItem]
    total: int
    next_cursor: str | None


async def list_awards(
    s: AsyncSession,
    bizno: str,
    p: Period,
    *,
    field_tag: str | None = None,
    org: str | None = None,
    cursor: tuple[datetime, int] | None = None,
    limit: int = 50,
) -> AwardPage:
    if p.eff_from is None:
        return AwardPage([], 0, None)
    conds: list[Any] = []
    if field_tag:
        conds.append(BidAward.fields.contains([field_tag]))  # @> — GIN 색인
    if org:
        conds.append(BidAward.dminstt_cd == org)
    total = await s.scalar(
        select(func.count()).select_from(BidAward).where(*period_conds(bizno, p), *conds)
    )
    page_conds = list(conds)
    if cursor is not None:
        ts, last_id = cursor
        page_conds.append(
            or_(
                BidAward.registered_at < ts,
                and_(BidAward.registered_at == ts, BidAward.id < last_id),
            )
        )
    stmt = (
        select(BidAward, Bid.id)
        .where(*period_conds(bizno, p))
        .outerjoin(Bid, Bid.bid_key == literal("regular:") + BidAward.bid_ntce_no)
        .where(*page_conds)
        .order_by(BidAward.registered_at.desc(), BidAward.id.desc())
        .limit(limit + 1)
    )
    rows = (await s.execute(stmt)).all()
    items = [AwardItem(a, bid_id) for a, bid_id in rows[:limit]]
    nxt = (
        encode_cursor(items[-1].award.registered_at, items[-1].award.id)
        if len(rows) > limit
        else None
    )
    return AwardPage(items, int(total or 0), nxt)


# ---------- 업체 검색 ----------

_LIKE_ESCAPE = re.compile(r"([\\%_])")


@dataclass
class CompanyHit:
    bizno: str
    name: str
    award_count: int
    last_award_at: datetime | None


def search_key(q: str) -> tuple[str, str] | None:
    """('bizno', 번호) 또는 ('name', 정규화한 이름). 너무 짧으면 None."""
    digits = re.sub(r"[\s-]", "", q)
    if digits.isdigit():
        b = normalize_bizno(digits)
        return ("bizno", b) if b else None
    norm = normalize_name(q)
    return ("name", norm) if len(norm) >= 2 else None


async def search_companies(
    s: AsyncSession, key: tuple[str, str], limit: int = 20
) -> list[CompanyHit]:
    kind, value = key
    counts = (
        select(
            BidAward.bizno.label("bizno"),
            func.count().label("n"),
            func.max(BidAward.registered_at).label("last_at"),
        )
        .group_by(BidAward.bizno)
        .subquery()
    )
    stmt = select(Company.bizno, Company.name, counts.c.n, counts.c.last_at).outerjoin(
        counts, counts.c.bizno == Company.bizno
    )
    if kind == "bizno":
        stmt = stmt.where(Company.bizno == value)
    else:
        pattern = "%" + _LIKE_ESCAPE.sub(r"\\\1", value) + "%"
        stmt = stmt.where(Company.name_norm.like(pattern, escape="\\"))
    stmt = stmt.order_by(
        func.coalesce(counts.c.n, 0).desc(), func.length(Company.name_norm), Company.name
    ).limit(limit)
    return [CompanyHit(b, n, int(c or 0), last) for b, n, c, last in (await s.execute(stmt)).all()]


async def get_company(s: AsyncSession, bizno: str) -> Company | None:
    return await s.get(Company, bizno)


def known_fields(keywords: dict[str, list[str]], rows: Sequence[FieldRow]) -> list[str]:
    """필터에 보일 분야: 사전의 태그 + 실제로 나온 태그(사전이 바뀐 뒤 재분류 전일 수 있음)."""
    return sorted(set(keywords) | {r.field for r in rows})

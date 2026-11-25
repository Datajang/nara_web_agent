"""결과 메일 문안 (설계 2026-11-25). 텍스트+HTML. 업체명·사업명은 HTML에서 이스케이프한다.

메일 종류: opened(개찰 결과) · awarded(낙찰 결과) · failed(유찰) · renotice(재공고가 올라왔어요).
경쟁사 투찰가는 분류마다 상위 10곳 + '외 N곳'. 협상계약이면 기술·가격·총점.
"""

from __future__ import annotations

import html as _html
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.mail import Mail
from app.db.models import Bid, BidAward, BidParticipant, BidResultWatch
from app.llm.versions import bid_ref

Kind = Literal["opened", "awarded", "failed", "renotice"]
TOP = 10
FOOTER = "결과 메일은 설정 > 계정에서 끌 수 있어요."
_SUBJECT = {
    "opened": "개찰 결과",
    "awarded": "낙찰 결과",
    "failed": "유찰",
    "renotice": "재공고가 올라왔어요",
}


@dataclass(frozen=True)
class RankRow:
    rank: int | None
    name: str
    bid_amount: int | None
    scores: tuple[float, float, float] | None  # 기술·가격·총점(협상계약)
    remark: str | None
    clsfc: str


@dataclass(frozen=True)
class ResultView:
    title: str
    bid_ref: str
    org: str | None
    rows: list[RankRow]
    our_rank: str
    winner: str | None
    amount: int | None
    kind: Kind
    renotice_ref: str | None
    negotiated: bool


def _won(v: int | None) -> str:
    return "-" if v is None else f"{v:,}원"


def _row_text(r: RankRow) -> str:
    rank = f"{r.rank}위" if r.rank is not None else f"순위 없음({r.remark or '-'})"
    s = f"{rank} {r.name} {_won(r.bid_amount)}"
    if r.scores is not None:
        t, p, total = r.scores
        s += f" (기술 {t:.2f} · 가격 {p:.2f} · 총점 {total:.2f})"
    return s


def _groups(rows: list[RankRow]) -> list[tuple[str, list[RankRow]]]:
    out: dict[str, list[RankRow]] = {}
    for r in rows:
        out.setdefault(r.clsfc, []).append(r)
    return sorted(out.items())


def _lines(v: ResultView) -> list[str]:
    """본문 줄(텍스트·HTML 공통). 링크는 따로 붙인다."""
    head = f"{v.title}" + (f" ({v.org})" if v.org else "")
    out = [head, ""]
    if v.kind == "failed":
        out += ["유찰되었어요. 같은 사업의 재공고가 올라오면 다시 알려드려요."]
    elif v.kind == "renotice":
        out += ["유찰된 공고의 재공고가 올라왔어요. 새 공고를 북마크하면 그 결과도 메일로 받아요."]
    else:
        if v.kind == "awarded":
            out += [f"낙찰자: {v.winner or '-'} · 낙찰금액 {_won(v.amount)}"]
        elif v.rows:
            first = min(
                (r for r in v.rows if r.rank is not None), key=lambda r: r.rank or 0, default=None
            )
            if first is not None:
                out += [f"1순위(낙찰 예정자): {first.name} · {_won(first.bid_amount)}"]
        out += [f"우리 회사: {v.our_rank}"]
        groups = _groups(v.rows)
        for clsfc, rows in groups:
            out += [""] + ([f"[분류 {clsfc}]"] if len(groups) > 1 else [])
            out += [_row_text(r) for r in rows[:TOP]]
            if len(rows) > TOP:
                out += [f"외 {len(rows) - TOP}곳"]
    return out


def render(view: ResultView, to: str, app_origin: str, service_name: str) -> Mail:
    origin = app_origin.rstrip("/")
    link = f"{origin}/bids/{view.renotice_ref or view.bid_ref}"
    settings_link = f"{origin}/settings/account"
    lines = _lines(view)
    label = "재공고 보기" if view.kind == "renotice" else "공고 보기"
    body = "\n".join([*lines, "", f"{label}: {link}", "", f"{FOOTER} {settings_link}"])
    e = _html.escape
    p = 'style="margin:0 0 8px;font-size:14px;line-height:1.6;color:#1f2937"'
    paras = "".join(f"<p {p}>{e(x)}</p>" if x else "<br>" for x in lines)
    html = (
        '<!doctype html><html lang="ko"><body style="margin:0;padding:24px;background:#f3f4f6">'
        '<div style="max-width:560px;margin:0 auto;padding:24px;background:#ffffff;'
        'border-radius:8px">'
        f'<p style="margin:0 0 16px;font-size:13px;color:#6b7280">{e(service_name)}</p>'
        f"{paras}"
        f'<p style="margin:16px 0"><a href="{e(link, quote=True)}" style="color:#2563eb">'
        f"{e(label)}</a></p>"
        f'<p style="margin:16px 0 0;font-size:13px;color:#6b7280">{e(FOOTER)} '
        f'<a href="{e(settings_link, quote=True)}" style="color:#6b7280">설정 열기</a></p>'
        "</div></body></html>"
    )
    one_line = " ".join(view.title.split())  # 메일 제목은 줄바꿈 금지
    subject = f"[{service_name}] {_SUBJECT[view.kind]}: {one_line}"
    return Mail(to=to, subject=subject, body=body, html=html)


def _rank_row(p: BidParticipant) -> RankRow:
    scores = None
    if p.tech_score is not None and p.price_score is not None and p.total_score is not None:
        scores = (float(p.tech_score), float(p.price_score), float(p.total_score))
    return RankRow(p.rank, p.name or p.bizno, p.bid_amount, scores, p.remark, p.bid_clsfc_no)


async def load_view(s: AsyncSession, bid_id: int, our_bizno: str | None, kind: Kind) -> ResultView:
    """DB에서 메일 내용을 모은다. 분류마다 마지막 재입찰 차수의 개찰 순위를 쓴다."""
    bid = await s.get_one(Bid, bid_id)
    w = await s.get_one(BidResultWatch, bid_id)
    parts = (
        await s.execute(
            select(BidParticipant).where(
                BidParticipant.bid_ntce_no == bid.bid_no,
                BidParticipant.bid_ntce_ord == w.notice_ord,
            )
        )
    ).scalars()
    last_rbid: dict[str, str] = {}
    plist = list(parts)
    for p in plist:
        last_rbid[p.bid_clsfc_no] = max(last_rbid.get(p.bid_clsfc_no, ""), p.rbid_no)
    rows = sorted(
        (p for p in plist if p.rbid_no == last_rbid[p.bid_clsfc_no]),
        key=lambda p: (p.bid_clsfc_no, p.rank is None, p.rank or 0, p.name or ""),
    )
    our = "미참가"
    mine = next((p for p in rows if our_bizno and p.bizno == our_bizno), None)
    if mine is not None:
        n = sum(1 for p in rows if p.bid_clsfc_no == mine.bid_clsfc_no)
        our = (
            f"{mine.rank}위 / {n}곳"
            if mine.rank is not None
            else f"순위 없음({mine.remark or '-'})"
        )
    award = (
        await s.execute(
            select(BidAward)
            .where(BidAward.bid_ntce_no == bid.bid_no, BidAward.bid_ntce_ord == w.notice_ord)
            .order_by(BidAward.bid_clsfc_no, BidAward.rbid_no.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    rank_rows = [_rank_row(p) for p in rows]
    return ResultView(
        title=bid.title,
        bid_ref=bid_ref(bid.id),
        org=bid.org_name,
        rows=rank_rows,
        our_rank=our,
        winner=award.winner_name if award else None,
        amount=award.award_amount if award else None,
        kind=kind,
        renotice_ref=bid_ref(w.renotice_bid_id) if w.renotice_bid_id else None,
        negotiated=any(r.scores is not None for r in rank_rows),
    )

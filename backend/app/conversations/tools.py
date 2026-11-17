"""어시스턴트 도구 실행 (SPEC §8.6 표). 모두 읽기 전용이며 개인 자원은 user_id로 제한한다.

모델에 주는 결과는 최대 20건, bid_id·제목·기관·예산·마감·headline만, URL 없음,
전체 TOOL_RESULT_TOKENS 이하로 자른다 [가정].
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select

from app.awards import views
from app.awards.mapper import normalize_name
from app.bids.meta import kst_text, money_text
from app.db.models import Bid, BidSummary, Profile
from app.deps import Deps
from app.errors import ApiError
from app.history import repo as history
from app.llm.assistant import ToolArgError, ToolExec, ToolOutcome
from app.llm.tokens import load_counter
from app.llm.versions import SUMMARY_PROMPT, bid_ref, parse_bid_ref, prompt_version
from app.pipeline.analyze import get_or_create_analysis
from app.pipeline.explain import counted_period
from app.pipeline.recommend import recommend
from app.pipeline.scoring import _headlines
from app.search.query import SearchQuery
from app.search.service import find_bids

TOOL_ITEMS = 20
TOOL_RESULT_TOKENS = 6000
COMPANY_TOOLS = frozenset({"search_companies", "get_company_awards", "compare_companies"})
NO_PROFILE = {"error": "대화에 프로필이 없어요. 설정에서 프로필을 만들도록 안내하세요."}


class SearchArgs(SearchQuery):
    limit: int = Field(default=10, ge=1, le=20)


class BidArgs(BaseModel):
    bid_id: str


class RecommendArgs(BaseModel):
    days: int = Field(default=14, ge=1, le=90)
    source: Literal["regular", "prespec", "all"] = "all"
    top_n: int = Field(default=5, ge=1, le=10)


class CompanyQueryArgs(BaseModel):
    q: str = Field(min_length=1, max_length=100)


class CompanyRef(BaseModel):
    """업체 지정: 사업자번호 또는 업체명. 실제 모델은 이름만 알 때 이름을 넣는다(2026-11-16)."""

    bizno: str | None = Field(default=None, pattern=r"^\d{10}$")
    name: str | None = Field(default=None, min_length=1, max_length=100)


class CompanyAwardsArgs(CompanyRef):
    limit: int = Field(default=10, ge=1, le=20)


class CompareArgs(CompanyRef):
    pass


class Ambiguous(Exception):
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload


class NavigateArgs(BaseModel):
    tab: Literal["search", "recommend", "library", "settings"]
    params: dict[str, str | int | bool | list[str]] = Field(default_factory=dict, max_length=10)


@dataclass
class TurnProfile:
    id: int
    description: str
    keywords: list[str]


def _dump(payload: dict[str, Any], deps: Deps, items: list[Any] | None = None) -> str:
    """JSON으로. TOOL_RESULT_TOKENS를 넘으면 목록(기본 payload['items'])을 뒤에서 줄인다."""
    counter = load_counter(deps.settings.llm_tokenizer_path)
    items = items if items is not None else payload.get("items")
    text = json.dumps(payload, ensure_ascii=False)
    while isinstance(items, list) and items and counter.count(text) > TOOL_RESULT_TOKENS:
        items.pop()
        payload["truncated"] = True
        text = json.dumps(payload, ensure_ascii=False)
    return text


async def _items(deps: Deps, bids: list[Bid], extra: dict[int, dict[str, Any]] | None = None):
    model_id = deps.llm.model_id if deps.llm else deps.settings.llm_model_id
    heads = await _headlines(deps, [b.id for b in bids], model_id)
    out = []
    for b in bids[:TOOL_ITEMS]:
        item: dict[str, Any] = {
            "bid_id": bid_ref(b.id),
            "title": b.title,
            "org": b.org_name,
            "budget": money_text(b.budget),
            "deadline": kst_text(b.deadline_at),
        }
        if b.id in heads:
            item["headline"] = heads[b.id]
        item.update((extra or {}).get(b.id, {}))
        out.append(item)
    return out


def make_executor(deps: Deps, user_id: int, profile: TurnProfile | None) -> ToolExec:
    async def bid_of(raw: str) -> Bid:
        n = parse_bid_ref(raw)
        async with deps.db.session() as s:
            bid = await s.get(Bid, n) if n is not None else None
        if bid is None:
            raise ToolArgError(f"없는 공고 ID: {raw}")
        return bid

    async def execute(name: str, args: dict[str, Any]) -> ToolOutcome:
        try:
            return await _run(name, args)
        except ValidationError as e:
            raise ToolArgError(str(e.errors(include_url=False))[:300]) from e
        except ApiError as e:  # 회사 미설정·없는 업체 등: 모델이 사용자에게 안내하게 돌려준다
            return ToolOutcome(
                json.dumps({"error": e.message}, ensure_ascii=False), summary=f"{name}: {e.code}"
            )

    async def _resolve(s: Any, ref: CompanyRef) -> str | None:
        """업체명이면 업체 검색으로 사업자번호를 찾는다. 하나로 정해지지 않으면 후보를 돌려준다."""
        if ref.bizno or not ref.name:
            return ref.bizno
        hits = (await views.company_search(s, deps, user_id, ref.name)).items
        exact = [h for h in hits if normalize_name(h.name) == normalize_name(ref.name)]
        pick = exact if len(exact) == 1 else hits
        if len(pick) == 1:
            return pick[0].bizno
        raise Ambiguous(
            {
                "error": "업체가 여럿이에요. 후보의 사업자번호(bizno)로 다시 불러 주세요."
                if hits
                else "수집된 낙찰에서 그 이름의 업체를 찾지 못했어요.",
                "candidates": [h.model_dump(mode="json") for h in hits[:5]],
            }
        )

    async def _company(name: str, args: dict[str, Any]) -> ToolOutcome:
        """낙찰·경쟁사 도구 (§15.8). API와 같은 서비스 함수·같은 응답 스키마(app.awards.views)."""
        try:
            return await _company_run(name, args)
        except Ambiguous as e:
            return ToolOutcome(
                json.dumps(e.payload, ensure_ascii=False), summary=f"{name}: 업체 미확정"
            )

    async def _company_run(name: str, args: dict[str, Any]) -> ToolOutcome:
        async with deps.db.session() as s:
            if name == "search_companies":
                q = CompanyQueryArgs.model_validate(args).q
                found = await views.company_search(s, deps, user_id, q)
                payload = found.model_dump(mode="json")
                return ToolOutcome(
                    _dump(payload, deps), summary=f"search_companies: {len(found.items)}건"
                )
            if name == "get_company_awards":
                ca = CompanyAwardsArgs.model_validate(args)
                bizno, cname = await views.resolve_target(s, deps, await _resolve(s, ca))
                summary = await views.summary_out(s, deps, bizno, cname)
                awards = await views.award_list(s, deps, bizno, limit=ca.limit)
                payload = counted_period(
                    {
                        "summary": summary.model_dump(mode="json", by_alias=True),
                        "awards": awards.model_dump(mode="json", by_alias=True),
                    }
                )
                text = _dump(payload, deps, payload["awards"]["items"])
                return ToolOutcome(text, summary=f"get_company_awards: {bizno}")
            ref = CompareArgs.model_validate(args)
            them = await _resolve(s, ref)
            if them is None:
                raise ToolArgError("비교할 업체의 bizno 또는 name이 필요해요")
            out = await views.compare_out(s, deps, them)
            payload = counted_period(out.model_dump(mode="json", by_alias=True))
            return ToolOutcome(_dump(payload, deps), summary=f"compare_companies: {them}")

    async def _run(name: str, args: dict[str, Any]) -> ToolOutcome:
        if name == "search_bids":
            q = SearchArgs.model_validate(args)
            found = await find_bids(deps, q, q.limit)
            items = await _items(deps, found.bids)
            payload = {"items": items, "total": len(items), "incomplete": found.incomplete}
            return ToolOutcome(
                _dump(payload, deps),
                [b.id for b in found.bids[:TOOL_ITEMS]],
                f"search_bids: {len(items)}건",
            )
        if name == "get_bid":
            bid = await bid_of(BidArgs.model_validate(args).bid_id)
            (item,) = await _items(deps, [bid])
            model_id = deps.llm.model_id if deps.llm else deps.settings.llm_model_id
            async with deps.db.session() as s:
                summary = await s.scalar(
                    select(BidSummary.summary)
                    .where(
                        BidSummary.bid_id == bid.id,
                        BidSummary.prompt_version == prompt_version(SUMMARY_PROMPT, model_id),
                    )
                    .order_by(BidSummary.id.desc())
                    .limit(1)
                )
            if summary:
                item["overview"] = summary.get("overview")
            return ToolOutcome(_dump(item, deps), [bid.id], f"get_bid: {bid_ref(bid.id)}")
        if name == "analyze_bid":
            bid = await bid_of(BidArgs.model_validate(args).bid_id)
            if profile is None:
                return ToolOutcome(json.dumps(NO_PROFILE, ensure_ascii=False), [], "프로필 없음")
            row, _ = await get_or_create_analysis(deps, bid.id, profile.description)
            async with deps.db.session() as s:
                await history.link_analysis(s, user_id, row.id, profile.id)
            r = row.result
            payload = {
                "bid_id": bid_ref(bid.id),
                "fit": {"score": r["fit"]["score"], "verdict": r["fit"]["verdict"]},
                "purpose": r["understanding"]["purpose"],
                "team_needs": r["team_needs"],
                "next_actions": r["next_actions"][:5],
                "warnings": r["warnings"][:3],
            }
            return ToolOutcome(_dump(payload, deps), [bid.id], f"analyze_bid: {bid_ref(bid.id)}")
        if name == "recommend_bids":
            ra = RecommendArgs.model_validate(args)
            if profile is None:
                return ToolOutcome(json.dumps(NO_PROFILE, ensure_ascii=False), [], "프로필 없음")
            async with deps.db.session() as s:
                prof = await s.get_one(Profile, profile.id)
            rec = await recommend(
                deps,
                user_id,
                prof,
                days=ra.days,
                source=ra.source,
                top_n=ra.top_n,
                keywords=None,
            )
            extra = {b.id: {"score": sc.score, "reason": sc.reason} for b, sc in rec.ranked}
            items = await _items(deps, [b for b, _ in rec.ranked], extra)
            return ToolOutcome(
                _dump({"items": items}, deps),
                [b.id for b, _ in rec.ranked],
                f"recommend_bids: {len(items)}건",
            )
        if name == "list_bookmarks":
            async with deps.db.session() as s:
                rows = await history.list_bookmarks(s, user_id)
            extra = {b.id: {"note": bm.note} for bm, b in rows if bm.note}
            items = await _items(deps, [b for _, b in rows], extra)
            return ToolOutcome(
                _dump({"items": items}, deps),
                [b.id for _, b in rows[:TOOL_ITEMS]],
                f"list_bookmarks: {len(items)}건",
            )
        if name in COMPANY_TOOLS:
            return await _company(name, args)
        if name == "navigate":
            nav = NavigateArgs.model_validate(args)
            return ToolOutcome(
                '{"ok": true}',
                summary=f"navigate: {nav.tab}",
                action={"name": "open_tab", "params": {"tab": nav.tab, **nav.params}},
            )
        raise ToolArgError(f"알 수 없는 도구: {name}")

    return execute

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

from app.bids.meta import budget_text, kst_text
from app.db.models import Bid, BidSummary, Profile
from app.deps import Deps
from app.history import repo as history
from app.llm.assistant import ToolArgError, ToolExec, ToolOutcome
from app.llm.tokens import load_counter
from app.llm.versions import SUMMARY_PROMPT, bid_ref, parse_bid_ref, prompt_version
from app.pipeline.analyze import get_or_create_analysis
from app.pipeline.recommend import recommend
from app.pipeline.scoring import _headlines
from app.search.query import SearchQuery
from app.search.service import find_bids

TOOL_ITEMS = 20
TOOL_RESULT_TOKENS = 6000
NO_PROFILE = {"error": "대화에 프로필이 없어요. 설정에서 프로필을 만들도록 안내하세요."}


class SearchArgs(SearchQuery):
    limit: int = Field(default=10, ge=1, le=20)


class BidArgs(BaseModel):
    bid_id: str


class RecommendArgs(BaseModel):
    days: int = Field(default=14, ge=1, le=90)
    source: Literal["regular", "prespec", "all"] = "all"
    top_n: int = Field(default=5, ge=1, le=10)


class NavigateArgs(BaseModel):
    tab: Literal["search", "recommend", "library", "settings"]
    params: dict[str, str | int | bool | list[str]] = Field(default_factory=dict, max_length=10)


@dataclass
class TurnProfile:
    id: int
    description: str
    keywords: list[str]


def _dump(payload: dict[str, Any], deps: Deps) -> str:
    counter = load_counter(deps.settings.llm_tokenizer_path)
    items = payload.get("items")
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
            "budget": budget_text(b.budget),
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
                "overview": r["overview"],
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
        if name == "navigate":
            nav = NavigateArgs.model_validate(args)
            return ToolOutcome(
                '{"ok": true}',
                summary=f"navigate: {nav.tab}",
                action={"name": "open_tab", "params": {"tab": nav.tab, **nav.params}},
            )
        raise ToolArgError(f"알 수 없는 도구: {name}")

    return execute

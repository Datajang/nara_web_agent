"""라우터 공용 도우미: 공고 ID 파싱, LLM 사용 가능 여부, SSE 사용량 기록."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.sse import FinishFn
from app.db.models import Bid, UsageLog
from app.deps import Deps
from app.errors import ApiError
from app.llm.base import LLMClient
from app.llm.usage import RunStats
from app.llm.versions import parse_bid_ref


def model_id(deps: Deps) -> str:
    return deps.llm.model_id if deps.llm is not None else deps.settings.llm_model_id


def bid_not_found() -> ApiError:
    return ApiError(404, "not_found", "공고를 찾을 수 없어요.")


async def load_bid(s: AsyncSession, raw: str) -> Bid:
    n = parse_bid_ref(raw)
    bid = await s.get(Bid, n) if n is not None else None
    if bid is None:
        raise bid_not_found()
    return bid


def require_llm(deps: Deps) -> LLMClient:
    if deps.llm is None:
        raise ApiError(
            503, "llm_unavailable", "지금은 AI 응답이 어려워요. 잠시 후 다시 시도해 주세요."
        )
    return deps.llm


def usage_logger(deps: Deps, user_id: int, event: str) -> FinishFn:
    async def finish(run: RunStats, g2b_calls: int, duration_ms: int) -> None:
        async with deps.db.transaction() as s:
            s.add(
                UsageLog(
                    user_id=user_id,
                    event=event,
                    cache=run.cache,
                    g2b_calls=g2b_calls,
                    llm_calls=run.llm_calls,
                    prompt_tokens=run.prompt_tokens,
                    completion_tokens=run.completion_tokens,
                    duration_ms=duration_ms,
                )
            )
        if deps.g2b is not None:
            deps.g2b.settle(g2b_calls)

    return finish

"""/api/v1/conversations (SPEC §6.2, §6.4 messages 흐름, §8.6). 메시지 전송은 SSE.

status(도구 실행) → token 반복 → cards·action → done(message_id). 도구 인자·결과는
클라이언트로 보내지 않고 messages.parts에 한 줄 요약만 저장한다.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.api.common import model_id, require_llm, usage_logger
from app.api.deps import ActiveUser, Ctx, DbSession
from app.api.schemas.assistant import (
    ConversationIn,
    ConversationList,
    ConversationOut,
    ConversationPatch,
    MessageIn,
    MessageList,
    MessageOut,
)
from app.api.schemas.events import SSE_RESPONSES
from app.api.sse import Emitter, sse_response
from app.bids.cards import BidCard, build_cards
from app.conversations import repo
from app.conversations.tools import TurnProfile, make_executor
from app.db.models import Bid, Message, Profile
from app.llm.assistant import run_turn
from app.llm.base import Message as LLMMessage
from app.llm.versions import bid_ref, parse_bid_ref

router = APIRouter(prefix="/conversations", tags=["assistant"])


def _history(rows: list[Message]) -> list[LLMMessage]:
    """이전 턴의 도구 결과는 빼고 parts의 한 줄 요약만 남긴다 (§8.6-1)."""
    out: list[LLMMessage] = []
    for m in rows:
        if m.role == "user":
            out.append({"role": "user", "content": m.content})
        elif m.role == "assistant":
            tools = [t.get("summary", "") for t in (m.parts or {}).get("tool_calls", [])]
            note = f"\n(사용한 도구: {'; '.join(tools)})" if tools else ""
            out.append({"role": "assistant", "content": m.content + note})
    return out


async def _cards(s: Any, user_id: int, refs: list[str], deps: Any) -> list[BidCard]:
    ids = [i for i in (parse_bid_ref(r) for r in refs) if i is not None]
    if not ids:
        return []
    bids = {b.id: b for b in (await s.execute(select(Bid).where(Bid.id.in_(ids)))).scalars()}
    return await build_cards(
        s, user_id, [bids[i] for i in ids if i in bids], deps.clock(), model_id(deps)
    )


@router.get("")
async def list_conversations(user: ActiveUser, s: DbSession) -> ConversationList:
    rows = await repo.list_conversations(s, user.id)
    return ConversationList(items=[ConversationOut.model_validate(c) for c in rows])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_conversation(
    body: ConversationIn, user: ActiveUser, s: DbSession, ctx: Ctx
) -> ConversationOut:
    c = await repo.create(s, user.id, body.title, body.profile_id, ctx.deps.clock())
    return ConversationOut.model_validate(c)


@router.patch("/{conversation_id}")
async def rename_conversation(
    conversation_id: int, body: ConversationPatch, user: ActiveUser, s: DbSession, ctx: Ctx
) -> ConversationOut:
    c = await repo.rename(s, user.id, conversation_id, body.title, ctx.deps.clock())
    return ConversationOut.model_validate(c)


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(conversation_id: int, user: ActiveUser, s: DbSession) -> Response:
    await repo.remove(s, user.id, conversation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{conversation_id}/messages")
async def list_messages(
    conversation_id: int, user: ActiveUser, s: DbSession, ctx: Ctx
) -> MessageList:
    c = await repo.get(s, user.id, conversation_id)
    items = []
    for m in await repo.messages(s, c.id):
        cards = await _cards(s, user.id, (m.parts or {}).get("cards", []), ctx.deps)
        items.append(
            MessageOut(
                id=m.id,
                role=m.role,  # type: ignore[arg-type]
                content=m.content,
                cards=cards,
                created_at=m.created_at,
            )
        )
    return MessageList(items=items)


@router.post(
    "/{conversation_id}/messages", response_class=StreamingResponse, responses=SSE_RESPONSES
)
async def post_message(
    conversation_id: int, body: MessageIn, user: ActiveUser, s: DbSession, ctx: Ctx
) -> StreamingResponse:
    ctx.limiter.hit(f"messages:{user.id}", 20, 60)
    deps = ctx.deps
    conv = await repo.get(s, user.id, conversation_id)
    llm = require_llm(deps)
    profile: TurnProfile | None = None
    if conv.profile_id is not None:
        p = await s.scalar(
            select(Profile).where(Profile.id == conv.profile_id, Profile.user_id == user.id)
        )
        if p is not None:
            profile = TurnProfile(p.id, p.description, [str(k) for k in p.keywords])
    history = _history(await repo.messages(s, conv.id))
    await repo.add_message(s, conv, "user", body.content, None, deps.clock())
    uid, cid, text = user.id, conv.id, body.content

    async def work(em: Emitter) -> dict[str, Any] | None:
        result = await run_turn(
            llm,
            profile=profile.description if profile else None,
            history=history,
            user_text=text,
            execute=make_executor(deps, uid, profile),
            emit=em.send,
        )
        refs = [bid_ref(i) for i in result.card_ids]
        async with deps.db.session() as s2:
            c2 = await repo.get(s2, uid, cid)
            msg = await repo.add_message(
                s2,
                c2,
                "assistant",
                result.content,
                {
                    "tool_calls": result.tool_log,
                    "cards": refs,
                    "warnings": result.warnings,
                    "actions": result.actions,
                },
                deps.clock(),
            )
            cards = await _cards(s2, uid, refs, deps)
        em.message_id = msg.id
        if cards:
            em.send({"type": "cards", "items": [c.model_dump(mode="json") for c in cards]})
        for action in result.actions:
            em.send({"type": "action", **action})
        return {"message_id": msg.id}

    return sse_response(work, on_finish=usage_logger(deps, uid, "assistant_turn"))

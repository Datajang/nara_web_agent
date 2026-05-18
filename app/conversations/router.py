import json
from typing import Optional, AsyncIterator
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.database import get_db
from app.db.models import Conversation, Message, Project
from app.auth.deps import get_current_user
from app.pipeline.orchestrator import run_pipeline, is_search_intent, _get_current_step

router = APIRouter(tags=["conversations"])


class ConvIn(BaseModel):
    title: Optional[str] = None


class ChatIn(BaseModel):
    message: str
    selected_bid: Optional[dict] = None


@router.get("/projects/{pid}/conversations")
async def list_conversations(pid: int, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    p = await db.get(Project, pid)
    if not p or p.user_id != user.id:
        raise HTTPException(404)
    result = await db.execute(select(Conversation).where(Conversation.project_id == pid))
    convs = result.scalars().all()
    return [{"id": c.id, "title": c.title, "created_at": c.created_at.isoformat()} for c in convs]


@router.post("/projects/{pid}/conversations", status_code=201)
async def create_conversation(pid: int, body: ConvIn, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    p = await db.get(Project, pid)
    if not p or p.user_id != user.id:
        raise HTTPException(404)
    c = Conversation(project_id=pid, title=body.title)
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return {"id": c.id, "title": c.title, "created_at": c.created_at.isoformat()}


@router.get("/conversations/{cid}/messages")
async def list_messages(cid: int, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    c = await db.get(Conversation, cid)
    if not c:
        raise HTTPException(404)
    p = await db.get(Project, c.project_id)
    if not p or p.user_id != user.id:
        raise HTTPException(403)
    result = await db.execute(select(Message).where(Message.conversation_id == cid))
    msgs = result.scalars().all()
    return [{"id": m.id, "role": m.role, "content": m.content,
             "step": m.step, "metadata_": m.metadata_, "created_at": m.created_at.isoformat()}
            for m in msgs]


@router.post("/conversations/{cid}/chat")
async def chat(cid: int, body: ChatIn, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    c = await db.get(Conversation, cid)
    if not c:
        raise HTTPException(404)
    p = await db.get(Project, c.project_id)
    if not p or p.user_id != user.id:
        raise HTTPException(403)

    result = await db.execute(select(Message).where(Message.conversation_id == cid))
    history = result.scalars().all()

    user_msg = Message(conversation_id=cid, role="user", content=body.message)
    db.add(user_msg)
    await db.commit()

    async def generate() -> AsyncIterator[str]:
        full_response = []
        final_step = "chat"
        metadata = None

        async for chunk in run_pipeline(
            message=body.message,
            history=history,
            selected_bid=body.selected_bid,
            department_profile=p.department_profile,
        ):
            yield chunk
            try:
                payload = json.loads(chunk.removeprefix("data: ").strip())
                if payload["type"] == "token":
                    full_response.append(payload["content"])
                elif payload["type"] == "cards":
                    final_step = "search"
                    metadata = json.dumps({"cards": payload["content"]}, ensure_ascii=False)
                    full_response.append(f"검색 결과 {len(payload['content'])}건")
            except Exception:
                pass

        if body.selected_bid:
            final_step = "analyze"

        async with db.begin():
            asst = Message(
                conversation_id=cid,
                role="assistant",
                content="".join(full_response),
                step=final_step,
                metadata_=metadata,
            )
            db.add(asst)

    return StreamingResponse(generate(), media_type="text/event-stream")

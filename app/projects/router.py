from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.database import get_db
from app.db.models import Project, User
from app.auth.deps import get_current_user

router = APIRouter(prefix="/projects", tags=["projects"])

class ProjectIn(BaseModel):
    name: str
    department_profile: Optional[str] = None

class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    department_profile: Optional[str] = None

def _project_out(p: Project) -> dict:
    return {"id": p.id, "name": p.name, "department_profile": p.department_profile,
            "created_at": p.created_at.isoformat()}

@router.get("")
async def list_projects(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Project).where(Project.user_id == user.id))
    return [_project_out(p) for p in result.scalars()]

@router.post("", status_code=201)
async def create_project(body: ProjectIn, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    p = Project(user_id=user.id, name=body.name, department_profile=body.department_profile)
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return _project_out(p)

@router.get("/{pid}")
async def get_project(pid: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    p = await db.get(Project, pid)
    if not p or p.user_id != user.id:
        raise HTTPException(404, "Not found")
    return _project_out(p)

@router.put("/{pid}")
async def update_project(pid: int, body: ProjectUpdate, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    p = await db.get(Project, pid)
    if not p or p.user_id != user.id:
        raise HTTPException(404, "Not found")
    if body.name is not None:
        p.name = body.name
    if body.department_profile is not None:
        p.department_profile = body.department_profile
    await db.commit()
    await db.refresh(p)
    return _project_out(p)

@router.delete("/{pid}", status_code=204)
async def delete_project(pid: int, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    p = await db.get(Project, pid)
    if not p or p.user_id != user.id:
        raise HTTPException(404, "Not found")
    await db.delete(p)
    await db.commit()

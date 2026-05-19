import bcrypt as _bcrypt

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from app.db.database import get_db
from app.db.models import User
from app.auth.jwt import create_access_token

router = APIRouter(prefix="/auth", tags=["auth"])

class _Pwd:
    def hash(self, plain: str) -> str:
        return _bcrypt.hashpw(plain.encode(), _bcrypt.gensalt()).decode()
    def verify(self, plain: str, hashed: str) -> bool:
        return _bcrypt.checkpw(plain.encode(), hashed.encode())

pwd = _Pwd()

class RegisterIn(BaseModel):
    email: str
    password: str

class LoginIn(BaseModel):
    email: str
    password: str

@router.post("/register", status_code=201)
async def register(body: RegisterIn, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")
    user = User(email=body.email, password_hash=pwd.hash(body.password))
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return {"user_id": user.id}

@router.post("/login")
async def login(body: LoginIn, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if not user or not pwd.verify(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"access_token": create_access_token(user.id)}

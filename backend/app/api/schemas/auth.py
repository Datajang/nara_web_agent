"""인증·회원·프로필 요청·응답 모델 (SPEC §6.2, §9)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Email = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$"),
]
# 정책 검사(10~128자)는 서비스가 한다. 여기서는 해시 비용 폭주만 막는다.
RawPassword = Annotated[str, StringConstraints(max_length=1024)]
UserStatus = Literal["pending_verification", "pending_approval", "active", "disabled"]
Role = Literal["member", "admin"]
TeamRole = Literal["owner", "member"]
Keyword = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]


class RegisterIn(BaseModel):
    email: Email
    password: RawPassword
    display_name: Annotated[str, StringConstraints(strip_whitespace=True, max_length=50)] = ""


class TokenIn(BaseModel):
    token: Annotated[str, StringConstraints(min_length=1, max_length=200)]


class EmailIn(BaseModel):
    email: Email


class LoginIn(BaseModel):
    email: Email
    password: RawPassword


class ResetIn(BaseModel):
    token: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    password: RawPassword


class AcceptedOut(BaseModel):
    status: Literal["accepted"] = "accepted"


class VerifyOut(BaseModel):
    status: UserStatus


class UserBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    display_name: str
    role: Role
    status: UserStatus


class MeTeam(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class MeOut(UserBase):
    """내 정보. 팀(P6)과 개인 관심 키워드를 함께 준다."""

    interest_keywords: list[str] = []
    team: MeTeam | None = None
    team_role: TeamRole | None = None


class MePatch(BaseModel):
    display_name: Annotated[str, StringConstraints(strip_whitespace=True, max_length=50)] | None = (
        None
    )
    current_password: RawPassword | None = None
    new_password: RawPassword | None = None
    interest_keywords: Annotated[list[Keyword], Field(max_length=10)] | None = None


class AdminUserOut(UserBase):
    email_verified_at: datetime | None
    last_login_at: datetime | None
    created_at: datetime


class AdminUserList(BaseModel):
    items: list[AdminUserOut]
    total: int


class AdminUserPatch(BaseModel):
    status: Literal["active", "disabled"] | None = None
    role: Role | None = None


class ProfileIn(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    description: Annotated[str, StringConstraints(max_length=4000)] = ""
    keywords: Annotated[list[Keyword], Field(max_length=10)] = []
    is_default: bool = False
    scope: Literal["personal", "team"] = "personal"


class ProfilePatch(BaseModel):
    name: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
        | None
    ) = None
    description: Annotated[str, StringConstraints(max_length=4000)] | None = None
    keywords: Annotated[list[Keyword], Field(max_length=10)] | None = None
    is_default: bool | None = None


class ProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    keywords: list[str]
    is_default: bool
    profile_hash: str
    scope: Literal["personal", "team"]
    created_at: datetime
    updated_at: datetime


class ProfileList(BaseModel):
    items: list[ProfileOut]


class DevMail(BaseModel):
    to: str
    subject: str
    body: str


class DevMailList(BaseModel):
    items: list[DevMail]

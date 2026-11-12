"""팀 요청·응답 모델 (SPEC §13 P6)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints

TeamName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]


class TeamIn(BaseModel):
    name: TeamName


class JoinIn(BaseModel):
    code: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=32)]


class TeamOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    invite_code: str


class MemberOut(BaseModel):
    user_id: int
    display_name: str
    role: Literal["owner", "member"]
    joined_at: datetime | None


class MyTeamOut(BaseModel):
    """팀이 없으면 team=null이고 나머지는 비어 있다."""

    team: TeamOut | None = None
    role: Literal["owner", "member"] | None = None
    members: list[MemberOut] = []

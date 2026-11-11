"""API 요청·응답 모델 (SPEC §6). 프론트 타입은 이 스키마에서 생성된다 (scripts/export_openapi.py).

영역별 모듈: auth(회원·프로필), bids(검색·상세·분석·추천), history(내 기록·피드백),
assistant(대화), admin(사용량·수집기), events(SSE 이벤트).
"""

from app.api.schemas.auth import *  # noqa: F403

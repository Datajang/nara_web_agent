"""API 오류 (SPEC §6.1 오류 형식). 서비스 계층도 이 예외를 던지고 API가 JSON으로 바꾼다."""

from __future__ import annotations

from typing import Any


class ApiError(Exception):
    def __init__(
        self,
        status: int,
        code: str,
        message: str = "",
        details: list[dict[str, Any]] | None = None,
        retry_after: int | None = None,
    ) -> None:
        super().__init__(f"{status} {code}")
        self.status = status
        self.code = code
        self.message = message
        self.details = details or []
        self.retry_after = retry_after

    def body(self) -> dict[str, Any]:
        return {"error": {"code": self.code, "message": self.message, "details": self.details}}

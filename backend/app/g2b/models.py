from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

Source = Literal["regular", "prespec"]


class BidFileRef(BaseModel):
    url: str
    name: str
    kind: Literal["rfp", "spec", "other"]
    origin: Literal["notice", "eorder", "prespec"]


class BidRecord(BaseModel):
    bid_key: str
    source: Source
    bid_no: str
    ord: str | None
    prespec_reg_no: str | None
    title: str
    org_name: str | None
    budget: int | None
    deadline_at: datetime | None
    notice_at: datetime | None
    detail_url: str | None
    files: list[BidFileRef]
    raw: dict[str, Any]

    def content_hash(self) -> str:
        """메타·파일 목록의 정규화 JSON sha256 (§4). raw의 다른 필드 변화는 무시한다.

        차수(ord)와 공고 종류(ntceKindNm)를 넣어 변경·취소공고를 내용 변경으로 잡는다.
        """
        meta = {
            "ord": self.ord,
            "kind": self.raw.get("ntceKindNm"),
            "title": self.title,
            "org_name": self.org_name,
            "budget": self.budget,
            "deadline_at": self.deadline_at.isoformat() if self.deadline_at else None,
            "notice_at": self.notice_at.isoformat() if self.notice_at else None,
            "detail_url": self.detail_url,
            "files": sorted((f.url, f.name) for f in self.files),
        }
        blob = json.dumps(meta, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

"""호출 횟수를 세는 가짜 LLM (SPEC §12.2). 스키마는 P3에서 §8로 바뀐다."""

from __future__ import annotations

import asyncio
from collections import Counter
from typing import Any

from app.llm.base import LLMResult


class FakeLLM:
    def __init__(self, model_id: str = "fake-1", delay_s: float = 0.0) -> None:
        self.model_id = model_id
        self.delay_s = delay_s
        self.calls: Counter[str] = Counter()
        self.payloads: list[tuple[str, dict[str, Any]]] = []

    async def complete_json(self, task: str, payload: dict[str, Any]) -> LLMResult:
        self.calls[task] += 1
        self.payloads.append((task, payload))
        if self.delay_s:
            await asyncio.sleep(self.delay_s)
        if task == "summary":
            data: dict[str, Any] = {
                "overview": f"요약: {payload.get('title', '')}",
                "chars": len(payload.get("text", "")),
            }
        elif task == "analysis":
            data = {"fit": "mid", "markdown": f"분석({payload.get('profile', '')[:10]})"}
        elif task == "score":
            data = {
                "scores": [
                    {"bid_id": b["bid_id"], "score": 50, "reason": "가짜"} for b in payload["bids"]
                ]
            }
        else:
            data = {}
        return LLMResult(data=data, prompt_tokens=10, completion_tokens=5)

"""vLLM(OpenAI 호환) 비동기 클라이언트 (SPEC §8.1, §8.7, docs/LLM_SETUP.md).

- 전역 세마포어(LLM_MAX_CONCURRENCY)로 동시 요청 수를 제한한다.
- 5xx·타임아웃·연결 실패는 2회 재시도 뒤 LLMUnavailable. 400 컨텍스트 초과는 LLMContextTooLong.
- thinking은 요청마다 끈다(서버 기본값과 별개로 명시).
- 요청 본문·프롬프트는 로그에 남기지 않는다.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Sequence
from typing import Any

import httpx
import openai

from app.llm.base import (
    Completion,
    LLMContextTooLong,
    LLMError,
    LLMUnavailable,
    Message,
    StreamEvent,
    StreamUsage,
    TextDelta,
    ToolCall,
    ToolCalls,
)

log = logging.getLogger(__name__)
NO_THINK: dict[str, Any] = {"chat_template_kwargs": {"enable_thinking": False}}
_RETRYABLE = (openai.APITimeoutError, openai.APIConnectionError, openai.InternalServerError)


def _is_context_error(e: openai.BadRequestError) -> bool:
    text = str(e).lower()
    return "context" in text or "maximum" in text or "too long" in text


class OpenAICompatLLM:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        model_id: str,
        timeout_s: float,
        max_concurrency: int,
        retry_delays: Sequence[float] = (1.0, 3.0),
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.model = model
        self.model_id = model_id
        self._retry_delays = tuple(retry_delays)
        self._sem = asyncio.Semaphore(max_concurrency)
        self._client = openai.AsyncOpenAI(
            base_url=base_url,
            api_key=api_key or "none",
            timeout=timeout_s,
            max_retries=0,  # 재시도는 여기서 직접 (§8.7)
            http_client=http_client,
        )

    async def close(self) -> None:
        await self._client.close()

    async def _call(self, task: str, **kwargs: Any) -> Any:
        last: Exception | None = None
        for attempt in range(len(self._retry_delays) + 1):
            if attempt:
                await asyncio.sleep(self._retry_delays[attempt - 1])
            try:
                async with self._sem:
                    return await self._client.chat.completions.create(
                        model=self.model, extra_body=NO_THINK, **kwargs
                    )
            except openai.BadRequestError as e:
                if _is_context_error(e):
                    raise LLMContextTooLong(task) from e
                raise LLMError(f"{task}: bad request") from e
            except _RETRYABLE as e:
                last = e
                log.warning("llm.retry task=%s attempt=%d %s", task, attempt + 1, type(e).__name__)
            except openai.APIStatusError as e:
                raise LLMError(f"{task}: HTTP {e.status_code}") from e
        raise LLMUnavailable(task) from last

    async def complete(
        self,
        task: str,
        messages: list[Message],
        *,
        json_schema: dict[str, Any] | None,
        temperature: float,
        max_tokens: int,
    ) -> Completion:
        kwargs: dict[str, Any] = {
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_schema is not None:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": task, "schema": json_schema},
            }
        resp = await self._call(task, **kwargs)
        u = resp.usage
        return Completion(
            text=resp.choices[0].message.content or "",
            prompt_tokens=u.prompt_tokens if u else 0,
            completion_tokens=u.completion_tokens if u else 0,
        )

    async def chat_stream(
        self,
        messages: list[Message],
        *,
        tools: list[dict[str, Any]],
        tool_choice: str,
        temperature: float,
        max_tokens: int,
    ) -> AsyncIterator[StreamEvent]:
        """텍스트 조각은 바로, 도구 호출은 조각을 누적해 스트림 끝에 한 번에 낸다 (§8.6-6)."""
        kwargs: dict[str, Any] = {
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice
        stream = await self._call("assistant", **kwargs)
        calls: dict[int, dict[str, str]] = {}
        try:
            async for chunk in stream:
                if chunk.usage is not None:
                    yield StreamUsage(chunk.usage.prompt_tokens, chunk.usage.completion_tokens)
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta.content:
                    yield TextDelta(delta.content)
                for tc in delta.tool_calls or []:
                    slot = calls.setdefault(tc.index, {"id": "", "name": "", "arguments": ""})
                    if tc.id:
                        slot["id"] = tc.id
                    if tc.function and tc.function.name:
                        slot["name"] += tc.function.name
                    if tc.function and tc.function.arguments:
                        slot["arguments"] += tc.function.arguments
        except _RETRYABLE as e:
            raise LLMUnavailable("assistant") from e
        if calls:
            yield ToolCalls(
                [
                    ToolCall(id=c["id"] or f"call_{i}", name=c["name"], arguments=c["arguments"])
                    for i, c in sorted(calls.items())
                ]
            )

    async def health(self) -> bool:
        try:
            await self._client.with_options(timeout=5).models.list()
            return True
        except (openai.OpenAIError, json.JSONDecodeError):
            return False

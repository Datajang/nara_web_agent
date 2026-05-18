from openai import AsyncOpenAI
from typing import AsyncIterator
from app.config import settings

_client: AsyncOpenAI | None = None


def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(base_url=settings.vllm_base_url, api_key="unused")
    return _client


async def chat_complete(messages: list[dict], max_tokens: int = 512) -> str:
    resp = await get_client().chat.completions.create(
        model=settings.vllm_model_name,
        messages=messages,
        max_tokens=max_tokens,
        temperature=0.1,
        stream=False,
    )
    return resp.choices[0].message.content or ""


async def chat_stream(messages: list[dict], max_tokens: int = 1500) -> AsyncIterator[str]:
    stream = await get_client().chat.completions.create(
        model=settings.vllm_model_name,
        messages=messages,
        max_tokens=max_tokens,
        temperature=0.3,
        stream=True,
    )
    async for chunk in stream:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta

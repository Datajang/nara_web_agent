# /// script
# requires-python = ">=3.11"
# dependencies = ["openai>=1.50", "pydantic>=2.7"]
# ///
"""vLLM 스모크 테스트 (SPEC §13.2 P0, §8.2).

측정 항목 5개:
  1. simple      단순 응답 — 첫 토큰 지연(TTFT), 전체 지연, 토큰/초
  2. json_schema 스키마 JSON 출력 — response_format json_schema → Pydantic 검증
  3. tool_call   도구 호출 — tool_calls의 함수 이름·인자 파싱
  4. long_input  긴 입력(기본 약 12K 토큰) — 본문 중간의 값을 찾는지, 실제 prompt_tokens
  5. concurrency 동시 4요청 — 요청별 TTFT·지연 p50/최대, 합계 토큰/초

실행 예 (GPU 서버에서):
  uv run eval/smoke_llm.py --label fp8 --vllm-flags "--quantization fp8 ..."
환경변수: LLM_BASE_URL(필수), LLM_MODEL(기본 brain), LLM_API_KEY.
결과: eval/results/<날짜>_smoke_<label>.json + 표준출력에 마크다운 표.
도구 호출이 실패하면 서버를 --tool-call-parser qwen3_xml로 다시 띄워 재측정한다(§8.2).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionFunctionToolParam, ChatCompletionMessageParam
from pydantic import BaseModel, ValidationError

# 생각 모드는 서버 기본값과 이중으로 끈다 (§8.2 클라이언트 호출 규칙)
NO_THINK: dict[str, Any] = {"chat_template_kwargs": {"enable_thinking": False}}
NEEDLE = "NARA-7342"
FILLER = (
    "본 사업은 공공기관의 업무 효율화를 위한 정보시스템 구축 용역으로, 수행사는 과업 범위에 "
    "따라 요구사항 분석, 설계, 구현, 시험, 이행 및 안정화 지원을 수행하여야 한다. "
)
BID_TEXT = (
    "[공고] 2026년 AI 기반 민원 분석 시스템 구축 용역\n"
    "- 사업 예산: 금 150,000,000원 (부가세 포함)\n"
    "- 입찰 마감: 2026-12-01 10:00\n"
    "- 계약 방법: 협상에 의한 계약\n"
)


class BidFacts(BaseModel):
    title: str
    budget_won: int | None
    deadline: str | None
    method: str | None


SEARCH_TOOL: ChatCompletionFunctionToolParam = {
    "type": "function",
    "function": {
        "name": "search_bids",
        "description": "키워드로 나라장터 용역 입찰 공고를 검색한다.",
        "parameters": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "검색 키워드"},
                "days": {"type": "integer", "description": "최근 며칠"},
            },
            "required": ["keyword"],
        },
    },
}


@dataclass
class CheckResult:
    name: str
    passed: bool
    metrics: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass
class StreamStats:
    text: str
    ttft_s: float | None
    latency_s: float
    completion_tokens: int | None
    prompt_tokens: int | None

    @property
    def tokens_per_s(self) -> float | None:
        if not self.completion_tokens or self.ttft_s is None:
            return None
        decode_s = self.latency_s - self.ttft_s
        return round(self.completion_tokens / decode_s, 2) if decode_s > 0 else None


async def stream_chat(
    client: AsyncOpenAI, model: str, messages: list[ChatCompletionMessageParam], max_tokens: int
) -> StreamStats:
    """스트리밍으로 호출하고 첫 토큰 지연·전체 지연·토큰 수를 잰다."""
    start = time.perf_counter()
    ttft: float | None = None
    parts: list[str] = []
    usage = None
    stream = await client.chat.completions.create(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=0.1,
        stream=True,
        stream_options={"include_usage": True},
        extra_body=NO_THINK,
    )
    async for chunk in stream:
        if chunk.usage is not None:
            usage = chunk.usage
        if chunk.choices and chunk.choices[0].delta.content:
            if ttft is None:
                ttft = time.perf_counter() - start
            parts.append(chunk.choices[0].delta.content)
    return StreamStats(
        text="".join(parts),
        ttft_s=round(ttft, 3) if ttft is not None else None,
        latency_s=round(time.perf_counter() - start, 3),
        completion_tokens=usage.completion_tokens if usage else None,
        prompt_tokens=usage.prompt_tokens if usage else None,
    )


async def check_simple(client: AsyncOpenAI, model: str) -> CheckResult:
    msgs: list[ChatCompletionMessageParam] = [
        {"role": "user", "content": "나라장터가 무엇인지 두 문장으로 설명해 주세요."}
    ]
    s = await stream_chat(client, model, msgs, max_tokens=200)
    ok = bool(s.text.strip()) and "<think>" not in s.text
    return CheckResult(
        "simple",
        ok,
        {
            "ttft_s": s.ttft_s,
            "latency_s": s.latency_s,
            "completion_tokens": s.completion_tokens,
            "tokens_per_s": s.tokens_per_s,
            "sample": s.text[:120],
        },
        None if ok else "빈 응답이거나 <think> 블록이 남아 있음",
    )


async def check_json_schema(client: AsyncOpenAI, model: str) -> CheckResult:
    start = time.perf_counter()
    resp = await client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": "공고에서 사실만 뽑아 JSON으로 답한다. 금액은 원 단위 정수.",
            },
            {"role": "user", "content": BID_TEXT},
        ],
        temperature=0.1,
        max_tokens=300,
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "BidFacts",
                "schema": BidFacts.model_json_schema(),
                "strict": True,
            },
        },
        extra_body=NO_THINK,
    )
    raw = resp.choices[0].message.content or ""
    metrics: dict[str, Any] = {"latency_s": round(time.perf_counter() - start, 3), "raw": raw[:200]}
    try:
        facts = BidFacts.model_validate_json(raw)
    except ValidationError as e:
        return CheckResult("json_schema", False, metrics, f"스키마 검증 실패: {e.errors()[:2]}")
    metrics["budget_ok"] = facts.budget_won == 150_000_000
    return CheckResult(
        "json_schema", True, metrics, None if metrics["budget_ok"] else "예산 값 불일치"
    )


async def check_tool_call(client: AsyncOpenAI, model: str) -> CheckResult:
    start = time.perf_counter()
    resp = await client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "최근 30일 동안 올라온 AI 관련 용역 공고 찾아줘"}],
        tools=[SEARCH_TOOL],
        tool_choice="auto",
        temperature=0.1,
        max_tokens=300,
        extra_body=NO_THINK,
    )
    msg = resp.choices[0].message
    metrics: dict[str, Any] = {"latency_s": round(time.perf_counter() - start, 3)}
    calls = msg.tool_calls or []
    if not calls:
        metrics["content"] = (msg.content or "")[:200]
        return CheckResult("tool_call", False, metrics, "tool_calls 없음 → qwen3_xml 파서로 재시험")
    call = calls[0]
    if call.type != "function":
        return CheckResult("tool_call", False, metrics, f"예상 밖 도구 호출 형식: {call.type}")
    fn = call.function
    metrics["function"] = fn.name
    metrics["arguments"] = fn.arguments
    try:
        args = json.loads(fn.arguments)
    except json.JSONDecodeError:
        return CheckResult("tool_call", False, metrics, "인자 JSON 파싱 실패 → qwen3_xml로 재시험")
    ok = fn.name == "search_bids" and isinstance(args.get("keyword"), str)
    return CheckResult(
        "tool_call", ok, metrics, None if ok else "함수 이름 또는 keyword 인자 불일치"
    )


async def _prompt_tokens(client: AsyncOpenAI, model: str, content: str) -> int:
    resp = await client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": content}],
        max_tokens=1,
        extra_body=NO_THINK,
    )
    return resp.usage.prompt_tokens if resp.usage else 0


async def check_long_input(client: AsyncOpenAI, model: str, target_tokens: int) -> CheckResult:
    # 반복 문단 1개의 토큰 수를 서버 토크나이저로 재서 반복 횟수를 정한다
    base = await _prompt_tokens(client, model, "")
    per_filler = max(1, await _prompt_tokens(client, model, FILLER) - base)
    reps = max(2, (target_tokens - base - 60) // per_filler)
    half = reps // 2
    doc = FILLER * half + f"\n비밀 코드: {NEEDLE}\n" + FILLER * (reps - half)
    msgs: list[ChatCompletionMessageParam] = [
        {
            "role": "user",
            "content": f"{doc}\n\n위 문서에 적힌 비밀 코드를 그대로 한 줄로만 답하세요.",
        }
    ]
    s = await stream_chat(client, model, msgs, max_tokens=50)
    metrics = {
        "target_tokens": target_tokens,
        "prompt_tokens": s.prompt_tokens,
        "ttft_s": s.ttft_s,
        "latency_s": s.latency_s,
        "answer": s.text.strip()[:80],
    }
    found = NEEDLE in s.text
    long_enough = (s.prompt_tokens or 0) >= int(target_tokens * 0.9)
    err = None
    if not found:
        err = "본문 중간의 값을 찾지 못함"
    elif not long_enough:
        err = "실제 입력이 목표 토큰보다 짧음"
    return CheckResult("long_input", found and long_enough, metrics, err)


async def check_concurrency(client: AsyncOpenAI, model: str, n: int) -> CheckResult:
    msgs: list[ChatCompletionMessageParam] = [
        {"role": "user", "content": "공공 SI 사업 제안서의 목차를 10개 항목으로 써 주세요."}
    ]
    wall_start = time.perf_counter()
    results = await asyncio.gather(
        *(stream_chat(client, model, msgs, max_tokens=256) for _ in range(n)),
        return_exceptions=True,
    )
    wall = time.perf_counter() - wall_start
    ok_stats = [r for r in results if isinstance(r, StreamStats) and r.text.strip()]
    errors = [repr(r)[:120] for r in results if isinstance(r, BaseException)]
    lat = [r.latency_s for r in ok_stats]
    ttft = [r.ttft_s for r in ok_stats if r.ttft_s is not None]
    tokens = sum(r.completion_tokens or 0 for r in ok_stats)
    metrics = {
        "requests": n,
        "succeeded": len(ok_stats),
        "latency_p50_s": round(statistics.median(lat), 3) if lat else None,
        "latency_max_s": round(max(lat), 3) if lat else None,
        "ttft_p50_s": round(statistics.median(ttft), 3) if ttft else None,
        "ttft_max_s": round(max(ttft), 3) if ttft else None,
        "aggregate_tokens_per_s": round(tokens / wall, 2) if wall > 0 else None,
        "per_request_tokens_per_s": [r.tokens_per_s for r in ok_stats],
    }
    ok = len(ok_stats) == n
    return CheckResult("concurrency", ok, metrics, None if ok else f"실패 요청: {errors}")


def gpu_memory_mib() -> list[int] | None:
    """nvidia-smi가 있으면 GPU별 사용 메모리(MiB)를 돌려준다."""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    return [int(x) for x in out.split() if x.strip().isdigit()]


async def server_info(client: AsyncOpenAI) -> dict[str, Any]:
    """/models 응답에서 모델 id와 max_model_len(vLLM 확장 필드)을 읽는다."""
    try:
        page = await client.models.list()
    except Exception as e:  # 연결 실패도 결과에 남긴다
        return {"error": repr(e)[:200]}
    return {
        "models": [
            {"id": m.id, "max_model_len": getattr(m, "max_model_len", None)} for m in page.data
        ]
    }


CHECKS = ("simple", "json_schema", "tool_call", "long_input", "concurrency")


async def run_checks(
    client: AsyncOpenAI,
    model: str,
    checks: tuple[str, ...] = CHECKS,
    long_tokens: int = 12_000,
    concurrency: int = 4,
) -> list[CheckResult]:
    funcs = {
        "simple": lambda: check_simple(client, model),
        "json_schema": lambda: check_json_schema(client, model),
        "tool_call": lambda: check_tool_call(client, model),
        "long_input": lambda: check_long_input(client, model, long_tokens),
        "concurrency": lambda: check_concurrency(client, model, concurrency),
    }
    results = []
    for name in checks:
        try:
            results.append(await funcs[name]())
        except Exception as e:  # 한 항목이 죽어도 나머지는 계속 잰다
            results.append(CheckResult(name, False, error=repr(e)[:300]))
    return results


def to_markdown(results: list[CheckResult]) -> str:
    lines = ["| 항목 | 결과 | 주요 측정치 | 오류 |", "| --- | --- | --- | --- |"]
    for r in results:
        keys = [k for k in r.metrics if k not in ("sample", "raw", "content", "answer")]
        shown = ", ".join(f"{k}={r.metrics[k]}" for k in keys)
        lines.append(f"| {r.name} | {'통과' if r.passed else '실패'} | {shown} | {r.error or ''} |")
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--base-url", default=os.environ.get("LLM_BASE_URL"))
    p.add_argument("--model", default=os.environ.get("LLM_MODEL", "brain"))
    p.add_argument("--api-key", default=os.environ.get("LLM_API_KEY", "EMPTY"))
    p.add_argument("--label", required=True, help="결과 파일 이름표 (예: bf16, fp8)")
    p.add_argument("--vllm-flags", default="", help="서버 실행 플래그 (기록용)")
    p.add_argument("--checks", default=",".join(CHECKS))
    p.add_argument("--long-tokens", type=int, default=12_000)
    p.add_argument("--concurrency", type=int, default=4)
    p.add_argument("--timeout", type=float, default=180.0)
    p.add_argument("--out-dir", default=str(Path(__file__).parent / "results"))
    return p.parse_args(argv)


async def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.base_url:
        print("LLM_BASE_URL 또는 --base-url이 필요합니다.", file=sys.stderr)
        return 2
    checks = tuple(c.strip() for c in args.checks.split(",") if c.strip())
    unknown = set(checks) - set(CHECKS)
    if unknown:
        print(f"알 수 없는 항목: {sorted(unknown)}", file=sys.stderr)
        return 2

    client = AsyncOpenAI(base_url=args.base_url, api_key=args.api_key, timeout=args.timeout)
    info = await server_info(client)
    gpu_before = gpu_memory_mib()
    results = await run_checks(client, args.model, checks, args.long_tokens, args.concurrency)
    report = {
        "label": args.label,
        "model": args.model,
        "vllm_flags": args.vllm_flags,
        "run_at": datetime.now().isoformat(timespec="seconds"),
        "server": info,
        "gpu_memory_mib": {"before": gpu_before, "after": gpu_memory_mib()},
        "results": [asdict(r) for r in results],
    }
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{datetime.now():%Y-%m-%d}_smoke_{args.label}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"## smoke_llm — {args.label} ({args.model})\n")
    print(f"서버: {json.dumps(info, ensure_ascii=False)}")
    print(f"GPU 메모리(MiB): {report['gpu_memory_mib']}\n")
    print(to_markdown(results))
    print(f"\n결과 파일: {out}")
    return 0 if all(r.passed for r in results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

"""외부 LLM(Gemini API의 Gemma) [미확인] 항목 확인 (SPEC §8.2 모델 대안, §12.6, 2026-11-24).

확인 항목: Gemma 모델 이름, 운영 클라이언트(OpenAICompatLLM) 요청이 그대로 통하는지
(extra_body chat_template_kwargs, response_format json_schema), FileFacts 스키마 출력,
도구 호출(어시스턴트 TOOLS), 긴 입력(약 12K 토큰) 속도.
입력은 합성 문장뿐이다(실제 공고·프로필·사용자 데이터 없음).
API 키는 출력·파일에 남기지 않는다(규칙 4).
모델마다 약 5회 호출한다.

실행: uv run python -m scripts.probe_gemini --env-file ../.env --model <모델> [--model ...] \
        [--strip-extra-body --label <이름>]
      (모델 이름을 모르면 --model 없이 실행 → 목록만 출력)
.env: GEMINI_API_KEY=...
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from datetime import date
from pathlib import Path
from typing import Any

import openai
from dotenv import dotenv_values

from app.llm import client as llm_client
from app.llm.assistant import TOOLS
from app.llm.base import ToolCalls
from app.llm.client import OpenAICompatLLM
from app.llm.schemas import FileFacts
from app.llm.structured import model_schema

BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
RESULTS = Path(__file__).resolve().parents[2] / "eval" / "results"

RFP = """<document>
사업명: 합성 시험용 데이터 플랫폼 구축 사업
사업기간: 계약일로부터 6개월
사업예산: 금 350,000,000원(부가가치세 포함)
계약방법: 협상에 의한 계약, 기술평가 90점·가격평가 10점
제안서 제출 마감: 2026년 12월 15일 17시
입찰참가자격: 소프트웨어사업자(컴퓨터관련서비스사업) 신고 업체, 중소기업
과업 내용: 데이터 수집·정제 파이프라인 구축, 검색 기능 개발, 운영자 교육
</document>"""
FILLER = (
    "제3조(과업 범위) 수급인은 발주기관이 제시한 요구사항에 따라 "
    "데이터 수집, 정제, 적재, 검색 기능을 "
    "구현하고 시험 운영 결과를 보고서로 제출하여야 한다. 세부 일정은 착수 보고 때 협의하여 정한다. "
)


def _err(e: BaseException) -> str:
    cause = e.__cause__ or e
    return f"{type(e).__name__}: {type(cause).__name__} {str(cause)[:300]}"


async def _timed(coro: Any) -> tuple[Any, float]:
    t0 = time.perf_counter()
    out = await coro
    return out, round(time.perf_counter() - t0, 2)


async def probe(llm: OpenAICompatLLM, raw: openai.AsyncOpenAI, model: str) -> dict[str, Any]:
    r: dict[str, Any] = {"model": model}
    sys = {
        "role": "system",
        "content": "당신은 공공 입찰 문서를 정리하는 도우미입니다. 한국어로 답합니다.",
    }

    # 1. 운영과 같은 요청(extra_body 포함), 스키마 없음
    try:
        c, s = await _timed(
            llm.complete(
                "plain",
                [sys, {"role": "user", "content": "한 문장으로 자기소개를 해 주세요."}],
                json_schema=None,
                temperature=0.1,
                max_tokens=100,
            )
        )
        r["plain"] = {"ok": True, "s": s, "text": c.text[:120], "out_tok": c.completion_tokens}
    except Exception as e:  # noqa: BLE001 — 확인 스크립트: 실패 모양을 그대로 기록
        r["plain"] = {"ok": False, "error": _err(e)}
        # extra_body 때문인지 가린다
        try:
            await raw.chat.completions.create(
                model=model, messages=[{"role": "user", "content": "안녕"}], max_tokens=20
            )
            r["plain"]["without_extra_body"] = "ok"
        except Exception as e2:  # noqa: BLE001
            r["plain"]["without_extra_body"] = _err(e2)

    # 2. FileFacts json_schema (map 단계와 같은 스키마)
    try:
        c, s = await _timed(
            llm.complete(
                "extract_file",
                [sys, {"role": "user", "content": f"아래 문서에서 사실만 뽑아 JSON으로.\n{RFP}"}],
                json_schema=model_schema(FileFacts),
                temperature=0.1,
                max_tokens=4000,
            )
        )
        entry: dict[str, Any] = {"ok": True, "s": s, "out_tok": c.completion_tokens}
        entry["fenced"] = c.text.strip().startswith("```")
        try:
            ff = FileFacts.model_validate_json(c.text.strip().strip("`").removeprefix("json"))
            entry["valid"] = True
            entry["budget"] = ff.budget_contract.model_dump()
        except Exception as e:  # noqa: BLE001
            entry["valid"] = False
            entry["parse_error"] = str(e)[:300]
            entry["text_head"] = c.text[:300]
        r["schema"] = entry
    except Exception as e:  # noqa: BLE001
        r["schema"] = {"ok": False, "error": _err(e)}

    # 3. 도구 호출 (어시스턴트와 같은 TOOLS)
    try:
        calls: list[dict[str, Any]] = []
        text = ""
        t0 = time.perf_counter()
        async for ev in llm.chat_stream(
            [sys, {"role": "user", "content": "최근 7일 동안 올라온 AI 관련 공고를 찾아줘."}],
            tools=TOOLS,
            tool_choice="auto",
            temperature=0.3,
            max_tokens=500,
        ):
            if isinstance(ev, ToolCalls):
                calls += [{"name": c.name, "arguments": c.arguments} for c in ev.calls]
            elif hasattr(ev, "text"):
                text += ev.text
        r["tools"] = {
            "ok": True,
            "s": round(time.perf_counter() - t0, 2),
            "calls": calls,
            "text": text[:200],
        }
    except Exception as e:  # noqa: BLE001
        r["tools"] = {"ok": False, "error": _err(e)}

    # 4. 긴 입력 속도 (약 12K 토큰, map 청크 목표 크기)
    try:
        body = FILLER * 110
        c, s = await _timed(
            llm.complete(
                "long",
                [
                    sys,
                    {
                        "role": "user",
                        "content": f"<document>{body}</document>\n"
                        "과업 범위를 10줄로 정리해 주세요.",
                    },
                ],
                json_schema=None,
                temperature=0.1,
                max_tokens=800,
            )
        )
        r["long"] = {
            "ok": True,
            "s": s,
            "in_tok": c.prompt_tokens,
            "out_tok": c.completion_tokens,
            "out_tok_per_s": round(c.completion_tokens / s, 1) if s else None,
        }
    except Exception as e:  # noqa: BLE001
        r["long"] = {"ok": False, "error": _err(e)}
    return r


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env-file", default="../.env")
    ap.add_argument("--model", action="append", default=[])
    ap.add_argument("--base-url", default=BASE_URL)
    ap.add_argument("--label", default="", help="결과 파일 이름 뒤에 붙임")
    ap.add_argument(
        "--strip-extra-body",
        action="store_true",
        help="vLLM용 chat_template_kwargs를 빼고 보냄 (Gemini는 400, 2026-11-24 확인)",
    )
    a = ap.parse_args()
    if a.strip_extra_body:
        llm_client.NO_THINK = {}  # 확인 스크립트에서만: 운영 클라이언트는 그대로
    key = dotenv_values(a.env_file).get("GEMINI_API_KEY")
    if not key:
        raise SystemExit(f"{a.env_file}에 GEMINI_API_KEY가 없습니다")
    raw = openai.AsyncOpenAI(base_url=a.base_url, api_key=key, max_retries=0, timeout=120)
    models = sorted(m.id for m in (await raw.models.list()).data)
    gemma = [m for m in models if "gemma" in m.lower()]
    print("Gemma 모델:", *gemma, sep="\n  ")
    out: dict[str, Any] = {"date": date.today().isoformat(), "base_url": a.base_url, "gemma": gemma}
    out["strip_extra_body"] = a.strip_extra_body
    out["results"] = []
    for m in a.model:
        llm = OpenAICompatLLM(
            base_url=a.base_url,
            api_key=key,
            model=m,
            model_id="probe",
            timeout_s=360,
            max_concurrency=1,
            retry_delays=(5.0, 20.0),  # 503 '요청 몰림'은 잠깐 뒤 재시도
        )
        res = await probe(llm, raw, m)
        await llm.close()
        out["results"].append(res)
        print(json.dumps(res, ensure_ascii=False, indent=1))
    await raw.close()
    if a.model:
        suffix = f"_{a.label}" if a.label else ""
        path = RESULTS / f"{date.today().isoformat()}_probe_gemini{suffix}.json"
        path.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
        print("저장:", path)


if __name__ == "__main__":
    asyncio.run(main())

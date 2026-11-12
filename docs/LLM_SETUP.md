# LLM 서버 설정 기록 (P0-b, 2026-11-11)

SPEC §8.2·§11.3의 vLLM 구성을 GCP L4 VM에서 실제로 띄워 확인한 기록. 비교표는 `docs/decisions/2026-11-11-bf16-vs-fp8.md`. **채택: FP8** (아래 "실제로 쓴 명령"의 FP8 명령).

## 환경

| 항목 | 값 |
|---|---|
| GPU | NVIDIA L4 23,034 MiB, 드라이버 550.54.15 (CUDA 12.4까지), 시스템 nvcc 없음 |
| OS | Debian 11, glibc 2.31, RAM 31GB, 8코어, 디스크 여유 100GB(측정 전) → 74GB |
| vLLM | **0.19.1** (torch 2.10.0+cu128, transformers 5.22.2), Python 3.12, `~/vllm-p0b/.venv` |
| 모델 | `Qwen/Qwen3.5-9B` snapshot `c2022362`, 19GB, gated 아님(HF 토큰 불필요), `~/.cache/huggingface` |

## 실제로 쓴 명령

```bash
uv venv --python 3.12 ~/vllm-p0b/.venv
uv pip install --python ~/vllm-p0b/.venv/bin/python "vllm==0.19.1"
uvx --from "huggingface_hub[hf_transfer]" hf download Qwen/Qwen3.5-9B

# FP8 (BF16은 --quantization fp8을 빼고 --gpu-memory-utilization 0.95)
~/vllm-p0b/.venv/bin/vllm serve Qwen/Qwen3.5-9B --served-model-name brain \
  --quantization fp8 --max-model-len 32768 --max-num-seqs 8 --gpu-memory-utilization 0.90 \
  --language-model-only --reasoning-parser qwen3 \
  --enable-auto-tool-choice --tool-call-parser qwen3_coder \
  --default-chat-template-kwargs '{"enable_thinking": false}' \
  --api-key "$LLM_API_KEY" --host 127.0.0.1 --port 8011

LLM_BASE_URL=http://127.0.0.1:8011/v1 LLM_MODEL=brain uv run eval/smoke_llm.py --label fp8
uv run eval/smoke_llm.py --label fp8_warm_c8 --checks simple,concurrency --concurrency 8
```

결과 원본: `eval/results/2026-11-11_smoke_{bf16,fp8}{,_warm_c8}.json`

## [미확인] 플래그 확인 결과

| 플래그 | 결과 |
|---|---|
| `--quantization fp8` | ✅ 동작. 온라인 FP8로 가중치 16.8 → 10.36 GiB |
| `--max-model-len 32768` | FP8 ✅(0.90에서). **BF16 ❌(0.90)**: KV 0.89 GiB < 필요 1.06 GiB, vLLM 추정 최대 27,456. BF16은 0.95로 올려야 기동 |
| `--max-num-seqs 8` | ✅ 둘 다. 동시 8요청이 대기 없이 `Running: 8 reqs`로 처리됨 |
| `--language-model-only` | ✅ 둘 다 수용 (BF16 가중치 16.8 GiB, 디스크 19GB 대비 비전 인코더 제외) |
| `--tool-call-parser qwen3_coder` | ✅ 둘 다 `search_bids` 호출·인자 JSON 정상 → `qwen3_xml` 폴백 불필요(미시험) |
| `--default-chat-template-kwargs` 생각 끔 | ✅ 응답에 `<think>` 없음 |

## 막힌 곳

1. **드라이버 550 → vLLM 0.19.1이 상한.** vLLM 0.20~0.33(최신)은 torch 2.11 이상이 CUDA 13.0 빌드라 드라이버 580 이상이 필요하다. 0.20.x는 glibc 2.35도 요구한다. SPEC 최소(0.17)는 만족한다. 최신을 쓰려면 드라이버 업그레이드(sudo·재부팅)가 필요하다.
2. **포트**: SPEC의 vLLM 8001은 v1 API(uvicorn)가 쓰고 있고 8000도 다른 프로세스가 쓰고 있어 측정은 8011에서 했다. 운영 포트는 P4 전환 때 정한다.
3. **v1 vLLM 중지**: 사용자 지시로 `sudo systemctl stop nara-vllm`(15.2GB 점유)과 `disable` 실행. v1 채팅·분석은 이제 동작하지 않는다.
4. vLLM 경고: v0.19에서 CUDA graph 메모리 프로파일링이 기본이 될 예정이며, 같은 KV를 유지하려면 `--gpu-memory-utilization`을 약 0.004 올리라고 안내한다. 측정에는 영향 없음.
5. 첫 요청 TTFT(약 3초)는 워밍업이다. 비교에는 워밍업 뒤 값을 쓴다.

## 실제 파이프라인에서 잰 값 (P3a-2, 2026-11-12)

| 항목 | 값 |
|---|---|
| 생성 속도 | 단일 요청 약 24토큰/초. 동시 3요청 합계 64~67토큰/초(요청당 약 22), 4요청이면 요청당 약 17 (vLLM `loggers.py` 10초 평균) |
| 요약 map 출력 | 모델용 스키마를 모두 required로 한 뒤 1,043~2,113토큰(청크 4건) → 최대 출력 4,000, `LLM_TIMEOUT_S` 360 |
| 골든셋 | 19건 순차 실행 v1 2,795초. 결과·원인 분석은 `docs/decisions/2026-11-12-p3a2-real-llm.md` |

## 남은 일

- FP8 품질(추출 정확도·환각률)은 골든셋 라벨 확정 뒤 판단한다(초안 라벨 결과는 위 결정 기록).
- MTP 추론 가속, prefix caching은 시험하지 않았다(§8.2 선택 항목).
- 운영 유닛(§11.3)은 `/opt/nara/vllm-venv`, `User=nara`를 가정한다. P4에서 sudo로 만든다.

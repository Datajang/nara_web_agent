# vLLM MTP 추론 가속 시험 (SPEC §8.2 선택 항목, 2026-11-24 준비)

**운영자가 직접 실행한다.** 목적: 분석 시간의 약 60%인 단일 요청 생성 속도(23.5토큰/초)를 올린다
(`docs/decisions/2026-11-24-llm-concurrency.md`). 사전 확인(읽기만): 설치된 vLLM 0.19.1에 `qwen3_5_mtp`가 있고,
Qwen3.5-9B에 MTP 층 1개(`mtp.*` 텐서 15개)가 들어 있다. 본 모델은 `mtp.*`를 건너뛰고 MTP 쪽이 따로 읽는다.
동작 여부(FP8·`--language-model-only`·json_schema와 함께)는 기동해 봐야 안다.

- vLLM 재시작 동안(약 3~5분) LLM 기능이 멈춘다 → **분석·어시스턴트 쓰는 사람이 없을 때** 한다.
- 원본 유닛은 건드리지 않고 drop-in으로 덧씌운다. `deploy.sh`는 `deploy/systemd/*` 파일만 복사하므로 drop-in은 남는다
  (채택하면 저장소 유닛에 옮기고 drop-in을 지운다).

## 1. 지금 상태 측정 (저장소 루트에서, 약 1분)
```bash
cd /home/Seungil/AX_Team_Nara_bot
export LLM_BASE_URL=http://127.0.0.1:8011/v1 LLM_API_KEY="$(sudo sed -n 's/^VLLM_API_KEY=//p' /etc/nara/vllm.env)"
uv run eval/smoke_llm.py --label fp8-base
```

## 2. MTP 켜기
```bash
sudo mkdir -p /etc/systemd/system/nara-vllm.service.d
sudo tee /etc/systemd/system/nara-vllm.service.d/mtp.conf >/dev/null <<'EOF'
[Service]
ExecStart=
ExecStart=/opt/nara/vllm-venv/bin/vllm serve Qwen/Qwen3.5-9B \
    --served-model-name brain \
    --quantization fp8 \
    --max-model-len 32768 \
    --max-num-seqs 8 \
    --gpu-memory-utilization 0.90 \
    --language-model-only \
    --reasoning-parser qwen3 \
    --enable-auto-tool-choice \
    --tool-call-parser qwen3_coder \
    --default-chat-template-kwargs '{"enable_thinking": false}' \
    --speculative-config '{"method": "mtp", "num_speculative_tokens": 1}' \
    --host 127.0.0.1 --port 8011
EOF
sudo systemctl daemon-reload && sudo systemctl restart nara-vllm
sudo journalctl -u nara-vllm -f    # 'Application startup complete'가 나오면 Ctrl+C. 오류면 4번(되돌리기)
sudo journalctl -u nara-vllm --since "10 min ago" --no-pager | grep -iE 'speculative|mtp|KV cache size|Maximum concurrency|error' | tail -15
curl -s http://127.0.0.1:8010/readyz
```

## 3. MTP 상태 측정
```bash
uv run eval/smoke_llm.py --label fp8-mtp1          # 1번과 같은 셸(환경변수 그대로)
```
그다음 **아직 분석한 적 없는 공고** 하나를 분석하고 아래 둘을 붙여 준다.
```bash
sudo journalctl -u nara-vllm --since "15 min ago" --no-pager | grep -E 'SpecDecoding|Running' | tail -40
sudo -u postgres psql -p 5434 -d nara -X -c "SELECT created_at AT TIME ZONE 'Asia/Seoul' AS kst, llm_calls, completion_tokens, round(duration_ms/1000.0,1) AS sec, cache FROM usage_logs WHERE event='analyze' ORDER BY id DESC LIMIT 3"
```
결과 파일 `eval/results/<날짜>_smoke_fp8-{base,mtp1}.json`은 Claude가 비교한다.

## 4. 되돌리기 (기동 실패, 스키마·도구 호출 실패, 느려짐)
```bash
sudo rm /etc/systemd/system/nara-vllm.service.d/mtp.conf
sudo systemctl daemon-reload && sudo systemctl restart nara-vllm
```

## 판단 기준
- 채택: smoke 5항목 통과(특히 json_schema·tool_call), 단일 요청 토큰/초 1.3배 이상, 분석 시간 단축, 동시 4요청 합계가 크게 줄지 않음
- 기록: 결과는 `docs/decisions/`에 남기고, 채택하면 저장소 `deploy/systemd/nara-vllm.service`·SPEC §8.2·`docs/LLM_SETUP.md`를 고친다

## 5. 채택 뒤 정리 (2026-11-24 채택, `docs/decisions/2026-11-24-mtp.md`)
저장소 유닛에 MTP 플래그를 넣었다. **다음 배포로 유닛이 깔린 뒤** drop-in을 지운다(내용이 같아 vLLM 재시작은 필요 없음).
```bash
grep -c speculative /etc/systemd/system/nara-vllm.service   # 1이면 새 유닛이 깔림
sudo rm /etc/systemd/system/nara-vllm.service.d/mtp.conf && sudo rmdir /etc/systemd/system/nara-vllm.service.d
sudo systemctl daemon-reload && systemctl cat nara-vllm | grep -c speculative   # 1
```

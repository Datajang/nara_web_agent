# 진행 기록

단계마다 '한 일 / 달라진 결정 / 남은 문제'를 3~5줄로 남긴다 (SPEC §13).

## P0-a — 저장소 정리·CI·테스트 골격 (2026-11-11, 태그 전 확인 대기)

- **한 일**: v1 재사용 모듈(extractor, section_extractor, g2b 순수 함수)을 `backend/app`으로 옮겼다. 나머지 v1 코드는 삭제(참조는 `61519ad`). Vite+Vue3+TS 프론트 골격, `.github/workflows/ci.yml` PR 게이트, `eval/smoke_llm.py`(5항목, 미실행)를 만들었다. pytest 31개 통과.
- **달라진 결정**: Python 3.12로 실행, `uv.lock` 추적, vitest ^5(npm peer 오류 회피), oxlint 제거. 실패 테스트 8개는 고침 2 / 버림 6. `is_bid_open`이 `YYYYMMDD`를 잘못 읽던 v1 버그를 고쳤다 (`docs/decisions/2026-11-11-*`).
- **남은 문제**: SPEC 수정 제안 대기(§2 docx 원인, §5.2 날짜 4종, vLLM 포트 8001이 v1 API 포트와 겹침). 첨부 다운로드의 curl `--insecure`는 P1에서 확인. gitleaks pre-commit 미도입. CI가 GitHub에서 실제로 초록인지는 push 후 확인해야 함. P0-b(vLLM 실측)는 GPU 서버에서 진행.

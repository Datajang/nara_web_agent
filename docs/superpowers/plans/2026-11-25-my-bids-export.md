# 투찰 결과 엑셀 다운로드 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 투찰 결과 탭의 현재 조건 목록을 요약 + 연도별 시트 xlsx로 내려받는다.
**Architecture:** 서버 `app/awards/mybids_export.py`가 `mybids.page`로 전부 모아 openpyxl로 만든다. 라우터 `GET /my-bids/export`. 프론트는 `requestBlob` + `saveBlob`.
**Tech Stack:** FastAPI, openpyxl, Vue 3, vitest.
**Spec:** `docs/superpowers/specs/2026-11-25-my-bids-export-design.md`

## Global Constraints
- 열·시트 이름·문구는 spec 그대로. 글자 칸은 `data_type="s"`(수식 주입 방지)
- API 스키마 변경 뒤 `scripts.export_openapi` + `npm run gen:api`
- ruff·mypy·pytest·lint·typecheck·test·build 통과

## Review Focus
- 등록일이 12/31 15:00Z 이후(KST 1/1)인 행은 다음 해 시트로 → 단위 테스트
- 구성원 낙찰 행: 투찰금액·순위 빈칸, 금액 합계는 지분만큼 → 단위 테스트
- `=`로 시작하는 사업명이 수식이 되지 않음 → 단위 테스트
- 결과 필터 'lost'면 낙찰 행 없음, 기간 거꾸로 422 → 통합 테스트
- 0건이면 요약 시트만(연도 시트 없음) → 단위 테스트

### Task 1: 서버 엑셀 + API
**Files:** Create `backend/app/awards/mybids_export.py`, `backend/tests/unit/test_mybids_export.py`; Modify `backend/app/api/routers/mybids.py`, `backend/tests/integration/test_api_mybids.py`
**Produces:** `build_xlsx(items: list[MyBidOut], scan_done: int, cond: str, now: datetime, origin: str) -> bytes`, `export_filename(now) -> str` (`{YYYY-MM-DD}_투찰 결과.xlsx`)
- [ ] 단위 테스트(위 Review Focus 1·2·3·5 + 14열 머리글·요약 행 값) 작성 → 실패 확인
- [ ] 구현 → 통과
- [ ] 통합 테스트 `test_export_follows_filters`(전체·lost·422, content-type, 시트 이름) → 라우터 구현 → 통과
- [ ] openapi 갱신, 커밋

### Task 2: 프론트 버튼
**Files:** Modify `frontend/src/api/mybids.ts`, `frontend/src/components/awards/MyBidsPanel.vue`, `frontend/src/copy.ts`; Test `frontend/tests/myBids.test.ts`
- [ ] 테스트: 버튼 클릭 → `GET /api/v1/my-bids/export?result=lost&from=…` 호출, 파일 이름 `{KST 날짜}_투찰 결과.xlsx`; 목록이 비면 disabled → 실패 확인
- [ ] `myBidsApi.exportXlsx(result, narrow)`, 버튼(Download 아이콘, '엑셀 다운로드') 구현 → 통과
- [ ] 문서(`docs/PROGRESS_ops_feedback.md` 한 줄), 전체 검사, 커밋

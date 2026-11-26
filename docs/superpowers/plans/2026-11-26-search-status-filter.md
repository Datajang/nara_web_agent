# 공고 검색 상태 마감·유찰 + 빠진 마감 공고 알림 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 검색 상태에 마감·유찰을 더하고, '진행중' 검색에서 빠진 마감 공고 수를 알려 한 번에 보이게 한다.
**Architecture:** `SearchQuery.status`에 closed·failed 추가(`build_query`의 SQL 조건). 서비스가 status=open일 때
같은 조건 + closed로 COUNT 한 번 → `SearchResult.hidden_closed` → API → SearchView 알림 줄·빈 상태 버튼.
**Tech Stack:** FastAPI·SQLAlchemy(PG16), Vue 3·vitest.
**Spec:** `docs/superpowers/specs/2026-11-26-search-status-filter-design.md`

## Global Constraints
- UI 문구 한국어. 화면 요청에서 G2B 호출 늘지 않음(COUNT는 DB만). 취소공고는 모든 상태에서 제외
- 유찰 규칙 = `docs/BID_OUTCOME.md`(현재 차수 raw bidNtceOrd, 낙찰 행 없음, 분류마다 마지막 rbid가 모두 '유찰')
- 추천(`status="open"`)·어시스턴트 도구 enum(open/all)은 그대로. API 바꾸면 openapi·schema 재생성

## Review Focus
- 정정공고(현재 차수 001): 000 차수의 유찰 행만 있으면 유찰 아님
- 분류 2개 중 1개만 유찰 / 유찰 뒤 재입찰 001이 개찰완료 → 유찰 아님
- 사전규격·마감일 없는 공고는 유찰·마감에서 빠짐
- hidden_closed는 status≠open이면 0, 취소공고는 세지 않음
- 알림 버튼을 누르면 URL status=all로 다시 검색(뒤로 가기 복원)

---

### Task 1: 백엔드 상태 조건 + hidden_closed
**Files:** `backend/app/search/query.py`, `backend/app/search/service.py`, `backend/app/api/schemas/bids.py`,
`backend/app/api/routers/bids.py`, Test: `backend/tests/integration/test_search.py`, `tests/integration/test_api_bids.py`
**Produces:** `status: Literal["open","closed","failed","all"]`, `failed_only() -> ColumnElement[bool]`,
`SearchResult.hidden_closed: int`, `SearchResultOut.hidden_closed: int`

- [ ] 실패 테스트: `test_status_closed_and_failed`(진행중·마감·유찰·정정 차수·분류 혼합·재입찰 뒤 개찰완료·사전규격 시드 →
  closed = 마감된 regular+prespec, failed = 순수 유찰 공고만), `test_hidden_closed_counts_only_for_open`(open이면 마감 수, all이면 0, 취소 제외)
- [ ] API 응답 키 집합에 `hidden_closed` 추가(test_api_bids)
- [ ] 구현: closed = `deadline_at <= now`; failed = closed ∧ regular ∧ EXISTS 유찰 행(현재 차수) ∧ NOT EXISTS 낙찰 행(현재 차수)
  ∧ NOT EXISTS (현재 차수의 '유찰' 아닌 행 r, r보다 큰 rbid가 같은 분류에 없음). 현재 차수 = `coalesce(raw->>'bidNtceOrd','000')`
- [ ] `find_bids`에서 status=open이면 `select count()`(build_query를 status=closed로, limit 없음) → hidden_closed
- [ ] `uv run pytest -q tests/integration/test_search.py tests/integration/test_api_bids.py` 통과 → 커밋

### Task 2: 프론트 옵션 + 알림
**Files:** `frontend/src/composables/useUrlState.ts`, `src/views/SearchView.vue`, `src/copy.ts`, `src/api` 타입(schema 재생성),
Test: `frontend/tests/searchView.test.ts`
- [ ] 실패 테스트: 상태 4개 옵션; hidden_closed=3이면 알림 줄 + 버튼 → 다음 검색 body.status='all'·URL status=all;
  items 0 + hidden_closed>0이면 빈 상태에 버튼; hidden_closed=0이면 알림 없음; URL `status=failed` 복원
- [ ] 구현: Status 타입·pick 목록·fromRunQuery 확장, copy `statusClosed:'마감' statusFailed:'유찰' hiddenClosed(n) showClosed emptyOpenOnly(n)`
- [ ] `npm run lint && npm run typecheck && npm run test && npm run build` → 커밋

### Task 3: 문서
- [ ] SPEC §6.3 status 값·`hidden_closed` 한 줄, `docs/PROGRESS_ops_feedback.md` 한 줄(80줄 이하)
- [ ] 백엔드 전체 검사(ruff·format·mypy·pytest) → 커밋

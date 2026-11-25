# 마감 공고 사유 표시 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 마감된 공고 카드·상세에 낙찰·유찰·개찰완료·재입찰·개찰 전·결과 대기·의견 마감 배지.
**Architecture:** 새 수집 소스 `status`(개찰결과 목록, inqryDiv=3 개찰일시, 기존 `_collect`·커버리지·한 페이지 분할 재사용) →
`bid_opening_status`. 카드 빌더가 `bid_awards`·`bid_opening_status`·개찰일로 `outcome`을 만든다.
**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Vue 3, vitest. **Spec:** `docs/superpowers/specs/2026-11-26-closed-bid-reason-design.md`

## Global Constraints
- G2B 호출은 `G2BClient`로만, 예산 `G2B_STATUS_DAILY_BUDGET`(3000, label '개찰 상태'), 키는 낙찰 키
- DB는 Alembic 0014만. 화면 요청은 G2B를 부르지 않는다. UI 문구 한국어

## Review Focus
- 정정공고: 현재 차수(raw bidNtceOrd)와 다른 차수의 낙찰·상태 행은 무시 → outcome 단위 테스트
- 분류 둘 중 하나 유찰·하나 개찰완료 → 개찰완료(유찰 아님); 재입찰 000 → 001 개찰완료 → 개찰완료 → 단위 테스트
- 하루 999행 초과 → 시간 분할(기존 `_fetch_whole`) → 수집 통합 테스트에서 page_size 작게
- 취소공고·진행 중 공고·사전규격 진행 중 → outcome null → 단위 테스트
- 같은 키 다시 받기 → 덮어쓰기(상태 재입찰 → 개찰완료) → 수집 통합 테스트

### Task 1: 수집 소스 `status`
**Files:** `app/db/models/awards.py`(BidOpeningStatus), `alembic/versions/0014_opening_status.py`, `app/g2b/client.py`, `app/runtime.py`,
`app/config.py`, `app/awards/status.py`(new: `to_status`, `status_store`, `incremental`, `backfill`), `app/collector/__main__.py`,
`deploy/systemd/nara-collector*.service`, `tests/fakes/g2b.py`(inqryDiv=3 창), tests unit+integration
- [ ] 테스트: `to_status`(1순위 `opengCorpInfo` 분해, 문구 200자), 수집 incremental 어제·오늘 창 + upsert 덮어쓰기 + 분할 → 실패 확인 → 구현 → 통과

### Task 2: outcome 판정·API
**Files:** `app/bids/outcome.py`(new: `decide(bid, now, awards, statuses) -> BidOutcome | None`, `load_outcomes(s, bids, now)`),
`app/bids/cards.py`(BidCard.outcome), openapi 재생성, tests
- [ ] 단위 테스트(설계 판정 순서 1~6 + Review Focus) → 구현 → 통합(검색 카드에 outcome) → 통과

### Task 3: 화면 배지
**Files:** `frontend/src/components/bid/OutcomeBadge.vue`(new), `BidCard.vue`, `views/BidDetailView.vue`, `copy.ts`, tests
- [ ] 테스트(종류별 문구·색, 진행 중 없음) → 구현 → lint·typecheck·test·build

### Task 4: 문서
- `docs/PROGRESS_ops_feedback.md` 한 줄, `docs/ops/RUNBOOK.md`에 첫 백필 명령, 전체 검사

# 분석 결과 개편 + 진행 로딩바 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 분석 중 실제 진행률 로딩바를 보여 주고(A), 분석 결과를 요약과 겹치지 않는 '사업 이해·적합도·필요한 것' 중심으로 바꾼다(B).

**Architecture:** A는 요약 map 단계가 조각마다 `status(summarize, progress)`를, 분석 단계가 `expected_s`를 보내고, 프론트 순수 함수가 막대 %·남은 시간을 계산한다. B는 LLM 출력 스키마 `AnalysisOut`과 저장 스키마 `AnalysisResult`(= Out + 서버가 정한 `profile_brief`)로 나누고, 예전 결과는 `LegacyAnalysisResult`로 계속 읽는다. PROMPT_VERSION v10.

**Tech Stack:** FastAPI·Pydantic v2·pytest(PG16) / Vue 3·TS·Vitest·Tailwind 토큰.

**Spec:** `docs/superpowers/specs/2026-11-16-analysis-restructure-progress-design.md`

## Global Constraints
- UI 문구 한국어, 식별자 영어. TDD(실패 확인 후 구현).
- 게이트: `cd backend && uv run ruff check . ../eval && uv run ruff format --check . ../eval && uv run mypy app ../eval && uv run pytest -q`, `cd frontend && npm run lint && npm run typecheck && npm run test && npm run build`.
- API 스키마를 바꾸면 `uv run python -m scripts.export_openapi && cd ../frontend && npm run gen:api`.
- 명세는 Claude Docs 원본(project `4U6mSLGjySeEKqkSyQCpcx`, node `4292f572-8c36`)에서 고치고 export → 3번째 줄 머리말·'(다이어그램 생략' 두 줄 복원.
- docs 파일 80줄 이하. 커밋 끝에 `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. CLAUDE_before.md 커밋 금지.
- 분석 단계 실측(골든셋 v8·v9, 38건): 중앙값 약 89초, p90 101초 → `analyze_expected_s = 90`.
- `profile_min_chars = 200`(정규화한 팀 소개 글자 수).

## Review Focus
1. 예전(v9 이하) 분석을 '내 기록'에서 열 때 500 없이 옛 화면으로 보인다 → Task 4·6 테스트.
2. 요약이 캐시 적중이고 분석만 새로 할 때 막대가 10%에 머물지 않고 분석 구간(75%~)으로 간다 → Task 2 테스트.
3. 예상 시간을 넘긴 분석은 남은 시간을 음수·0분으로 쓰지 않고 '거의 다 됐어요' → Task 2 테스트.
4. 오류(in_progress·끊김)가 나면 막대가 사라진다 → Task 2 테스트.
5. 팀 소개가 정확히 200자면 상세(brief 아님), 199자면 brief → Task 5 테스트.

---

## A. 진행 로딩바

### Task 1: 백엔드 진행 이벤트

**Files:** Modify `backend/app/pipeline/summarize.py`(`_summarize`의 gather), `backend/app/pipeline/analyze.py`(analyze status), `backend/app/config.py`(`analyze_expected_s: int = 90`), `backend/app/api/schemas/events.py`(`StatusEvent.expected_s: int | None = None`), openapi·`frontend/src/api/schema.d.ts` 재생성. Test: `backend/tests/integration/test_pipeline_llm.py`.

**Interfaces — Produces:** status 이벤트 `{"stage":"summarize","progress":{"done":k,"total":n}}`(k=0..n, 조각 하나 끝날 때마다, 반쪽 재시도는 1조각으로 셈), `{"stage":"analyze","expected_s":90}`.

- [ ] **Step 1: 실패 테스트** — `test_summary_reports_chunk_progress`: `monkeypatch.setattr(sm, "CHUNK_TARGET", 작게)`·`SINGLE_MAX` 작게로 3조각 이상 만들고 `usage.track(on_status=events.append)` 아래 `get_or_create_summary`. 단언: summarize progress 목록의 첫 값 `done == 0`, 마지막 `done == total == 선택된 조각 수`, done이 줄지 않음. `test_analyze_status_carries_expected_seconds`: 분석 status에 `expected_s == deps.settings.analyze_expected_s`.
- [ ] **Step 2:** `uv run pytest tests/integration/test_pipeline_llm.py -k "progress or expected" -q` → FAIL.
- [ ] **Step 3:** gather 전에 `usage.status("summarize", "문서를 읽고 있어요", progress={"done":0,"total":n}, cache=False)`, 각 `_map_chunk`를 감싼 코루틴이 끝날 때 카운터를 올려 같은 status를 보낸다(메시지 `f"문서를 읽고 있어요 ({k}/{n})"`). analyze의 `usage.status("analyze", …)`에 `expected_s=deps.settings.analyze_expected_s`.
- [ ] **Step 4:** 같은 명령 PASS, openapi export·gen:api, 백엔드 게이트 전체.
- [ ] **Step 5:** 커밋 `feat: 요약 조각 진행률·분석 예상 시간을 SSE로 (§6.4)`.

### Task 2: 프론트 로딩바

**Files:** Create `frontend/src/components/bid/progress.ts`, `frontend/src/components/bid/AnalyzeProgress.vue`, `frontend/tests/analyzeProgress.test.ts`. Modify `frontend/src/views/BidDetailView.vue`(ProgressSteps 아래), `frontend/src/copy.ts`(`copy.progress`).

**Interfaces — Produces:**
```ts
export interface Stamped { stage: Stage; progress?: { done: number; total: number } | null; expected_s?: number | null; at: number } // at = 받은 시각(ms)
export const DEFAULT_ANALYZE_S = 90
export function progressState(stamped: Stamped[], startedAt: number, now: number): { percent: number; elapsedS: number; remainingS: number | null }
export function formatDuration(s: number): string // 45 → '45초', 80 → '1분 20초'
```
규칙: 없음 0%/null · files 5 · extract 10 · summarize `10 + 60*done/total`(progress 없으면 10), 남은 시간은 done≥1일 때 `(경과/done)*(total-done) + 첫 조각까지 걸린 시간 + DEFAULT_ANALYZE_S`, done=0이면 null · analyze `75 + 20*min(1, e/expected)`, 남은 시간 `max(0, expected - e)`(e = analyze 이벤트 이후 초, expected = 이벤트 값 ?? DEFAULT). percent는 정수로 내림.
copy: `progress.label '분석 진행률'`, `progress.elapsed(t) => \`경과 ${t}\``, `progress.remaining(s) => s < 60 ? '1분 이내 남음' : \`약 ${Math.ceil(s/60)}분 남음\``, `progress.almostDone '거의 다 됐어요'`.

- [ ] **Step 1: 실패 테스트**(`analyzeProgress.test.ts`): `progressState` — 빈 배열 → `{percent:0, remainingS:null}`; summarize 3/6(at 30s, 첫 조각 10s) → percent 40, remainingS = 30/3*3+10+90 = 130; summarize 0/6 → remainingS null; 요약 이벤트 없이 analyze만(캐시 적중) at=0, now=45s → percent 85, remainingS 45; analyze now=200s → percent 95, remainingS 0. `formatDuration(80) === '1분 20초'`. 컴포넌트 — fake timers로 마운트, `role="progressbar"`·`aria-valuenow`, 남은 0초면 `copy.progress.almostDone` 표시; detailView에서 `error` 이벤트 뒤 progressbar 없음.
- [ ] **Step 2:** `./node_modules/.bin/vitest run tests/analyzeProgress.test.ts` → FAIL.
- [ ] **Step 3:** 구현. `AnalyzeProgress.vue` props `{ events: StreamEvent[] }`; 새 status 이벤트가 들어오면 `Date.now()`로 도장, 1초 `setInterval`로 now 갱신(언마운트 때 해제). 막대는 토큰 색(`bg-primary` 채움, `bg-surface-2` 바탕), `motion-reduce` 존중. BidDetailView: `v-if="sse.streaming.value && !sse.error.value && hasStatus"`.
- [ ] **Step 4:** 프론트 게이트 전체 PASS.
- [ ] **Step 5:** 커밋 `feat: 분석 진행 로딩바 — 조각 진행률·경과·남은 시간 (§7.5-4)`.

### Task 3: A 마무리 — 명세·실화면 확인
- [ ] 명세 §6.4(status `progress`는 summarize·score, `expected_s`는 analyze)·§7.5-4(막대·경과·남은 시간, 캐시 적중·오류 때 숨김) 수정 후 export·복원.
- [ ] 개발 서버 재기동(빌드본 preview 127.0.0.1:5173) 후 실제 vLLM으로 새 공고 1건 분석, Playwright 스크린샷으로 막대 확인.
- [ ] `docs/PROGRESS.md` 한 줄, 커밋·push.

## B. 분석 결과 개편 (v10)

### Task 4: 스키마·예전 결과 호환

**Files:** Modify `backend/app/llm/schemas.py`, `backend/app/llm/structured.py`(CAPS), `backend/app/api/schemas/history.py`·`events.py`, `backend/app/api/routers/history.py:120`, `backend/app/llm/fake.py`, openapi·schema.d.ts, `frontend/src/api/types.ts`. Tests: `backend/tests/unit/test_llm_structured.py`, `backend/tests/integration/test_api_history.py`, `backend/tests/unit/test_llm_fake.py`.

**Interfaces — Produces:**
```python
class Understanding(BaseModel): purpose: str; scope: list[str] = []; conditions: list[str] = []
class Fit(BaseModel): score: int (0~100); verdict: Literal[...]; reasoning: str        # strengths·gaps 제거
class TeamNeeds(BaseModel): have: list[str] = []; need: list[str] = []
class AnalysisOut(BaseModel):  # LLM 출력, 순서 = 화면 순서
    understanding: Understanding; fit: Fit; team_needs: TeamNeeds
    profile_missing: list[str] = []; risks: list[Risk]; next_actions: list[str]; warnings: list[str] = []
class AnalysisResult(AnalysisOut): profile_brief: bool = False   # 서버가 정함
class LegacyFit / LegacyAnalysisResult  # 지금 Fit·AnalysisResult 그대로 이름만 바꿈
AnyAnalysis = AnalysisResult | LegacyAnalysisResult
BidSummary.scope: list[str] = []
```
CAPS: `Understanding.purpose` 300자, `Understanding.scope` 8개·80자, `Understanding.conditions` 5개·80자, `TeamNeeds.have`·`need` 5개·100자, `AnalysisOut.profile_missing` 5개·60자, `Fit.reasoning` 300자, `BidSummary.scope` 8개·60자. TS: `AnalysisResult`, `LegacyAnalysisResult`, `AnyAnalysis`, `isLegacy(a): a is LegacyAnalysisResult`(`!('understanding' in a)`).

- [ ] **Step 1: 실패 테스트** — `test_analysis_caps_apply`(AnalysisOut 스키마의 profile_missing maxItems 5, Understanding.scope maxItems 8); `test_old_analysis_still_opens`(v9 모양 result를 analyses에 직접 넣고 `GET /analyses/{id}` 200, 응답 analysis에 `requirements` 있음); 가짜 LLM 분석이 `AnalysisOut`으로 검증됨.
- [ ] **Step 2:** FAIL 확인. **Step 3:** 구현(history·ResultEvent의 타입은 `AnyAnalysis`, history는 `TypeAdapter(AnyAnalysis)`). **Step 4:** 게이트(파이프라인 테스트 중 requirements를 보던 분석 단언은 Task 5에서 고치므로 여기서는 깨지면 `xfail` 말고 같이 고친다). **Step 5:** 커밋.

### Task 5: 파이프라인·프롬프트 v10

**Files:** Modify `backend/app/pipeline/analyze.py`, `backend/app/llm/prompts/analyze_bid.md`, `summarize_bid.md`, `backend/app/llm/versions.py`(`"v10"` + 주석), `backend/app/conversations/tools.py`(payload `overview` → `understanding.purpose`), `backend/app/pipeline/summarize.py`(fake 포함 scope). Tests: `test_pipeline_llm.py`, `test_prompts.py`, `test_assistant.py`, `test_api_history.py`(버전 문자열).

**Interfaces — Consumes:** Task 4 스키마. **Produces:** `is_brief(profile_text: str, min_chars: int) -> bool`(`len(normalize_profile(t)) < min_chars`), `render("analyze_bid", …, profile_detail="brief"|"detailed")`, `render_markdown(r: AnalysisResult) -> str` 제목 순서 `사업 이해 → 우리 팀 적합도 → 우리 팀에 필요한 것 → (프로필 보완) → 리스크·유의사항 → 다음 할 일`.

프롬프트 규칙(analyze_bid.md, 기준표는 그대로): understanding은 '무엇을 왜 하는 사업인지'를 summary.overview·scope·key_requirements에서; conditions에 금액·날짜를 쓰지 말 것; team_needs는 프로필에 적힌 사실만, 없으면 need나 profile_missing으로; `<profile_detail>`이 brief면 have·need 각 3개 이하; profile_missing은 이 공고 판단에 필요한데 프로필에 없는 정보(예: 'PM 자격 보유 여부'). summarize_bid.md: scope는 FileFacts.scope를 합쳐 8개 이내.

- [ ] **Step 1: 실패 테스트** — `test_analysis_has_only_new_sections`(result 키 집합 = understanding·fit·team_needs·profile_missing·risks·next_actions·warnings·profile_brief); `test_profile_brief_threshold`(199자 → True, 200자 → False, 프롬프트 user에 `<profile_detail>brief`); `test_summary_keeps_scope`; `test_markdown_follows_new_order`; 조수 도구 payload에 `purpose`.
- [ ] **Step 2:** FAIL. **Step 3:** 구현. 분석에서 requirements 관련 check_evidence·attach_sources 제거, risks의 known_source·ground·경고 처리 유지, `result.profile_brief = is_brief(...)`. **Step 4:** 게이트. **Step 5:** 커밋.

### Task 6: 분석 화면·프로필 안내

**Files:** Create `frontend/src/components/bid/AnalysisResultLegacy.vue`(지금 AnalysisResultView 내용을 옮김). Modify `AnalysisResultView.vue`, `BidDetailView.vue`(타입 `AnyAnalysis`), `copy.ts`, `views/settings/ProfilesView.vue`(안내 한 줄). Tests: `frontend/tests/detailView.test.ts`, `components.test.ts`.

copy(정확히): `analysis.understanding '사업 이해'`, `purpose '목적·배경'`, `scope '과업 범위·주요 기능'`, `conditions '수행 조건'`, `teamNeeds '우리 팀에 필요한 것'`, `have '이미 갖춘 것'`, `need '보완할 것'`, `profileNotice '프로필 정보가 더 상세히 있으면 정확한 분석이 가능해요.'`, `profileMissing '이 공고를 판단하는 데 필요한 정보'`, `editProfile '프로필 고치기'`(→ `/settings/profiles`). `profile.descriptionPlaceholder '주력 분야와 기술, 인력 규모와 주요 자격(PM·정보처리기사 등), 최근 3년 유사 사업 실적, 보유 인증·면허, 하지 않는 일을 적어 주세요.'`, `profile.descriptionHint '자세히 적을수록 공고 분석의 적합도 판단이 정확해져요(200자 이상 권장).'`

- [ ] **Step 1: 실패 테스트** — 새 결과: 제목 순서 `[사업 이해, 우리 팀 적합도, 우리 팀에 필요한 것, 리스크·유의사항, 다음 할 일]`, `핵심 요구사항` 없음; `profile_brief: true` 또는 profile_missing 있으면 안내 문구·목록·링크, 둘 다 없으면 안내 없음; 예전 결과(`?analysis=`로 v9 모양) → `copy.analysis.requirements` 보임; 프로필 화면에 hint.
- [ ] **Step 2:** FAIL. **Step 3:** 구현(안내는 '우리 팀에 필요한 것' 위, `bg-warning-bg` 대신 `bg-primary-soft` 안내 톤). **Step 4:** 게이트. **Step 5:** 커밋.

### Task 7: B 마무리 — 실모델 확인·명세·기록
- [ ] 개발 서버 재기동, 실제 vLLM으로 g004(적합)·g012(부적합) 분석: 짧은 프로필(37자)·긴 프로필(200자+) 각각 → brief·안내·have/need 개수·금액 미포함 확인, 스크린샷.
- [ ] 골든셋 `run --only g001 g004 g012 g017`로 fit_score·원문 대조 100%·스키마 실패 0 확인(전체 재평가는 사용자에게 제안).
- [ ] 명세 §7.5-5·§8.4·§8.5 수정·export·복원. `docs/decisions/2026-11-16-analysis-restructure.md`(측정 결과), PROGRESS. 커밋·push.

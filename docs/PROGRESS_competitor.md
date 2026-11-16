# 진행 기록 — 경쟁사 분석 (SPEC §15, P8~P11)

단계마다 '한 일 / 달라진 결정 / 남은 문제'를 3~5줄로 남긴다 (SPEC §13).

## P8-a — 낙찰·계약 API 확인 (2026-11-16, 완료)

- **한 일**: §15 장을 SPEC.md에 넣고(문서만), `backend/scripts/probe_awards.py`로 §15.10의 8가지를 실제 응답으로 확인(G2B 40회). 녹화본 `tests/fixtures/g2b/awards_*.json`·`opening_compt_page1.json`·`contracts_page1.json`(개인정보 칸 제거).
- **달라진 결정**: 조회 창은 7일 '미만'(정확히 7일이면 07 오류), `numOfRows=1000`은 조용히 10행. 낙찰 고유키는 분류·재입찰까지 `(공고번호, 차수, 분류, 재입찰)`. 공동수급은 낙찰 응답에 주계약업체 1행뿐 → 계약정보 `corpList` 방식 칸으로만 판정(`cmmnCntrctYn` 불신). 협상계약은 낙찰률(G2B)이 대부분 빔. 기존 키로 호출됨. 5년 백필 약 522회 (`docs/decisions/2026-11-16-awards-probe.md`).
- **남은 문제**: SPEC §15.2·§15.3·§15.4 수정 제안(결정 문서 '명세 수정 필요').

## P8-b — 낙찰 테이블·수집기 (2026-11-16, 완료·태그 전)

- **한 일**: 마이그레이션 0008(`companies`·`bid_awards`·`bid_participants`·`bid_joint_members`·`org_settings`·`watched_companies`, 개인정보·raw 없음), `ENDPOINTS`에 awards·opening_compt·contracts, 키 `NARA_AWARD_API_KEY`→`NARA_API_KEY`, 낙찰 몫 예산 `G2B_AWARDS_DAILY_BUDGET`(usage_logs `cache.source`로 집계), `app/awards/`(화이트리스트 매퍼·분야 분류·upsert·수집기), CLI `--source awards`, `scripts/reclassify_awards.py`, systemd `nara-collector-awards.timer`(매일 04:30 증분→백필). 테스트 먼저 → pytest 520 통과. 실제 30일 수집 7,098행·9회, 14일 재수집 갱신 0·새 행 5·5회.
- **달라진 결정**: 조회 기간은 분이 아니라 **KST 날짜 7개**(첫 실제 수집의 07 오류로 발견, 3회로 확인) → 창을 KST 자정에 맞춤. 일부 페이지만 받은 창은 `G2BIncomplete`로 실패. `/readyz` 마지막 수집은 공고 소스만 (`docs/decisions/2026-11-16-awards-probe.md`).
- **남은 문제**: 운영 서버에서 `nara-collector-awards.timer` 활성화(`docs/ops/RUNBOOK.md`). 5년 백필은 아직 시작 안 함(timer가 하루 300회씩, 약 2일). SPEC §15.2~§15.4 수정 제안. 다음은 P9(회사 설정·우리 수주 현황·업체 검색).

## P9 — 회사 설정 · 우리 수주 현황 · 업체 검색 (2026-11-16, 완료·태그 전)

- **한 일**: API 7개(§15.6)와 조회 서비스 `app/awards/service.py`(기간을 수집 완료 범위로 자름, 요약·연도별·수요기관별·분야·커서 목록·업체 검색), 마이그레이션 0009(`company_search` 사용 기록), 화면 `/admin/company`(사업자번호 → 이름 찾기, 분야 키워드, 수집 기간, 연도별 진행률·오늘 호출량)·`/my-awards`·`/companies`(URL 동기화), 사이드바 '우리 수주 현황'·'업체 검색', 관리자 하위 메뉴 '회사 설정'. 테스트 → pytest 532·vitest 196·Playwright 3 통과. 캡처 `frontend/test-results/p9-*.png`.
- **달라진 결정**: 기간 축은 등록일시, 수집 안 된 해는 0이 아니라 '수집 중', `/company` → `/admin/company`, 검색 기록은 검색어 없이 방식·결과 수만 (`docs/decisions/2026-11-16-p9-company-awards.md`).
- **남은 문제**: 개발 DB에 우리 회사는 아직 미설정(관리자가 화면에서). '비교'·'관심 경쟁사' 버튼은 P10. SPEC §15.6·§15.7 수정 제안.

## P10 — 비교 · 강점/약점 · 경쟁사 레이더 (2026-11-16, 완료·태그 전)

- **한 일**: §15.5 판정 순수 함수(`app/analysis/competitors.py`, LLM 없음), 비교·레이더(겹침도 SQL)·관심 경쟁사 API 5개, 화면 `/competitors`·`/competitors/:bizno`(맨 위 강점·약점 카드와 항목별 판정 표, 한눈에 보기, 연도별, 수요기관 겹침, 주력 분야, 경쟁사 최근 낙찰, 공동수급·AI 해설 자리), 업체 검색의 비교·관심 버튼, 사이드바 '경쟁사'. 테스트 → 경계값 30개, 같은 입력 같은 출력, 판정 숫자 = `GET /awards` 합산, 우리 회사 변경 반영, pytest 568·vitest 200·Playwright 3 통과. 캡처 `frontend/test-results/p10-*.png`.
- **달라진 결정**: 판정 값 `up·same·down·info`+표본 적음, 맞대결은 개찰 결과를 불러온 공고만(P11 전에는 '참고'), 관심 목록은 `GET /competitors/watch` (`docs/decisions/2026-11-16-p10-compare-radar.md`).
- **남은 문제**: P11(공고별 경쟁 구도·AI 해설·어시스턴트 도구·공동수급). SPEC §15.5·§15.6 수정 제안. 겹침도 가중치·기준은 실제 5년 데이터를 본 뒤 조정(§15.5 결정).

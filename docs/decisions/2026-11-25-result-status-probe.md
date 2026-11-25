# 개찰·낙찰 결과 표시와 반영 지연 (결과 메일 사전 확인)
- 명세 위치: 설계 `docs/superpowers/specs/2026-11-25-bid-result-mail-design.md` [미확인] 항목, 계획 Task 1
- 방법: `backend/scripts/probe_results.py`(호출 19회, 2026-11-25 10:53 KST). 어제 0시~지금 개찰일시(inqryDiv=3) 용역
  `getOpengResultListInfoServc` 775행 + 상태별 표본 2건씩 낙찰(inqryDiv=4)·개찰완료 목록·공고 단건
- 결과:
  - `progrsDivCdNm` 값: 개찰완료 416 · 유찰 332 · 재입찰 25 · 재시담 2. 행에 `inptDt`(입력 시각)·`rbidNo`·`bidClsfcNo` 있음
  - 개찰(`opengDt`)→입력(`inptDt`) 지연: p50 22분 · p90 4.3시간 · p99·최대 약 24시간(유찰 p50 13분, 개찰완료 30분).
    방금(10:46~10:53) 개찰분이 10:53에 이미 보임 → Open API 반영은 입력 즉시
  - 낙찰 `getScsbidListSttusServc` inqryDiv=4 + `bidNtceNo` 단건 조회 동작(code 00). 개찰완료 표본 2건 중 1건은 낙찰 행 있음
    (개찰 당일 15:55 등록), 1건은 아직 없음. 유찰·재입찰·재시담 표본은 낙찰 0행·개찰완료 목록 0행
  - 재공고: 원공고에 재공고 표시는 없다. 재공고는 **새 공고번호**로 올라오고 그 공고의 `reNtceYn=Y`·`ntceKindNm=재공고`.
    원공고 번호를 가리키는 필드는 공고 응답에 없음 → 원공고와 재공고를 잇는 직접 연결은 없다
  - 루트 `.env`의 `NARA_API_KEY`는 data.go.kr '인코딩' 키(100자). 그대로 쓰면 '등록되지 않은 서비스키' → 디코딩 필요
- 추가 확인(Task 3): `getOpengResultListInfoServc` inqryDiv=4 + bidNtceNo 단건도 동작(행마다 차수·분류·재입찰·상태·inptDt)
- 결정(판별 규칙, Task 3·5): 개찰결과 1회 조회(`opening_status`)로 상태를 본다. 개찰완료 → 개찰완료 목록 받아 ①,
  낙찰 행 → ② 낙찰. 유찰 → ② 유찰. 재입찰·재시담 → 최종 아님(같은 공고에서 다시 개찰, 계속 감시)
- 미결(사용자): 재공고 알림 방법 — 원공고와 직접 연결이 없음
- 명세 수정 필요: 설계의 final_kind `rebid` 뜻을 사용자 결정에 맞춰 고침

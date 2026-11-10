# G2B 마감 날짜 파싱: YYYYMMDD 오판 버그와 형식 목록
- 명세 위치: §4 공통 규칙(마감 미정), §5.2(날짜 형식), `docs/g2b/API.md`
- 질문: v1 `is_bid_open`을 옮기면서 4가지 날짜 형식이 모두 맞게 해석되는가
- 방법: `backend/tests/unit/test_g2b_parse.py::test_is_bid_open_accepts_all_g2b_formats`
- 결과: v1 순서(`%Y%m%d%H%M` 먼저)에서는 strptime이 `"20261116"`을 2026-01-01 01:06으로 읽는다. 진행중 공고가 '마감'으로 판정되는 버그
- 결정: `%Y%m%d`를 먼저 시도(12자리 값에는 실패하므로 안전). 빈 값·해석 불가는 §4대로 진행중(True)
- 명세 수정 필요: 있음 — §5.2(270행)는 날짜 형식을 2종으로 적었지만 API.md와 v1 코드는 4종(`YYYYMMDDHHMM`, `YYYY-MM-DD HH:MM:SS`, `YYYY-MM-DD HH:MM`, `YYYYMMDD`). P1 `BidRecord` 파서는 4종을 받아야 함

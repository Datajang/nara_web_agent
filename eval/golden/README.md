# 골든셋 (SPEC §12.4) — 라벨링 안내

`items/gNNN.json`은 `eval/run_eval.py candidates`가 개발 DB에서 뽑은 **초안**입니다(`verified: false`).
운영자가 아래를 확인·수정한 뒤 `verified: true`로 바꿉니다. 원문은 `run` 실행 후 `texts/gNNN.txt`에
생깁니다(담당자 연락처가 있을 수 있어 커밋하지 않음).

| 필드 | 할 일 |
|---|---|
| `fit` | 합성 프로필 A(AI 플랫폼 개발팀, `run_eval.py`의 `PROFILES`) 기준 `high`·`mid`·`low`. 초안은 제목 정규식이라 틀린 것이 많음 |
| `expect.budget_won` | 원문의 사업 예산(원, 부가세 포함 여부는 원문대로). 없으면 `null` |
| `expect.deadline` | 입찰(제안서) 마감일 `YYYY-MM-DD`. 사전규격은 의견 마감일 |
| `expect.method` | 원문 표기의 계약·평가 방식(예: 협상에 의한 계약). 초안은 G2B `cntrctCnclsMthdNm` |
| `expect.qualifications` | 참가 자격 핵심 2~4개 |
| `tags` | `long`(40K 토큰 초과)·`table`·`multi_file`·`scanned` 등 해당 항목 추가 |

- 분포 목표: 적합 20·경계 15·부적합 15(50건). 첫 20건으로 스크립트를 검증하고 나머지는 운영 데이터로 보충.
- 요약 품질(5점 척도)은 `eval/results/<날짜>_eval_<label>.json`의 `headline`과 DB 요약을 보고 따로 채점.
- 며칠 뒤 같은 항목 10건을 다시 라벨링해 일관성을 확인합니다.

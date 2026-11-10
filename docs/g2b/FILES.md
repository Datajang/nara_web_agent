# 첨부파일 텍스트 추출 사실 모음

출처: `narajangteo_mcp_server`의 CLAUDE.md 정리본. 다운로드 허용 호스트·크기 제한·저장 규칙은 `docs/SPEC.md` §5.6이 우선한다.

## 추출 흐름

`extract_text_from_url(url, filename)` → `extract_text_from_bytes()`(형식별 분배) → 형식별 추출기.
지원 형식: HWP, HWPX, PDF, DOCX, XLSX.

## HWP는 2단계 대체 경로

1. `langchain-teddynote`의 `HWPLoader` (기본. zlib 압축 HWP 처리)
2. `olefile`로 직접 파싱 (`PrvText` 스트림, 안 되면 `BodyText/Section*`)

라이브러리 import는 모두 try/except와 `HAS_*` 플래그로 감싸 둔다. 없는 라이브러리 때문에 서버가 죽지 않고 해당 형식만 못 읽는 상태가 되게 한다.

## ZIP 안에서 파일 고르기

한 개만 고른다. 우선순위는 파일명에 `제안요청서`·`과업지시서`가 들어간 것 > `.hwp`/`.hwpx` > `.docx`/`.pdf`.

## v2에서 주의할 점

- 추출 결과는 `file_texts`(공유 계층)에 저장하고 같은 파일은 다시 추출하지 않는다(SPEC §4, §5.6).
- 추출 실패는 예외로 끝내지 말고 "추출 실패" 상태와 이유를 남긴다. 라이브러리 부재와 파일 손상을 구분해서 기록한다 [가정].

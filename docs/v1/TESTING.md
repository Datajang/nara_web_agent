# v1 테스트 패턴과 v2 차이

출처: v1 CLAUDE.md. 테스트를 새로 쓸 때 읽는다. v2 테스트 계층·평가 기준은 `docs/SPEC.md` §12가 기준이다.

## 그대로 가져올 패턴

- 앱이 필요한 테스트 파일마다 자체 `client` fixture를 둔다.
- fixture가 하는 일: DB 준비와 스키마 생성 → `get_db` 의존성 override → 외부 호출(vLLM, G2B) 목킹.
- `pyproject.toml`에 `asyncio_mode = "auto"`를 둔다. async 테스트에 `@pytest.mark.asyncio`가 필요 없다.
- 테스트는 외부 서비스 없이 돌아가야 한다.

## v2에서 바뀌는 것

| 항목 | v1 | v2 |
|---|---|---|
| 테스트 DB | 인메모리 SQLite | PostgreSQL (SPEC §12.1). SQLite로 테스트하지 않는다 |
| G2B 응답 | 필요한 곳에서 목킹 | 녹화한 JSON 픽스처 `tests/fixtures/g2b` (서비스키는 마스킹) |
| LLM | 목킹 | fake LLM 인터페이스 + 골든셋 평가는 별도 (SPEC §12) |
| 메일 | 해당 없음 | `MAIL_BACKEND=memory` |

## v1 명령 (참고)

```bash
uv run pytest
uv run pytest tests/test_auth.py -v
uv run pytest tests/test_auth.py::test_register -v
```

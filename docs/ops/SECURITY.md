# §9.5 보안 체크리스트 점검 (P4a, 2026-11-11)

저장소에서 확인할 수 있는 것은 테스트·검색으로 확인했다. 서버에서만 확인되는 것은 "서버" 열에 둔다.

| 항목 | 결과 | 근거 | 서버에서 할 확인 |
|---|---|---|---|
| 비밀키 | ✅ | `ENV=production`에서 기본값·32바이트 미만이면 시작 거부 (`test_config_startup.py`), `nara.env.example`은 빈 값 | `SECRET_KEY`를 `openssl rand -hex 32`로 새로 생성 |
| 토큰 저장 | ✅ | httpOnly·Secure·SameSite=Lax 쿠키(`api/security.py`), 프런트 `localStorage`·`sessionStorage` 사용 0건 | — |
| XSS | ✅ | ESLint `vue/no-v-html`(MarkdownView만 예외), DOMPurify, 카드 제목 XSS 테스트(vitest·e2e) | — |
| 보안 헤더 | ✅ | `deploy/nginx/snippets/nara-security.conf`, 모든 location include를 테스트로 고정 | `curl -sI https://<접속 주소>/` 로 5개 헤더 확인 |
| CSP 호환 | ✅ | 빌드 `index.html`에 인라인 스크립트 0개. 인라인 style 속성은 `'unsafe-inline'`로 허용 | 브라우저 콘솔에 CSP 위반 없음 |
| SQL | ✅ | 앱 코드에 f-string·format으로 만든 SQL 0건(바인드 파라미터만) | — |
| SSRF·파일 | ✅ | 허용 호스트·크기·시간 제한, 별도 프로세스 추출 (`test_files.py`) | — |
| 속도 제한 | ✅ | §6.1 표 (`test_rate_limit_api.py`). nginx 뒤 IP는 XFF 마지막 값(127.0.0.1에서만) | — |
| 비밀 관리 | ✅ | `.env`·`backend/.env` git 제외, 운영 `/etc/nara/*.env`는 root:nara 0640 | `ls -l /etc/nara` |
| 로그 | ✅ | 서비스키·비밀번호·토큰·JWT 마스킹, JSON 로그에 쿼리스트링·이메일·본문 없음(테스트), e2e 로그 실측 0건 | `journalctl -u nara-api | grep -ci servicekey=` 가 0 |
| 의존성 | ✅ | CI `audit` 잡(실패 시 병합 불가) + Dependabot. npm 운영 0건. pip-audit는 수용 목록 11개(langchain 계열, HWPLoader 때문에 올릴 수 없고 미사용 기능) 외 0건 — `backend/security/pip-audit-accepted.txt`, `test_hwp_dependency_guard.py` | — |
| LLM 데이터 | ✅ | 자체 vLLM만(`LLM_BASE_URL`=127.0.0.1:8011), 외부 LLM 경로 없음 | — |
| 백업 | ✅ | `pg_dump -Fc | age -R 공개키`, 파일 0600, 개인키는 서버 밖 (`test_deploy_scripts.py`) | 복원 리허설 1회(RUNBOOK) |
| 네트워크 | 서버 | API·vLLM·PG16은 127.0.0.1만 바인드(유닛·설정 테스트). 외부 공개는 nginx 80·443뿐이고, 가입은 관리자 승인 필수(허용 도메인 미설정) | GCP 방화벽 80·443만(INSTALL §6), SSH는 IAP. **시스템 PG13이 0.0.0.0:5432에 열려 있음** — v2와 무관하지만 점검 권장 |
| 시크릿 스캔 | ◐ | `.pre-commit-config.yaml`(gitleaks) 추가. 각자 `uvx pre-commit install` 필요 | — |

# 배포·롤백 (SPEC §11.6)

**운영자가 직접 실행한다.** 자동 배포(GitHub Actions)는 미룬다(사용자 결정): 수동 `deploy.sh`로 충분하고,
자동화에는 Workload Identity Federation + IAP 설정이 필요하다.

## 릴리스
1. 개발 PC: CI(§12.8) 초록 확인 → `git tag -a v2.x.y -m ...` → `git push origin v2.x.y` (push는 운영자)
2. 서버:
```bash
sudo /opt/nara/app/deploy/deploy.sh v2.x.y
sudo NARA_RESTART_VLLM=1 /opt/nara/app/deploy/deploy.sh v2.x.y   # 모델·플래그가 바뀐 릴리스만
```

`deploy.sh` 순서: 태그 확인(없으면 아무것도 안 바꾸고 종료) → 지금 태그를 `/opt/nara/.prev`에 기록 →
체크아웃 → `uv sync --locked --no-dev` → `npm ci && npm run build` → 새 릴리스 디렉터리로 `dist` 링크 교체
(최근 5개 보관) → `alembic upgrade head` → 유닛 복사·`daemon-reload` → `nara-api` 재시작 →
`/healthz` 30회(1초) 확인. 실패하면 `.prev` 태그로 **자동 롤백**(한 번만, `.prev`는 그대로).

## 수동 롤백
```bash
sudo /opt/nara/app/deploy/deploy.sh "$(cat /opt/nara/.prev)"
```
DB는 되돌리지 않는다. 마이그레이션은 이전 코드와 호환되게 쓴다(§11.5: 컬럼 추가 → 다음 릴리스에서 정리).

## 배포 후 확인
```bash
curl -fsS http://127.0.0.1:8010/healthz && curl -s http://127.0.0.1:8010/readyz
journalctl -u nara-api -n 50 --no-pager
systemctl list-timers 'nara-*'
```
`/readyz`: `db`가 `ok`가 아니면 503. `llm`·`collector`(`ok`/`stale`/`never`)는 본문으로만 알린다.

## 저장소 안에서의 시험
`backend/tests/deploy/`가 유닛·nginx·환경 예시를 검사하고, 스크립트를 가짜 명령으로 실제 실행한다
(순서, 롤백, 백업 보관 개수, 운영 DB 복원 거부). 서버 명령은 실행하지 않는다.

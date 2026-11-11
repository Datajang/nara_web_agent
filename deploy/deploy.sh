#!/usr/bin/env bash
# 릴리스 태그 배포 (SPEC §11.6). 운영 서버에서 root로: sudo /opt/nara/app/deploy/deploy.sh v2.0.0
#
# 1. 태그 체크아웃, 직전 태그를 /opt/nara/.prev에 기록
# 2. 백엔드 의존성 (uv sync --locked, 락 파일 기준)
# 3. 프런트 빌드 → 새 릴리스 디렉터리 → dist 심볼릭 링크를 원자적으로 교체
# 4. alembic upgrade head
# 5. systemd 유닛 복사 → daemon-reload → nara-api 재시작 (vLLM은 NARA_RESTART_VLLM=1일 때만)
# 6. /healthz를 30회(1초 간격) 확인. 실패하면 .prev 태그로 자동 롤백(롤백은 한 번만)
#
# 마이그레이션은 이전 코드와 호환되게 쓰므로(§11.5) 롤백 때 DB는 되돌리지 않는다.
set -euo pipefail

TAG=${1:?"사용법: deploy.sh <git-tag>"}
NARA_ROOT=${NARA_ROOT:-/opt/nara}
APP=$NARA_ROOT/app
VENV=$NARA_ROOT/venv
RELEASES=$NARA_ROOT/frontend/releases
DIST=$NARA_ROOT/frontend/dist
ENV_FILE=${NARA_ENV_FILE_PATH:-/etc/nara/nara.env}
SYSTEMD_DIR=${NARA_SYSTEMD_DIR:-/etc/systemd/system}
HEALTH_URL=${NARA_HEALTH_URL:-http://127.0.0.1:8010/healthz}
HEALTH_TRIES=${NARA_HEALTH_TRIES:-30}
ROLLBACK=${NARA_ROLLBACK:-0}
KEEP_RELEASES=${NARA_KEEP_RELEASES:-5}

log() { echo "[deploy] $*" >&2; }
as_nara() { runuser -u nara -- "$@"; }

cd "$APP"
as_nara git fetch --tags --quiet
if ! as_nara git rev-parse -q --verify "refs/tags/$TAG" >/dev/null; then
  log "태그가 없습니다: $TAG"
  exit 2
fi
prev=$(as_nara git describe --tags --exact-match 2>/dev/null || true)
if [[ $ROLLBACK != 1 ]]; then
  [[ -n $prev ]] || { log "지금 체크아웃이 태그가 아니라 롤백 지점을 정할 수 없습니다"; exit 2; }
  echo "$prev" >"$NARA_ROOT/.prev"
fi
log "배포 $prev → $TAG"
as_nara git checkout --quiet --detach "refs/tags/$TAG"

# 2. 백엔드
(cd backend && UV_PROJECT_ENVIRONMENT=$VENV as_nara uv sync --locked --no-dev)

# 3. 프런트 (새 디렉터리에 만들고 링크만 바꾼다)
(cd frontend && as_nara npm ci --no-audit --no-fund && as_nara npm run build)
release="$RELEASES/$TAG-$(date +%Y%m%d%H%M%S)"
mkdir -p "$release"
cp -a frontend/dist/. "$release/"
ln -sfn "$release" "$DIST.next"
mv -Tf "$DIST.next" "$DIST"
# 오래된 릴리스 정리 (지금 것 포함 최근 KEEP_RELEASES개 유지)
ls -1dt "$RELEASES"/*/ 2>/dev/null | tail -n +$((KEEP_RELEASES + 1)) | xargs -r rm -rf

# 4. 마이그레이션 (DATABASE_URL은 환경 파일에서 앱 설정으로 읽는다: 인자에 비밀값 없음)
(cd backend && NARA_ENV_FILE=$ENV_FILE as_nara "$VENV/bin/alembic" upgrade head)

# 5. 유닛 반영과 재시작
install -m 0644 deploy/systemd/* "$SYSTEMD_DIR/"
systemctl daemon-reload
systemctl restart nara-api
[[ ${NARA_RESTART_VLLM:-0} == 1 ]] && systemctl restart nara-vllm

# 6. 헬스체크와 자동 롤백
for _ in $(seq "$HEALTH_TRIES"); do
  if curl -fsS -o /dev/null "$HEALTH_URL"; then
    log "완료: $TAG (/healthz 정상)"
    exit 0
  fi
  sleep 1
done
if [[ $ROLLBACK == 1 ]]; then
  log "롤백한 $TAG도 /healthz에 실패했습니다. 수동 조치: docs/ops/RUNBOOK.md"
  exit 1
fi
back=$(cat "$NARA_ROOT/.prev")
log "/healthz 실패 → $back(으)로 롤백합니다"
NARA_ROLLBACK=1 "$0" "$back" || { log "롤백 실패"; exit 1; }
log "$back(으)로 롤백했습니다. $TAG는 배포되지 않았습니다"
exit 1

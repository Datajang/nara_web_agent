#!/usr/bin/env bash
# 서버 이전 1단계 (docs/ops/MIGRATE.md): 옛 서버에서 git에 없는 것을 한 파일로 묶어 암호화한다. root로:
#
#   sudo /opt/nara/app/deploy/migrate/export.sh [개발 저장소 경로]
#   예) sudo /opt/nara/app/deploy/migrate/export.sh /home/searching-doc-rag/AX_Team_Nara_bot
#
# 담는 것: 운영 DB(pg_dump), /etc/nara(비밀값·백업 공개키).
# 개발 저장소를 주면 그 저장소의 git 제외 파일(.env, *.local.md, 골든셋 원문, 커밋 안 한 문서),
# 개발 DB, 저장소 주인의 Claude 메모리·개발 cron 스크립트도 담는다.
# 백업 공개키(/etc/nara/backup.pub)로 암호화한다 → 푸는 데는 운영자 PC의 백업 개인키가 필요하다.
# 결과: <저장소 주인 홈 또는 /root>/nara-migrate-YYYY-MM-DD.tar.age (+ .sha256)
set -euo pipefail
umask 077

REPO=${1:-}
ETC=${NARA_ETC_DIR:-/etc/nara}
PUBKEY=${NARA_MIGRATE_PUBKEY:-$ETC/backup.pub}
PG_BIN=${PG_BIN:-/usr/lib/postgresql/16/bin}
DAY=$(TZ=Asia/Seoul date +%F)

log() { echo "[export] $*" >&2; }

# DATABASE_URL → PG* 환경변수 (비밀번호는 명령 인자에 남기지 않는다)
pg_env_from() { # $1 = env 파일
  local url re
  url=$(sed -n 's/^DATABASE_URL=//p' "$1" | tail -n 1)
  re='^postgresql(\+[a-z0-9]+)?://([^:@/]+):([^@/]+)@([^:/]+):([0-9]+)/([^?]+)'
  [[ $url =~ $re ]] || { log "DATABASE_URL 형식을 읽지 못했습니다: $1"; return 2; }
  export PGUSER=${BASH_REMATCH[2]} PGPASSWORD=${BASH_REMATCH[3]}
  export PGHOST=${BASH_REMATCH[4]} PGPORT=${BASH_REMATCH[5]} PGDATABASE=${BASH_REMATCH[6]}
}

[[ -r $PUBKEY ]] || { log "백업 공개키가 없습니다: $PUBKEY"; exit 2; }
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
mkdir "$work/bundle"
B=$work/bundle

# 1. 운영 DB
(pg_env_from "$ETC/nara.env" && "$PG_BIN/pg_dump" -Fc --no-password -f "$B/prod.dump")
log "운영 DB: $(stat -c %s "$B/prod.dump") bytes"

# 2. /etc/nara (nara.env, vllm.env, backup.pub)
tar -C "$(dirname "$ETC")" -cpf "$B/etc-nara.tar" "$(basename "$ETC")"

# 3. 개발 저장소(선택)
owner_home=/root
if [[ -n $REPO ]]; then
  [[ -d $REPO/.git ]] || { log "git 저장소가 아닙니다: $REPO"; exit 2; }
  owner=$(stat -c %U "$REPO")
  owner_home=$(getent passwd "$owner" | cut -d: -f6)
  # git 제외 파일: 커밋 안 한 파일 + 아래 목록(있는 것만). node_modules·.venv 같은 빌드물은 뺀다
  # -z: 한글 파일 이름을 git이 \354…로 바꾸지 않게 그대로 받는다
  mapfile -d '' -t untracked < <(runuser -u "$owner" -- git -C "$REPO" ls-files -z --others --exclude-standard)
  extra=(.env backend/.env eval/golden/texts)
  while IFS= read -r f; do extra+=("$f"); done < <(cd "$REPO" && find . -name '*.local.md' -not -path './node_modules/*' -not -path '*/node_modules/*' | sed 's#^\./##')
  files=()
  for f in "${untracked[@]}" "${extra[@]}"; do [[ -e $REPO/$f ]] && files+=("$f"); done
  if ((${#files[@]})); then
    tar -C "$REPO" -cpf "$B/repo-local.tar" "${files[@]}"
    printf '%s\n' "${files[@]}" > "$B/repo-local.list"
  fi
  # 개발 DB (backend/.env의 DATABASE_URL, 보통 Docker 127.0.0.1:5433)
  if [[ -r $REPO/backend/.env ]] && (pg_env_from "$REPO/backend/.env" && "$PG_BIN/pg_dump" -Fc --no-password -f "$B/dev.dump") 2>/dev/null; then
    log "개발 DB: $(stat -c %s "$B/dev.dump") bytes"
  else
    log "개발 DB는 건너뜀(접속 안 됨)"
    rm -f "$B/dev.dump"
  fi
  # Claude 메모리(이 저장소용)와 개발 cron 스크립트
  mem=".claude/projects/$(echo "$REPO" | sed 's#[/_]#-#g')/memory"
  home_files=()
  for f in "$mem" nara-dev/collect_awards.sh; do [[ -e $owner_home/$f ]] && home_files+=("$f"); done
  if ((${#home_files[@]})); then tar -C "$owner_home" -cpf "$B/home.tar" "${home_files[@]}"; fi
  runuser -u "$owner" -- crontab -l > "$B/crontab.txt" 2>/dev/null || true
fi

{
  echo "created_kst: $(TZ=Asia/Seoul date '+%F %T')"
  echo "source_host: $(hostname)"
  echo "repo: ${REPO:-없음}"
  (cd "$B" && ls -1)
} > "$B/MANIFEST.txt"

out="$owner_home/nara-migrate-$DAY.tar.age"
tar -C "$work" -cf - bundle | age -R "$PUBKEY" -o "$out"
(cd "$(dirname "$out")" && sha256sum "$(basename "$out")" > "$(basename "$out").sha256")
if [[ -n $REPO ]]; then chown "$owner:" "$out" "$out.sha256"; fi
chmod 0600 "$out"
log "완료: $out ($(stat -c %s "$out") bytes) — 내려받아 보관하고, 새 서버에서 import.sh로 푼다"
cat "$B/MANIFEST.txt" >&2

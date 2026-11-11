#!/usr/bin/env bash
# DB 백업 (SPEC §11.5). nara-backup.timer가 매일 03:30 KST에 nara 사용자로 실행한다.
#
# pg_dump -Fc | age -R <공개키> → /var/backups/nara/nara-YYYY-MM-DD.dump.age (0600)
# 일요일 것은 weekly/에도 둔다. 최근 14일치와 주간 4개만 남긴다.
# BACKUP_GCS_URI가 있으면 같은 파일을 GCS에 복사한다 [가정].
# 비밀번호는 PGPASSWORD 환경변수로만 넘긴다(명령 인자에 남지 않게).
set -euo pipefail
umask 077

ENV_FILE=${NARA_ENV_FILE_PATH:-/etc/nara/nara.env}
OUT=${NARA_BACKUP_DIR:-/var/backups/nara}
PUBKEY=${NARA_BACKUP_PUBKEY:-/etc/nara/backup.pub}
PG_BIN=${PG_BIN:-/usr/lib/postgresql/16/bin}
KEEP_DAILY=${KEEP_DAILY:-14}
KEEP_WEEKLY=${KEEP_WEEKLY:-4}
TODAY=${NARA_BACKUP_DATE:-$(TZ=Asia/Seoul date +%F)}
GCS=${BACKUP_GCS_URI:-}

log() { echo "[backup] $*" >&2; }

url=$(sed -n 's/^DATABASE_URL=//p' "$ENV_FILE" | tail -n 1)
re='^postgresql(\+[a-z0-9]+)?://([^:@/]+):([^@/]+)@([^:/]+):([0-9]+)/([^?]+)'
if [[ ! $url =~ $re ]]; then
  log "DATABASE_URL 형식을 읽지 못했습니다(user:password@host:port/db 필요)"
  exit 2
fi
export PGUSER=${BASH_REMATCH[2]} PGPASSWORD=${BASH_REMATCH[3]}
export PGHOST=${BASH_REMATCH[4]} PGPORT=${BASH_REMATCH[5]} PGDATABASE=${BASH_REMATCH[6]}

mkdir -p "$OUT/weekly"
name="nara-$TODAY.dump.age"
part="$OUT/.$name.part"
trap 'rm -f "$part"' EXIT
"$PG_BIN/pg_dump" -Fc --no-password | age -R "$PUBKEY" -o "$part"
mv -f "$part" "$OUT/$name"
chmod 0600 "$OUT/$name"
log "저장: $OUT/$name ($(stat -c %s "$OUT/$name") bytes)"

if [[ $(date -d "$TODAY" +%u) == 7 ]]; then
  cp -p "$OUT/$name" "$OUT/weekly/$name"
fi

prune() { # $1 디렉터리, $2 남길 개수 (파일 이름의 날짜순)
  find "$1" -maxdepth 1 -name 'nara-*.dump.age' -printf '%f\n' | sort -r |
    tail -n +$(($2 + 1)) | while read -r f; do rm -f -- "$1/$f"; done
}
prune "$OUT" "$KEEP_DAILY"
prune "$OUT/weekly" "$KEEP_WEEKLY"

if [[ -n $GCS ]]; then
  gcloud storage cp --quiet "$OUT/$name" "$GCS/$name"
  log "GCS 복사: $GCS/$name"
fi

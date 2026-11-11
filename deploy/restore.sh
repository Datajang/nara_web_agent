#!/usr/bin/env bash
# 백업 복원 (SPEC §11.5, §11.8). 복원 연습은 새 DB에 풀고 버전·행 수를 확인한다. root로 실행:
#
#   sudo NARA_AGE_IDENTITY=/root/nara-backup-key.txt \
#     /opt/nara/app/deploy/restore.sh /var/backups/nara/nara-2026-11-11.dump.age nara_restore_test
#
# 운영 DB(nara) 이름으로는 복원하지 않는다. 실제 장애 복구는 docs/ops/RUNBOOK.md 순서를 따른다
# (서비스 중지 → 새 DB에 복원·확인 → nara.env의 DB 이름 변경 → 서비스 시작).
set -euo pipefail

FILE=${1:?"사용법: restore.sh <백업.dump.age> <새 DB 이름>"}
TARGET=${2:?"사용법: restore.sh <백업.dump.age> <새 DB 이름>"}
IDENTITY=${NARA_AGE_IDENTITY:-}
PG_BIN=${PG_BIN:-/usr/lib/postgresql/16/bin}
export PGPORT=${PGPORT:-5434}
LIVE_DB=${NARA_LIVE_DB:-nara}
OWNER=${NARA_DB_OWNER:-nara}

log() { echo "[restore] $*" >&2; }
as_pg() { runuser -u postgres -- "$@"; }

if [[ $TARGET == "$LIVE_DB" ]]; then
  log "운영 DB($LIVE_DB)에는 복원하지 않습니다. 새 이름(예: nara_restore_test)을 주세요"
  exit 2
fi
if [[ -z $IDENTITY ]]; then
  log "NARA_AGE_IDENTITY(개인키 파일 경로)가 필요합니다. 개인키는 서버 밖에 보관합니다"
  exit 2
fi
[[ -r $FILE ]] || { log "백업 파일을 읽을 수 없습니다: $FILE"; exit 2; }

started=$(date +%s)
as_pg "$PG_BIN/createdb" -O "$OWNER" "$TARGET"
age -d -i "$IDENTITY" "$FILE" | as_pg "$PG_BIN/pg_restore" --no-owner --role="$OWNER" -d "$TARGET"

q() { as_pg "$PG_BIN/psql" -X -A -t -d "$TARGET" -c "$1"; }
echo "restore_file: $(basename "$FILE")"
echo "target_db: $TARGET"
echo "alembic_version: $(q 'SELECT version_num FROM alembic_version')"
for table in bids bid_files bid_summaries analyses users profiles feedback collector_runs; do
  echo "$table: $(q "SELECT count(*) FROM $table")"
done
echo "elapsed_s: $(($(date +%s) - started))"
log "확인 후 삭제: sudo -u postgres $PG_BIN/dropdb -p $PGPORT $TARGET"

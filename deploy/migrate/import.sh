#!/usr/bin/env bash
# 서버 이전 3단계 (docs/ops/MIGRATE.md): 새 서버에서 export.sh 묶음을 푼다. bootstrap.sh 다음에 root로:
#
#   sudo NARA_AGE_IDENTITY=/root/nara-backup-key.txt \
#     /opt/nara/app/deploy/migrate/import.sh /root/nara-migrate-YYYY-MM-DD.tar.age [개발 저장소 경로]
#
# 1. /etc/nara를 옛 서버 것으로(비밀값·서명 키 그대로 → 회원은 다시 로그인하지 않아도 된다).
#    bootstrap이 만든 nara.env는 nara.env.bootstrap으로 남긴다
# 2. DB 역할 nara의 비밀번호를 옮겨 온 nara.env에 맞추고, 운영 DB를 복원한다.
#    대상 DB에 이미 테이블이 있으면 멈춘다(NARA_IMPORT_FORCE=1이면 지우고 복원)
# 3. 개발 저장소를 주면 git 제외 파일·Claude 메모리·cron 스크립트를 제자리에 두고, 개발 DB 복원 명령을 알려 준다
# 개인키는 끝나면 서버에서 지운다(shred -u).
set -euo pipefail
umask 077

FILE=${1:?"사용법: import.sh <nara-migrate-*.tar.age> [개발 저장소 경로]"}
REPO=${2:-}
IDENTITY=${NARA_AGE_IDENTITY:?"NARA_AGE_IDENTITY(백업 개인키 파일 경로)가 필요합니다"}
ETC=${NARA_ETC_DIR:-/etc/nara}
PG_BIN=${PG_BIN:-/usr/lib/postgresql/16/bin}
FORCE=${NARA_IMPORT_FORCE:-0}
DB_OVERRIDE=${NARA_IMPORT_DB:-} # 시험용: 다른 DB 이름에 복원
REPO_ONLY=${NARA_IMPORT_REPO_ONLY:-0} # 1이면 /etc/nara·운영 DB는 건너뛰고 개발 파일만

log() { echo "[import] $*" >&2; }
as_pg() { runuser -u postgres -- "$@"; }

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
age -d -i "$IDENTITY" "$FILE" | tar -C "$work" -xf -
B=$work/bundle
[[ -f $B/MANIFEST.txt ]] || { log "묶음 형식이 아닙니다(MANIFEST 없음)"; exit 2; }
log "묶음: $(head -n 2 "$B/MANIFEST.txt" | tr '\n' ' ')"

# 1. /etc/nara
if [[ $REPO_ONLY == 1 ]]; then
  log "개발 파일만 풉니다(NARA_IMPORT_REPO_ONLY=1)"
else
if [[ -f $ETC/nara.env ]] && ! cmp -s <(tar -xOf "$B/etc-nara.tar" "$(basename "$ETC")/nara.env") "$ETC/nara.env"; then
  cp -p "$ETC/nara.env" "$ETC/nara.env.bootstrap"
fi
tar -C "$(dirname "$ETC")" -xpf "$B/etc-nara.tar"
if getent group nara >/dev/null; then chown -R root:nara "$ETC"; fi
log "/etc/nara 복원"

# 2. DB
url=$(sed -n 's/^DATABASE_URL=//p' "$ETC/nara.env" | tail -n 1)
re='^postgresql(\+[a-z0-9]+)?://([^:@/]+):([^@/]+)@([^:/]+):([0-9]+)/([^?]+)'
[[ $url =~ $re ]] || { log "nara.env의 DATABASE_URL 형식을 읽지 못했습니다"; exit 2; }
user=${BASH_REMATCH[2]} pw=${BASH_REMATCH[3]} port=${BASH_REMATCH[5]} db=${DB_OVERRIDE:-${BASH_REMATCH[6]}}
export PGPORT=$port
[[ $user =~ ^[a-z_][a-z0-9_]*$ && $db =~ ^[a-z_][a-z0-9_]*$ ]] || { log "DB 이름 형식이 이상합니다"; exit 2; }
# 비밀번호는 표준입력으로만 넘긴다(ps에 보이지 않게)
q_pw=${pw//\'/\'\'}
printf "DO \$\$ BEGIN IF EXISTS (SELECT FROM pg_roles WHERE rolname = '%s') THEN ALTER ROLE %s LOGIN PASSWORD '%s'; ELSE CREATE ROLE %s LOGIN PASSWORD '%s'; END IF; END \$\$;\n" \
  "$user" "$user" "$q_pw" "$user" "$q_pw" | as_pg "$PG_BIN/psql" -X -q -v ON_ERROR_STOP=1 -d postgres
exists=$(as_pg "$PG_BIN/psql" -X -A -t -d postgres -c "SELECT 1 FROM pg_database WHERE datname = '$db'")
if [[ $exists == 1 ]]; then
  tables=$(as_pg "$PG_BIN/psql" -X -A -t -d "$db" -c "SELECT count(*) FROM pg_tables WHERE schemaname = 'public'")
  if [[ $tables != 0 && $FORCE != 1 ]]; then
    log "DB $db 에 이미 테이블이 $tables 개 있습니다. 덮어쓰려면 NARA_IMPORT_FORCE=1"
    exit 3
  fi
  as_pg "$PG_BIN/dropdb" "$db"
fi
as_pg "$PG_BIN/createdb" -O "$user" "$db"
as_pg "$PG_BIN/pg_restore" --no-owner --role="$user" -d "$db" < "$B/prod.dump"
q() { as_pg "$PG_BIN/psql" -X -A -t -d "$db" -c "$1"; }
log "운영 DB 복원: $db (alembic $(q 'SELECT version_num FROM alembic_version'))"
for t in users bids bid_awards bid_participants search_runs analyses watched_companies; do
  echo "  $t: $(q "SELECT count(*) FROM $t")" >&2
done
fi

# 3. 개발 저장소(선택)
if [[ -n $REPO ]]; then
  [[ -d $REPO/.git ]] || { log "git 저장소가 아닙니다: $REPO"; exit 2; }
  owner=$(stat -c %U "$REPO")
  home=${NARA_IMPORT_HOME:-$(getent passwd "$owner" | cut -d: -f6)} # 시험용으로 바꿀 수 있다
  if [[ -f $B/repo-local.tar ]]; then
    runuser -u "$owner" -- tar -C "$REPO" -xpf - < "$B/repo-local.tar"
    log "저장소 로컬 파일 $(wc -l < "$B/repo-local.list")개 → $REPO"
  fi
  if [[ -f $B/home.tar ]]; then
    mem_old=$(tar -tf "$B/home.tar" | grep -m1 -o '^\.claude/projects/[^/]*' || true)
    mem_new=".claude/projects/$(echo "$REPO" | sed 's#[/_]#-#g')"
    runuser -u "$owner" -- tar -C "$home" -xpf - < "$B/home.tar"
    if [[ -n $mem_old && $mem_old != "$mem_new" && ! -e $home/$mem_new ]]; then
      runuser -u "$owner" -- mv "$home/$mem_old" "$home/$mem_new" # 저장소 경로가 바뀌어도 메모리를 잇는다
    fi
    log "Claude 메모리·개발 스크립트 → $home"
  fi
  if [[ -s $B/crontab.txt ]]; then
    cp "$B/crontab.txt" "$home/crontab-from-old-server.txt" && chown "$owner:" "$home/crontab-from-old-server.txt"
    log "옛 crontab: $home/crontab-from-old-server.txt (경로 확인 후 'crontab 파일'로 적용)"
  fi
  if [[ -f $B/dev.dump ]]; then
    cp "$B/dev.dump" "$home/nara-dev.dump" && chown "$owner:" "$home/nara-dev.dump"
    log "개발 DB 덤프: $home/nara-dev.dump — 개발 PostgreSQL을 띄운 뒤 MIGRATE.md 6단계 명령으로 복원"
  fi
fi
log "끝. 개인키를 지우세요: shred -u $IDENTITY"

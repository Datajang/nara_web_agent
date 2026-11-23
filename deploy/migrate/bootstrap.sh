#!/usr/bin/env bash
# 서버 이전 2단계 (docs/ops/MIGRATE.md): 빈 새 VM에 운영 실행 환경을 깐다(INSTALL.md §1~§4 자동판). root로:
#
#   curl -fsSL https://raw.githubusercontent.com/Datajang/nara_web_agent/v2/deploy/migrate/bootstrap.sh -o bootstrap.sh
#   sudo bash bootstrap.sh
#
# Debian 12(권장)·11, NVIDIA 드라이버가 깔린 GPU VM(L4 24GB 기준) 가정. 여러 번 돌려도 된다.
# 하는 일: 패키지(PostgreSQL 16·Node 22·nginx·certbot·age·uv), nara 사용자·디렉터리·저장소, PG16 클러스터(5434),
#          vLLM 0.19.1 venv, 모델 Qwen/Qwen3.5-9B 내려받기(19GB, 토큰 불필요)
# 하지 않는 일: 비밀값·DB 내용(import.sh), 배포(deploy.sh), 주소·인증서(set-host.sh), 서비스 켜기
set -euo pipefail

REPO_URL=${NARA_REPO_URL:-https://github.com/Datajang/nara_web_agent.git}
VLLM_VERSION=${NARA_VLLM_VERSION:-0.19.1}
MODEL=${NARA_MODEL:-Qwen/Qwen3.5-9B}
export DEBIAN_FRONTEND=noninteractive

log() { echo "[bootstrap] $*" >&2; }
[[ $(id -u) == 0 ]] || { log "root로 실행하세요(sudo bash bootstrap.sh)"; exit 2; }
. /etc/os-release
[[ $ID == debian ]] || log "Debian이 아닙니다($ID). 명령이 다를 수 있습니다"

if command -v nvidia-smi >/dev/null && nvidia-smi -L >/dev/null 2>&1; then
  log "GPU: $(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader | head -n 1)"
else
  log "경고: NVIDIA 드라이버가 없습니다. vLLM(분석·어시스턴트)이 돌지 않습니다 — MIGRATE.md 2단계 참고"
fi

# 1. 패키지
apt-get update -q
apt-get install -y -q git curl ca-certificates gnupg nginx certbot age postgresql-common
if [[ ! -f /etc/apt/sources.list.d/pgdg.list ]]; then
  yes | /usr/share/postgresql-common/pgdg/apt.postgresql.org.sh >/dev/null
  # 지원이 끝난 배포판(Debian 11)은 PGDG가 아카이브로 옮겨졌다(2026-11)
  if ! apt-get update -q 2>/dev/null || [[ $VERSION_CODENAME == bullseye ]]; then
    sed -i 's#http://apt.postgresql.org/pub/repos/apt/#https://apt-archive.postgresql.org/pub/repos/apt/#' \
      /etc/apt/sources.list.d/pgdg.list
    apt-get update -q
  fi
fi
apt-get install -y -q postgresql-16
if ! command -v node >/dev/null || (($(node -p 'process.versions.node.split(".")[0]') < 22)); then
  curl -fsSL https://deb.nodesource.com/setup_22.x | bash - >/dev/null
  apt-get install -y -q nodejs
fi
command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 sh
systemctl stop nginx || true
rm -f /etc/nginx/sites-enabled/default

# 2. 사용자·디렉터리·저장소 (INSTALL §1)
id nara >/dev/null 2>&1 || useradd --system --home /var/lib/nara --shell /usr/sbin/nologin nara
install -d -o nara -g nara -m 0751 /opt/nara # o+x: nginx가 frontend/dist에 들어간다
install -d -o nara -g nara -m 0750 /var/lib/nara /var/lib/nara/tmp /var/lib/hf-cache
install -d -o nara -g nara -m 0700 /var/backups/nara /var/backups/nara/weekly
install -d -o root -g nara -m 0750 /etc/nara
[[ -d /opt/nara/app/.git ]] || runuser -u nara -- git clone -q "$REPO_URL" /opt/nara/app
runuser -u nara -- git -C /opt/nara/app fetch -q --tags
# 기본 브랜치(main)에는 v2 코드가 없다 → 최신 릴리스 태그로. deploy.sh는 지금 체크아웃이 태그여야 한다
if ! runuser -u nara -- git -C /opt/nara/app describe --tags --exact-match >/dev/null 2>&1; then
  tag=$(runuser -u nara -- git -C /opt/nara/app tag --sort=-creatordate | head -n 1)
  runuser -u nara -- git -C /opt/nara/app checkout -q --detach "refs/tags/$tag"
  log "저장소: $tag"
fi
install -d /etc/systemd/journald.conf.d
printf '[Journal]\nSystemMaxUse=2G\n' > /etc/systemd/journald.conf.d/nara.conf

# 3. PostgreSQL 16 클러스터, 5434 (INSTALL §2). 역할·DB 내용은 import.sh가 만든다
if ! pg_lsclusters -h | awk '$1==16 && $2=="main"' | grep -q .; then
  pg_createcluster 16 main --port 5434 --start -- --encoding=UTF8 --locale=C.UTF-8
fi
sed -i 's/^port = .*/port = 5434/' /etc/postgresql/16/main/postgresql.conf
systemctl restart postgresql@16-main
systemctl enable postgresql >/dev/null

# 4. 방화벽: ufw가 켜져 있으면 22·80·443을 연다(GCP 방화벽 규칙은 따로)
if command -v ufw >/dev/null && ufw status | grep -q 'Status: active'; then
  ufw allow 22/tcp >/dev/null && ufw allow 80/tcp >/dev/null && ufw allow 443/tcp >/dev/null
fi

# 5. vLLM과 모델 (INSTALL §4, docs/LLM_SETUP.md)
if [[ ! -x /opt/nara/vllm-venv/bin/vllm ]]; then
  runuser -u nara -- env HOME=/var/lib/nara uv venv -q --python 3.12 /opt/nara/vllm-venv
  runuser -u nara -- env HOME=/var/lib/nara uv pip install -q --python /opt/nara/vllm-venv/bin/python "vllm==$VLLM_VERSION"
fi
runuser -u nara -- env HOME=/var/lib/nara HF_HOME=/var/lib/hf-cache /opt/nara/vllm-venv/bin/python -c \
  "from huggingface_hub import snapshot_download as d; print(d('$MODEL'))"
runuser -u nara -- env HOME=/var/lib/nara uv cache clean -q || true

log "완료. 다음: import.sh(비밀값·DB) → deploy.sh <태그> → set-host.sh <주소> → 서비스 켜기 (MIGRATE.md)"

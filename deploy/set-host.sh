#!/usr/bin/env bash
# 접속 주소 설정·변경 (P4, docs/ops/INSTALL.md §6). 운영 서버에서 root로:
#
#   sudo /opt/nara/app/deploy/set-host.sh 34-0-113-5.sslip.io     # 도메인 전 임시 주소(외부 IP를 -로)
#   sudo /opt/nara/app/deploy/set-host.sh nara.<회사 도메인>       # 도메인이 정해지면 같은 명령으로 교체
#
# 1. 주소 형식 확인(틀리면 아무것도 바꾸지 않음)
# 2. 인증서가 없으면 certbot --standalone으로 발급(발급 동안 nginx를 잠깐 멈춤, 80 포트 필요)
# 3. deploy/nginx/nara.conf의 nara.example.com을 주소로 바꿔 sites-available/nara에 쓰고 연결
# 4. nara.env의 APP_ORIGIN=https://<주소> → nginx -t → reload → nara-api 재시작
# 주소가 바뀌면 쿠키 도메인이 달라져 모두 다시 로그인해야 한다.
set -euo pipefail

HOST=${1:-}
SRC=$(cd "$(dirname "$0")" && pwd)
NGINX_DIR=${NARA_NGINX_DIR:-/etc/nginx}
ENV_FILE=${NARA_ENV_FILE_PATH:-/etc/nara/nara.env}
LE_DIR=${NARA_LE_DIR:-/etc/letsencrypt}

log() { echo "[set-host] $*" >&2; }

# 점이 하나 이상인 호스트 이름만 (스킴·경로·공백·특수문자 거부)
if [[ ! $HOST =~ ^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$ ]]; then
  log "사용법: set-host.sh <호스트 이름> (예: 34-0-113-5.sslip.io). 받은 값: '$HOST'"
  exit 2
fi

if [[ ! -f $LE_DIR/live/$HOST/fullchain.pem ]]; then
  if [[ -n ${CERTBOT_EMAIL:-} ]]; then
    account=(-m "$CERTBOT_EMAIL")
  else
    account=(--register-unsafely-without-email)
  fi
  log "인증서 발급: $HOST"
  certbot certonly --standalone --non-interactive --agree-tos "${account[@]}" -d "$HOST" \
    --pre-hook "systemctl stop nginx" --post-hook "systemctl start nginx"
fi

sed "s/nara\.example\.com/$HOST/g" "$SRC/nginx/nara.conf" >"$NGINX_DIR/sites-available/nara.next"
mv -f "$NGINX_DIR/sites-available/nara.next" "$NGINX_DIR/sites-available/nara"
install -m 0644 "$SRC/nginx/snippets/nara-security.conf" "$NGINX_DIR/snippets/nara-security.conf"
ln -sfn "$NGINX_DIR/sites-available/nara" "$NGINX_DIR/sites-enabled/nara"

if grep -q '^APP_ORIGIN=' "$ENV_FILE"; then
  sed -i "s#^APP_ORIGIN=.*#APP_ORIGIN=https://$HOST#" "$ENV_FILE"
else
  echo "APP_ORIGIN=https://$HOST" >>"$ENV_FILE"
fi

nginx -t
systemctl reload nginx
systemctl restart nara-api
log "완료: https://$HOST (APP_ORIGIN 갱신, nara-api 재시작)"

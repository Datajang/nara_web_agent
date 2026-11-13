# 운영 서버 첫 설치 (P4, SPEC §11)

**운영자가 직접 실행한다.** 저장소는 명령만 제공한다. 서버: GCP L4 VM, Debian 11, 드라이버 550.
포트·경로 결정은 `docs/decisions/2026-11-11-p4-ops.md`. 배포는 `DEPLOY.md`, 전환은 `CUTOVER.md`.

## 1. 사용자·디렉터리 (§11.2)
```bash
sudo useradd --system --home /var/lib/nara --shell /usr/sbin/nologin nara
sudo install -d -o nara -g nara -m 0750 /opt/nara /var/lib/nara /var/lib/nara/tmp /var/lib/hf-cache
sudo install -d -o nara -g nara -m 0700 /var/backups/nara /var/backups/nara/weekly
sudo install -d -o root -g nara -m 0750 /etc/nara
sudo -u nara git clone https://github.com/<조직>/AX_Team_Nara_bot.git /opt/nara/app
sudo install -m 0755 ~/.local/bin/uv /usr/local/bin/uv        # nara가 쓸 uv
printf '[Journal]\nSystemMaxUse=2G\n' | sudo tee /etc/systemd/journald.conf.d/nara.conf
```

## 2. PostgreSQL 16 (PGDG, 포트 5434)
5432는 시스템 PG13(모든 주소에 열려 있음 — 별도 점검 권장), 5433은 개발 Docker가 쓴다.
```bash
sudo apt install -y postgresql-common && sudo /usr/share/postgresql-common/pgdg/apt.postgresql.org.sh
sudo apt install -y postgresql-16
pg_lsclusters                                   # 16 main의 포트 확인
sudo sed -i 's/^port = .*/port = 5434/' /etc/postgresql/16/main/postgresql.conf
sudo systemctl restart postgresql@16-main
DBPW=$(openssl rand -hex 24); echo "$DBPW"      # nara.env에 넣을 값
sudo -u postgres psql -p 5434 -c "CREATE ROLE nara LOGIN PASSWORD '$DBPW'" -c "CREATE DATABASE nara OWNER nara"
```
`listen_addresses`는 기본값(localhost)을 유지한다.

## 3. 설정 파일
```bash
sudo install -o root -g nara -m 0640 /opt/nara/app/deploy/nara.env.example /etc/nara/nara.env
sudoedit /etc/nara/nara.env        # 빈 값 채우기: SECRET_KEY(openssl rand -hex 32), DB 비번, SMTP, G2B 키, LLM_API_KEY
echo "VLLM_API_KEY=<LLM_API_KEY와 같은 값>" | sudo install -o root -g nara -m 0640 /dev/stdin /etc/nara/vllm.env
```

## 4. vLLM (docs/LLM_SETUP.md 측정 버전)
```bash
sudo -u nara uv venv --python 3.12 /opt/nara/vllm-venv
sudo -u nara uv pip install --python /opt/nara/vllm-venv/bin/python "vllm==0.19.1"
# 쓰는 모델(19GB)만 복사. 캐시 전체(85GB, 2026-11-13)는 남은 디스크(69GB)를 넘는다
sudo install -d -o nara -g nara /var/lib/hf-cache/hub
sudo cp -a ~/.cache/huggingface/hub/models--Qwen--Qwen3.5-9B /var/lib/hf-cache/hub/ && sudo chown -R nara:nara /var/lib/hf-cache
```

## 5. 백업 키 (§11.5) — 개인키는 서버에 두지 않는다
```bash
sudo apt install -y age
age-keygen -o nara-backup-key.txt      # 운영자 PC에서. 출력된 public key를 아래에
echo "age1..." | sudo install -o root -g nara -m 0644 /dev/stdin /etc/nara/backup.pub
```

## 6. 외부 접속·HTTPS (도메인 전에는 임시 주소)
운영 설정은 HTTPS·Secure 쿠키를 강제한다. 도메인이 없으면 외부 IP로 만든 `<IP를 -로>.sslip.io`
(공개 DNS 서비스, 예: 34-0-113-5.sslip.io)에 Let's Encrypt 인증서를 받는다. 결정: `docs/decisions/2026-11-11-p4-ops.md`.
```bash
# (gcloud 권한이 있는 PC에서) 외부 IP 고정 → 80·443 열기. VM 서비스 계정은 권한이 없다
gcloud compute addresses create nara-ip --addresses=<외부IP> --region=<리전>
gcloud compute instances add-tags <인스턴스> --zone=<존> --tags=nara-web
gcloud compute firewall-rules create nara-web-https --allow=tcp:80,tcp:443 \
  --target-tags=nara-web --source-ranges=0.0.0.0/0     # 사내만이면 사내 IP 대역으로
# (서버에서)
sudo apt install -y nginx certbot && sudo rm -f /etc/nginx/sites-enabled/default
sudo CERTBOT_EMAIL=<운영 메일> /opt/nara/app/deploy/set-host.sh <IP를 -로>.sslip.io
```
도메인이 정해지면 DNS A 레코드를 같은 IP로 두고 `set-host.sh <도메인>`만 다시 실행한다(전원 재로그인).
인증서 갱신은 certbot 타이머가 한다(갱신 때 nginx가 몇 초 멈춤): `sudo certbot renew --dry-run`.

## 7. 첫 배포와 타이머
```bash
sudo -u nara git -C /opt/nara/app checkout --detach <첫 태그>   # deploy.sh는 지금 태그를 .prev로 쓴다
sudo /opt/nara/app/deploy/deploy.sh <첫 태그>
sudo systemctl enable --now nara-vllm nara-api nara-collector.timer nara-backup.timer nara-alert.timer
cd /opt/nara/app/backend && sudo -u nara env NARA_ENV_FILE=/etc/nara/nara.env \
  /opt/nara/venv/bin/python -m app.cli create-admin --email <관리자 이메일>
sudo -u nara env NARA_ENV_FILE=/etc/nara/nara.env /opt/nara/venv/bin/python -m app.collector backfill --days 90
```

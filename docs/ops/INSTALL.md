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
sudo cp -a ~/.cache/huggingface/hub /var/lib/hf-cache/ && sudo chown -R nara:nara /var/lib/hf-cache
```

## 5. 백업 키 (§11.5) — 개인키는 서버에 두지 않는다
```bash
sudo apt install -y age
age-keygen -o nara-backup-key.txt      # 운영자 PC에서. 출력된 public key를 아래에
echo "age1..." | sudo install -o root -g nara -m 0644 /dev/stdin /etc/nara/backup.pub
```

## 6. nginx·HTTPS (도메인 확정 후)
```bash
sudo apt install -y nginx certbot
sudo certbot certonly --standalone -d <도메인> \
  --pre-hook "systemctl stop nginx" --post-hook "systemctl start nginx"
sudo sed "s/nara.example.com/<도메인>/g" /opt/nara/app/deploy/nginx/nara.conf | sudo tee /etc/nginx/sites-available/nara >/dev/null
sudo cp /opt/nara/app/deploy/nginx/snippets/nara-security.conf /etc/nginx/snippets/
sudo ln -s /etc/nginx/sites-available/nara /etc/nginx/sites-enabled/nara
sudo nginx -t && sudo systemctl reload nginx
```
방화벽: GCP에서 80·443만 열고 SSH는 IAP 터널(§11.1). 파일럿 동안은 사내 IP 대역으로 제한 권장.

## 7. 첫 배포와 타이머
```bash
sudo -u nara git -C /opt/nara/app checkout --detach <첫 태그>   # deploy.sh는 지금 태그를 .prev로 쓴다
sudo /opt/nara/app/deploy/deploy.sh <첫 태그>
sudo systemctl enable --now nara-vllm nara-api nara-collector.timer nara-backup.timer nara-alert.timer
cd /opt/nara/app/backend && sudo -u nara env NARA_ENV_FILE=/etc/nara/nara.env \
  /opt/nara/venv/bin/python -m app.cli create-admin --email <관리자 이메일>
sudo -u nara env NARA_ENV_FILE=/etc/nara/nara.env /opt/nara/venv/bin/python -m app.collector backfill --days 90
```

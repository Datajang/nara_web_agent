# 서버 이전 — 옛 VM → 새 VM (2026-11-23)

코드는 git(공개 저장소)으로 받고, git에 없는 것(운영 DB·`/etc/nara` 비밀값·로컬 파일)은 `export.sh`가
**백업 공개키로 암호화한 파일 하나**로 묶는다. 푸는 데는 운영자 PC의 백업 개인키(`nara-backup-key.txt`)가 필요하다.
스크립트: `deploy/migrate/` — export(옛 서버) → bootstrap(새 서버 환경) → import(새 서버 데이터). 왕복 시험 통과(2026-11-23,
운영 DB 건수·nara.env·backup.pub 동일, 한글 파일 이름 포함).

## 0. 미리 (Cloud Shell)
- **주소를 그대로 쓰려면 외부 IP를 고정**하고 새 VM에 옮긴다. 확인: `gcloud compute addresses list --filter="address=34.135.176.205"`
  - 없으면: `gcloud compute addresses create nara-ip --addresses=34.135.176.205 --region=us-central1` (권한 필요)
- 새 VM 사양: GPU **L4**(예: `g2-standard-8`), **Debian 12 + NVIDIA 드라이버**(콘솔에서 GPU 선택 시 드라이버 설치 안내를 따르거나
  Deep Learning VM 이미지), 디스크 **150GB 이상**(모델 19GB·vLLM 11GB·DB 수 GB), 존은 IP와 같은 리전(us-central1)

## 1. 옛 서버: 묶기 (전환 직전에)
```bash
sudo systemctl stop nara-collector.timer nara-collector-awards.timer   # 묶는 동안 바뀌지 않게(선택)
sudo /opt/nara/app/deploy/migrate/export.sh /home/searching-doc-rag/AX_Team_Nara_bot
```
- 결과 `~/nara-migrate-YYYY-MM-DD.tar.age`(약 170MB)와 `.sha256`을 VS Code 탐색기에서 **Download**로 PC에 받는다
- 묶은 뒤 새로 생긴 회원·분석은 옮겨지지 않는다 → 묶은 다음 바로 옛 서버를 멈추고(`sudo systemctl stop nara-api nginx`) 전환한다
- `/opt/nara/app`이 이 스크립트가 없는 옛 태그면: `sudo bash <개발 저장소>/deploy/migrate/export.sh <개발 저장소>`

## 2. 새 VM 만들기와 IP 옮기기 (Cloud Shell)
```bash
gcloud compute instances delete-access-config searching-doc-rag --zone=us-central1-a --access-config-name="external-nat"
gcloud compute instances add-access-config <새VM> --zone=<존> --access-config-name="external-nat" --address=34.135.176.205
gcloud compute instances add-tags <새VM> --zone=<존> --tags=nara-web   # 방화벽 nara-web-https(80·443)
```
(IP를 못 옮기면 새 IP로 4단계 `set-host.sh <새IP를-로>.sslip.io` — 접속 주소가 바뀐다)

## 3. 새 서버: 환경 깔기 (약 20~30분, 모델 내려받기 포함)
```bash
nvidia-smi                                   # L4가 보여야 한다
curl -fsSL https://raw.githubusercontent.com/Datajang/nara_web_agent/v2/deploy/migrate/bootstrap.sh -o bootstrap.sh
sudo bash bootstrap.sh
```

## 4. 새 서버: 데이터 풀기 → 배포 → 주소
묶음 파일과 백업 개인키를 VS Code 탐색기에 끌어다 놓아 홈에 올린 뒤:
```bash
sudo NARA_AGE_IDENTITY=$HOME/nara-backup-key.txt /opt/nara/app/deploy/migrate/import.sh \
  $HOME/nara-migrate-YYYY-MM-DD.tar.age            # 개발도 옮기면 뒤에 저장소 경로(6단계 뒤 다시 실행 가능)
shred -u $HOME/nara-backup-key.txt                 # 개인키는 서버에 두지 않는다
TAG=$(git -C /opt/nara/app describe --tags --exact-match)   # bootstrap이 최신 릴리스 태그로 맞춰 둠
sudo /opt/nara/app/deploy/deploy.sh "$TAG"
sudo CERTBOT_EMAIL=<운영 메일> /opt/nara/app/deploy/set-host.sh 34-135-176-205.sslip.io
sudo systemctl enable --now nara-vllm nara-api nara-collector.timer nara-collector-awards.timer nara-backup.timer nara-alert.timer nara-result-watch.timer
curl -s http://127.0.0.1:8010/readyz               # db ok, 몇 분 뒤 llm ok
```
- 비밀값·서명 키가 그대로라 회원은 다시 가입·로그인하지 않아도 된다. 옛 서버가 멈춘 사이의 공고는 수집기가 채운다
- 브라우저 확인: 로그인 → 검색 → 분석 1건 → 우리 수주 현황

## 5. 확인 뒤 옛 VM 지우기
- 새 서버에서 하루 돌려 수집·백업(`systemctl list-timers 'nara-*'`)·경보 메일 확인 → 옛 VM 삭제
- PC의 묶음 파일은 옛 VM을 지운 뒤에도 한동안 보관(그때까지의 전체 백업)

## 6. (선택) 개발 환경 — Claude Code로 계속 개발할 때
```bash
git clone https://github.com/Datajang/nara_web_agent.git ~/AX_Team_Nara_bot && git -C ~/AX_Team_Nara_bot checkout v2
sudo NARA_IMPORT_REPO_ONLY=1 NARA_AGE_IDENTITY=<개인키> /opt/nara/app/deploy/migrate/import.sh <묶음> ~/AX_Team_Nara_bot
#   ↑ .env·git 제외 문서·골든셋 원문·Claude 메모리·개발 DB 덤프만 (운영 DB·/etc/nara는 건드리지 않음). 끝나면 개인키 shred
docker run -d --name nara-pg16 --restart unless-stopped -p 127.0.0.1:5433:5432 \
  -e POSTGRES_USER=nara -e POSTGRES_DB=nara -e POSTGRES_PASSWORD=<backend/.env DATABASE_URL의 비밀번호> postgres:16
docker exec -i nara-pg16 pg_restore -U nara --no-owner -d nara < ~/nara-dev.dump && docker exec nara-pg16 createdb -U nara nara_test
cd ~/AX_Team_Nara_bot/backend && uv sync && cd ../frontend && npm ci       # 테스트 명령은 CLAUDE.md
```
옛 crontab은 `~/crontab-from-old-server.txt` — 경로를 확인한 뒤 `crontab ~/crontab-from-old-server.txt`.
개발 DB 사용자·비밀번호는 `backend/.env`의 `DATABASE_URL`을 따른다.

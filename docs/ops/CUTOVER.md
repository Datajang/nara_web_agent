# v1 → v2 전환·롤백 (P4b, `docs/v1/DEPLOY_CUTOVER.md` 체크리스트의 실행판)

**운영자가 직접 실행한다.** 결정: v1 사용자는 이전하지 않고 새로 가입(P5 생략), v1은 지우지 않고 멈춘다.

## 확인된 현재 상태 (2026-11-11, 읽기 전용 점검)
- v1 `nara-api`: `/app/nara-web`, `127.0.0.1:8001`, `User=searching-doc-rag`, `HTTPS_PROXY` 설정 있음.
- v1 `nara-vllm`: P0-b에서 stop·disable(GPU 15GB 반납). nginx는 **설치돼 있지 않다**(v1 `nginx.conf`는 틀만).
- 도메인 없음: 외부 IP의 역방향 DNS는 GCP 기본값뿐, Cloud DNS는 이 VM 권한으로 조회 불가.
- **유닛 이름 충돌**: v1도 `nara-api.service`·`nara-vllm.service`다. v2 `deploy.sh`가 같은 이름으로 덮어쓰므로 1단계를 먼저 한다.

## 사전 조건
도메인·인증서(INSTALL §6), SMTP 계정, P3a-2(실제 vLLM 스모크) 통과, INSTALL §1~5 완료.

## 1. v1 보존 (이름 바꾸기)
```bash
sudo cp /etc/systemd/system/nara-api.service /etc/systemd/system/nara-v1-api.service
sudo cp /etc/systemd/system/nara-vllm.service /etc/systemd/system/nara-v1-vllm.service
sudo systemctl daemon-reload
sudo systemctl disable --now nara-api && sudo systemctl enable --now nara-v1-api   # v1 계속 동작
DB=$(sed -n 's/^DB_PATH=//p' /app/nara-web/.env); sudo cp -p "${DB:-/data/nara.db}" /var/backups/nara-v1-$(date +%F).db
```

## 2. 키 옮기기 (나머지 값은 새로 만든다, SECRET_KEY 재사용 금지)
```bash
# 화면에 키를 찍지 않고 옮긴다: 빈 줄을 지우고 v1 값을 붙인다
sudo sed -i '/^NARA_API_KEY=$/d;/^NARA_PRESPEC_API_KEY=$/d' /etc/nara/nara.env
sudo sh -c "grep -E '^NARA_(PRESPEC_)?API_KEY=' /app/nara-web/.env >> /etc/nara/nara.env"
grep HTTPS_PROXY /etc/systemd/system/nara-v1-api.service       # 필요하면 nara.env의 HTTPS_PROXY로
```

## 3. v2 기동과 스모크 (v1과 나란히: v2는 8010·8011)
INSTALL §7 실행 후:
```bash
curl -s http://127.0.0.1:8010/readyz          # db ok, llm ok, collector ok
```
브라우저 `https://<도메인>`: 가입 → 메일 인증 → 관리자 승인 → 검색 → 분석 1건 → 내 기록.

## 4. 공지·전환
v1 사용자에게 새 주소와 **새로 가입**해야 함을 알린다. 파일럿(5~10명, 2주) 동안 v1은 그대로 둔다.
파일럿이 끝나면 `sudo systemctl disable --now nara-v1-api` (파일·DB는 지우지 않는다).

## 5. 롤백 (전환 전에 한 번 연습하고 결과를 RUNBOOK 기록란처럼 남긴다)
```bash
sudo systemctl stop nginx nara-api nara-collector.timer nara-alert.timer
sudo systemctl start nara-v1-api        # v1 vLLM이 필요하면 nara-vllm(v2)을 멈춘 뒤 nara-v1-vllm 시작
```
L4 24GB 한 장에 v1(EXAONE)·v2(Qwen) vLLM을 동시에 띄우지 않는다(메모리 부족).

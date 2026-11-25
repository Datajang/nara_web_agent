# 런북·경보·백업 복원 (SPEC §11.5·§11.7·§11.8)

증상별 1차 조치표는 SPEC §11.8을 따른다. 포트만 v2 값으로 읽는다(API 8010, vLLM 8011).

## 경보 (`nara-alert.timer`, 10분마다 `python -m app.ops.check`)
| 경보 키 | 기준 [가정] | 먼저 볼 것 |
|---|---|---|
| `collector_stale` | 수집 2시간 넘게 성공 없음(기록 없음 포함) | `journalctl -u nara-collector -n 100`, 키 만료·예산 |
| `g2b_budget` | 오늘 G2B 호출 ≥ 예산의 80% | 관리자 > 사용량, `G2B_DAILY_CALL_BUDGET` |
| `disk:<경로>` | 사용률 ≥ 80% | `du -sh /var/lib/hf-cache /var/backups/nara /var/lib/postgresql` |
| `readyz` | `/readyz` 3회 연속 실패(약 30분) | `systemctl status nara-api postgresql@16-main` |

- 메일은 `ALERT_EMAIL`로 간다(비우면 로그만). 같은 경보는 6시간(`ALERT_REPEAT_H`)에 한 번, 해소되면 초기화.
- 상태 파일 `/var/lib/nara/alert-state.json`. 경보가 있으면 유닛이 failed로 보인다: `systemctl --failed`.
- 외부 감시: GCP Uptime Check로 `https://<접속 주소>/login` 5분 간격 [가정] (콘솔에서 운영자가 설정).

## 백업
매일 03:30 KST `nara-backup.timer` → `/var/backups/nara/nara-YYYY-MM-DD.dump.age` (일 14개, 주 4개).
```bash
sudo systemctl start nara-backup && ls -l /var/backups/nara /var/backups/nara/weekly
```

## 복원 리허설 (P4 게이트, 분기마다) — 결과를 아래 기록란에 남긴다
```bash
scp nara-backup-key.txt <서버>:/tmp/k && sudo install -m 0600 /tmp/k /root/nara-backup-key.txt && rm /tmp/k
sudo NARA_AGE_IDENTITY=/root/nara-backup-key.txt /opt/nara/app/deploy/restore.sh \
  /var/backups/nara/nara-<날짜>.dump.age nara_restore_test | tee ~/restore-$(date +%F).txt
sudo -u postgres psql -p 5434 -d nara -Atc "select count(*) from bids"      # 운영과 행 수 비교
sudo -u postgres /usr/lib/postgresql/16/bin/dropdb -p 5434 nara_restore_test
sudo shred -u /root/nara-backup-key.txt
```
`restore.sh`는 운영 DB 이름(`nara`)으로는 복원하지 않는다.

## 낙찰 수집(§15, P8 배포 후 한 번)
`deploy.sh`가 마이그레이션 0008과 유닛 파일을 올린 뒤 `sudo systemctl enable --now nara-collector-awards.timer`.
상태: `systemctl list-timers nara-collector-awards.timer`, 결과는 관리자 화면 수집 이력(source=awards).
하루 낙찰 호출은 `G2B_AWARDS_DAILY_BUDGET`(기본 300)에서 멈추고 다음 날 이어서 과거로 채운다.
P11 배포(0010) 뒤 같은 timer가 계약정보(공동수급, source=contracts)도 받는다: 증분 3일, 백필은 한 번에
`G2B_CONTRACTS_BACKFILL_CALLS`(기본 100)회까지(5년이면 약 3달). 나머지 낙찰 몫은 공고 '경쟁 구도'의 개찰 결과 조회에 쓰인다.
P12(0011) 뒤에는 개찰 결과(우리 투찰 결과, source=openings)도 받는다: 낙찰 몫과 따로 `G2B_OPENINGS_DAILY_BUDGET`(기본 300),
최근 14일 낙찰 공고 먼저, 남는 호출로 과거. 관리자 화면 수집 이력에서 source=openings로 확인.

## LLM 사용량 보기 (읽기 전용, 2026-11-24)
`sudo -u postgres psql -p 5434 -d nara -X -v days=14 < deploy/sql/llm_usage.sql` (저장소 루트에서) —
날짜별 호출 수·기능별 호출/지연·시간대별·최대 동시 요청. 외부 LLM API 한도 검토용.

## LLM 동시 호출 상한 시험 (4 → 8, `docs/decisions/2026-11-24-llm-concurrency.md`)
분석 중인 사람이 없을 때 한다(재시작하면 진행 중 SSE가 끊긴다). 같은 키가 두 줄이면 뒤 줄이 이기므로 지우고 넣는다.
```bash
sudo journalctl -u nara-vllm --no-pager | grep -E 'KV cache size|Maximum concurrency' | tail -2   # 용량 확인
sudo cp -a /etc/nara/nara.env /etc/nara/nara.env.before-conc8-$(date -u +%Y%m%dT%H%M%SZ)
sudo sed -i '/^LLM_MAX_CONCURRENCY=/d' /etc/nara/nara.env && echo 'LLM_MAX_CONCURRENCY=8' | sudo tee -a /etc/nara/nara.env
sudo systemctl restart nara-api && sleep 3 && curl -s http://127.0.0.1:8010/readyz
sudo journalctl -u nara-vllm -f | grep -E 'Running|KV cache usage'   # 분석 1건 돌리는 동안 (Ctrl+C로 끝)
```
측정: 아직 분석·요약한 적 없는 첨부 많은 공고를 하나 분석 → 위 사용량 쿼리 2번 표 `analyze`의 시간을 264초와 비교.
vLLM 로그에서 `Running: 8 reqs`·`Waiting: 0`·KV 사용률을 본다. 되돌리기: 백업 파일을 `nara.env`로 복사 → `nara-api` 재시작.

## 북마크 공고 결과 메일 (`nara-result-watch.timer`, 5분, 2026-11-25)
배포(0013 마이그레이션 포함) 뒤 **한 번** 켠다(`deploy.sh`는 타이머를 켜지 않는다). 몫은 `G2B_RESULT_WATCH_DAILY_BUDGET`(3000).
```bash
sudo systemctl enable --now nara-result-watch.timer
systemctl list-timers nara-result-watch.timer
journalctl -u nara-result-watch -n 20 --no-pager   # '결과 메일: 새 감시 N · 바뀐 공고 N · 보낸 메일 N'
```

## 실제 장애 복구
`systemctl stop nara-api nara-collector.timer` → 위 명령으로 새 DB(예: `nara_restored`)에 복원·확인 →
`nara.env`의 `DATABASE_URL` DB 이름을 바꿈 → `systemctl start nara-api nara-collector.timer` → `/readyz`.

## 복원 리허설 기록
| 날짜 | 백업 파일 | alembic | bids 행 수(복원/운영) | 소요 | 수행자 |
|---|---|---|---|---|---|
| 2026-11-13 (개발 DB 사전 리허설, **암호화 대역** — age 미설치) | nara-2026-11-13 (33MB) | 0005 | 56,721 / 56,721 (8개 표 모두 일치) | 백업 5초·복원 12초 | Claude |
| (운영 첫 리허설 후 기록) | | | | | |

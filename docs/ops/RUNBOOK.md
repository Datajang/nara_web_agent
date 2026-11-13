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

## 실제 장애 복구
`systemctl stop nara-api nara-collector.timer` → 위 명령으로 새 DB(예: `nara_restored`)에 복원·확인 →
`nara.env`의 `DATABASE_URL` DB 이름을 바꿈 → `systemctl start nara-api nara-collector.timer` → `/readyz`.

## 복원 리허설 기록
| 날짜 | 백업 파일 | alembic | bids 행 수(복원/운영) | 소요 | 수행자 |
|---|---|---|---|---|---|
| 2026-11-13 (개발 DB 사전 리허설, **암호화 대역** — age 미설치) | nara-2026-11-13 (33MB) | 0005 | 56,721 / 56,721 (8개 표 모두 일치) | 백업 5초·복원 12초 | Claude |
| (운영 첫 리허설 후 기록) | | | | | |

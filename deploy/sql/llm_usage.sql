-- LLM 사용량 집계 (외부 API 전환 검토용, 2026-11-24)
-- 읽기만 한다. 사용자 신원은 내보내지 않고 수만 센다(§9).
--
--   sudo -u postgres psql -p 5434 -d nara -X -v days=14 -f /opt/nara/app/deploy/sql/llm_usage.sql
--
-- 주의
-- - usage_logs는 요청 1건에 1줄이다(llm_calls = 그 요청 안의 LLM 호출 수, repair 재요청 포함).
-- - duration_ms는 요청 전체 시간이다(파일 다운로드·추출·LLM 대기 포함). LLM 순수 지연이 아니다.
-- - created_at은 요청이 끝난 시각이다. 시작 = created_at - duration_ms 로 동시 실행 수를 추정한다.
-- - 시간대는 KST로 본다.

\if :{?days}
\else
  \set days 14
\endif
\pset footer off

\echo '== 1. 날짜별 LLM 사용 (Gemini 무료 하루 한도와 비교할 값: llm_calls) =='
SELECT (created_at AT TIME ZONE 'Asia/Seoul')::date            AS day_kst,
       count(*) FILTER (WHERE llm_calls > 0)                     AS llm_requests,
       sum(llm_calls)                                            AS llm_calls,
       sum(prompt_tokens)                                        AS prompt_tok,
       sum(completion_tokens)                                    AS completion_tok,
       count(DISTINCT user_id) FILTER (WHERE llm_calls > 0)      AS users
FROM usage_logs
WHERE created_at >= now() - make_interval(days => :days)
GROUP BY 1 ORDER BY 1;

\echo '== 2. 기능별 (cache_only = LLM 호출 없이 캐시로 끝난 요청) =='
SELECT event,
       count(*)                                                  AS requests,
       count(*) FILTER (WHERE llm_calls = 0)                     AS cache_only,
       sum(llm_calls)                                            AS llm_calls,
       round(avg(llm_calls) FILTER (WHERE llm_calls > 0), 1)     AS calls_per_req,
       max(llm_calls)                                            AS max_calls,
       round(avg(completion_tokens) FILTER (WHERE llm_calls > 0)) AS out_tok_per_req,
       round((percentile_cont(0.5) WITHIN GROUP (ORDER BY duration_ms)
              FILTER (WHERE llm_calls > 0) / 1000)::numeric, 1)  AS p50_s,
       round((percentile_cont(0.9) WITHIN GROUP (ORDER BY duration_ms)
              FILTER (WHERE llm_calls > 0) / 1000)::numeric, 1)  AS p90_s,
       round(max(duration_ms) FILTER (WHERE llm_calls > 0) / 1000.0, 1) AS max_s
FROM usage_logs
WHERE created_at >= now() - make_interval(days => :days)
  AND event IN ('recommend', 'analyze', 'assistant_turn', 'compare_explain')
GROUP BY event ORDER BY llm_calls DESC NULLS LAST;

\echo '== 3. 시간대별 LLM 호출 (KST, 기간 합계) =='
SELECT extract(hour FROM created_at AT TIME ZONE 'Asia/Seoul')::int AS hour_kst,
       count(*)        AS llm_requests,
       sum(llm_calls)  AS llm_calls
FROM usage_logs
WHERE created_at >= now() - make_interval(days => :days) AND llm_calls > 0
GROUP BY 1 ORDER BY 1;

\echo '== 4. 날짜별 최대 동시 LLM 요청 수 (요청 시작~끝 구간이 겹친 수) =='
WITH r AS (
  SELECT created_at - make_interval(secs => duration_ms / 1000.0) AS t0, created_at AS t1
  FROM usage_logs
  WHERE created_at >= now() - make_interval(days => :days) AND llm_calls > 0
),
ev AS (
  SELECT t0 AS t, 1 AS d FROM r
  UNION ALL
  SELECT t1, -1 FROM r
),
run AS (
  -- 같은 시각이면 끝(-1)을 먼저 처리해 이어 붙은 요청을 겹침으로 세지 않는다
  SELECT t, sum(d) OVER (ORDER BY t, d ROWS UNBOUNDED PRECEDING) AS live FROM ev
)
SELECT (t AT TIME ZONE 'Asia/Seoul')::date AS day_kst, max(live) AS max_concurrent
FROM run GROUP BY 1 ORDER BY 1;

\echo '== 5. 기간 요약 =='
WITH per AS (
  SELECT (created_at AT TIME ZONE 'Asia/Seoul')::date AS d, sum(llm_calls) AS daily
  FROM usage_logs
  WHERE created_at >= now() - make_interval(days => :days) AND llm_calls > 0
  GROUP BY 1
)
SELECT count(*)          AS days_with_llm,
       sum(daily)        AS llm_calls,
       max(daily)        AS max_daily_calls,
       round(avg(daily)) AS avg_daily_calls
FROM per;

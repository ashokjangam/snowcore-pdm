/* ============================================================================
   PIADE root-cause card, per line and alarm code.

   Built only from observed state intervals. A "long breakdown" is one
   downtime interval of at least 10 minutes, the same rule as GOLD.WORK_ORDER
   and the 4-hour warning. For each one we record:
     - short same-code downtime stops in the 60 minutes before it (precursors)
     - whether the same code causes another long breakdown within 24 hours
     - the clock band it started in
     - the state the line entered next (back to running, waiting, ...)

   What this is not: PIADE alarm codes are anonymised, so no component,
   failure mode or technician finding can be named. Clock bands are fixed
   8-hour windows in dataset time (UTC); the real shift rota is unknown.
   Pattern thresholds (50%) are chosen, not learned, and are listed here.
   ========================================================================== */

USE ROLE ACCOUNTADMIN;
USE DATABASE SNOWCORE_REAL;
USE WAREHOUSE COMPUTE_WH;
ALTER SESSION SET TIMEZONE = 'UTC';
ALTER SESSION SET QUERY_TAG = 'snowcore-real|piade|root-cause';

CREATE OR REPLACE TABLE GOLD.ROOT_CAUSE_EVENT AS
WITH seq AS (
  SELECT MACHINE_KEY, MACHINE_CODE, INTERVAL_START, STATE_TYPE, ALARM_CODE, DURATION_SEC,
         LEAD(STATE_TYPE) OVER (PARTITION BY MACHINE_KEY ORDER BY INTERVAL_START) AS NEXT_STATE
  FROM SILVER.PIADE_INTERVAL
),
long_stop AS (
  SELECT * FROM seq
  WHERE STATE_TYPE = 'downtime' AND ROUND(DURATION_SEC / 60.0, 2) >= 10
),
short_stop AS (
  SELECT MACHINE_KEY, INTERVAL_START, ALARM_CODE
  FROM SILVER.PIADE_INTERVAL
  WHERE STATE_TYPE = 'downtime' AND ROUND(DURATION_SEC / 60.0, 2) < 10
),
precursor AS (
  SELECT l.MACHINE_KEY, l.INTERVAL_START, COUNT(s.INTERVAL_START) AS N
  FROM long_stop l
  LEFT JOIN short_stop s
    ON s.MACHINE_KEY = l.MACHINE_KEY AND s.ALARM_CODE = l.ALARM_CODE
   AND s.INTERVAL_START >= DATEADD('minute', -60, l.INTERVAL_START)
   AND s.INTERVAL_START <  l.INTERVAL_START
  GROUP BY l.MACHINE_KEY, l.INTERVAL_START
),
repeat_24h AS (
  SELECT l.MACHINE_KEY, l.INTERVAL_START, COUNT(r.INTERVAL_START) AS N
  FROM long_stop l
  LEFT JOIN long_stop r
    ON r.MACHINE_KEY = l.MACHINE_KEY AND r.ALARM_CODE = l.ALARM_CODE
   AND r.INTERVAL_START >  l.INTERVAL_START
   AND r.INTERVAL_START <= DATEADD('hour', 24, l.INTERVAL_START)
  GROUP BY l.MACHINE_KEY, l.INTERVAL_START
)
SELECT
  l.MACHINE_KEY, l.MACHINE_CODE, l.INTERVAL_START AS STOP_START, l.ALARM_CODE,
  ROUND(l.DURATION_SEC / 60.0, 2) AS STOP_DURATION_MIN,
  p.N AS PRECURSOR_SHORT_STOPS_60M,
  r.N AS SAME_CODE_REPEATS_24H,
  CASE
    WHEN DATE_PART('hour', l.INTERVAL_START) BETWEEN 6 AND 13 THEN 'EARLY_06_14'
    WHEN DATE_PART('hour', l.INTERVAL_START) BETWEEN 14 AND 21 THEN 'LATE_14_22'
    ELSE 'NIGHT_22_06'
  END AS CLOCK_BAND,
  CASE
    WHEN l.NEXT_STATE IN ('production', 'performance_loss') THEN 'BACK_TO_RUNNING'
    WHEN l.NEXT_STATE = 'idle' THEN 'WAITING'
    WHEN l.NEXT_STATE = 'downtime' THEN 'ANOTHER_BREAKDOWN'
    WHEN l.NEXT_STATE = 'scheduled_downtime' THEN 'PLANNED_STOP'
    ELSE 'END_OF_DATA'
  END AS NEXT_STATE_GROUP,
  'DERIVED_FROM_OBSERVED' AS DATA_ORIGIN
FROM long_stop l
JOIN precursor p  ON p.MACHINE_KEY = l.MACHINE_KEY AND p.INTERVAL_START = l.INTERVAL_START
JOIN repeat_24h r ON r.MACHINE_KEY = l.MACHINE_KEY AND r.INTERVAL_START = l.INTERVAL_START;

COMMENT ON TABLE GOLD.ROOT_CAUSE_EVENT IS
  'One row per observed long breakdown (downtime interval >= 10 min) with precursor, repeat, clock-band and next-state context.';

CREATE OR REPLACE VIEW GOLD.V_ROOT_CAUSE_ALARM AS
WITH agg AS (
  SELECT
    MACHINE_KEY, MACHINE_CODE, ALARM_CODE,
    COUNT(*)                                          AS LONG_BREAKDOWNS,
    SUM(STOP_DURATION_MIN) / 60                       AS BREAKDOWN_HOURS,
    MEDIAN(STOP_DURATION_MIN)                         AS MEDIAN_STOP_MIN,
    MAX(STOP_DURATION_MIN)                            AS LONGEST_STOP_MIN,
    AVG(IFF(PRECURSOR_SHORT_STOPS_60M > 0, 1, 0))     AS PRECURSOR_RATE,
    AVG(PRECURSOR_SHORT_STOPS_60M)                    AS AVG_PRECURSOR_STOPS,
    AVG(IFF(SAME_CODE_REPEATS_24H > 0, 1, 0))         AS REPEAT_24H_RATE,
    AVG(IFF(CLOCK_BAND = 'EARLY_06_14', 1, 0))        AS EARLY_SHARE,
    AVG(IFF(CLOCK_BAND = 'LATE_14_22', 1, 0))         AS LATE_SHARE,
    AVG(IFF(CLOCK_BAND = 'NIGHT_22_06', 1, 0))        AS NIGHT_SHARE,
    AVG(IFF(NEXT_STATE_GROUP = 'BACK_TO_RUNNING', 1, 0))   AS BACK_TO_RUNNING_RATE,
    AVG(IFF(NEXT_STATE_GROUP = 'WAITING', 1, 0))           AS WAITING_AFTER_RATE,
    AVG(IFF(NEXT_STATE_GROUP = 'ANOTHER_BREAKDOWN', 1, 0)) AS ANOTHER_BREAKDOWN_RATE,
    MIN(STOP_START)                                   AS FIRST_SEEN,
    MAX(STOP_START)                                   AS LAST_SEEN
  FROM GOLD.ROOT_CAUSE_EVENT
  GROUP BY MACHINE_KEY, MACHINE_CODE, ALARM_CODE
)
SELECT
  'PLANT_B' AS PLANT_CODE, a.*,
  100 * BREAKDOWN_HOURS / SUM(BREAKDOWN_HOURS) OVER (PARTITION BY MACHINE_KEY) AS SHARE_OF_LINE_BREAKDOWN_PCT,
  ROW_NUMBER() OVER (PARTITION BY MACHINE_KEY ORDER BY BREAKDOWN_HOURS DESC, ALARM_CODE) AS RANK_IN_LINE,
  CASE
    WHEN LONG_BREAKDOWNS < 5 THEN 'TOO_FEW_EVENTS'
    WHEN REPEAT_24H_RATE >= 0.5 THEN 'REPEATS_WITHIN_A_DAY'
    WHEN PRECURSOR_RATE >= 0.5 THEN 'SHORT_STOPS_COME_FIRST'
    WHEN GREATEST(EARLY_SHARE, LATE_SHARE, NIGHT_SHARE) >= 0.5 THEN 'CLOCK_BAND_CLUSTERED'
    WHEN WAITING_AFTER_RATE >= 0.5 THEN 'LINE_WAITS_AFTER_REPAIR'
    ELSE 'NO_DOMINANT_PATTERN'
  END AS PATTERN,
  'DERIVED_FROM_OBSERVED' AS DATA_ORIGIN
FROM agg a;

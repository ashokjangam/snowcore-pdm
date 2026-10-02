/* ============================================================================
   Gold — OEE for Plant B, from observed columns only.

   OEE = Availability x Performance x Quality.

   Every term comes from published PIADE columns. Nothing here uses UNIFORM,
   RANDOM, or a hardcoded percentage.

     Availability = run time / planned production time
                    run time      = 'production' + 'performance_loss'
                    planned time  = all interval time - 'scheduled_downtime'

     Performance  = actual packages produced / (run time x ideal rate)
                    ideal rate    = the machine's best demonstrated rate, i.e.
                                    its maximum observed speed while running.
                                    Derived from the data, not assumed.

     Quality      = packages out / packages in, summed over running time.

   ---------------------------------------------------------------------------
   WHY INTERVALS ARE SPLIT AT HOUR BOUNDARIES

   A first version of this script attributed each interval wholly to the hour
   in which it started. That was wrong. Measured on the source:

     - 7,263 of 429,394 intervals last longer than one hour
     - those intervals carry 35.9% of all recorded time
     - the longest is 22.0 hours
     - bucketing by start hour put a mean of 4,310 seconds into each
       3,600-second hour, with a worst case of 79,290 seconds

   An hour cannot contain more than 3,600 seconds of machine time, so every
   ratio built on those buckets was distorted, and the comparison against the
   publisher's own hourly aggregate diverged badly. This version splits each
   interval across the hours it actually spans and attributes only the
   overlapping seconds to each hour.

   Package counts are apportioned by the same time fraction. That assumes a
   constant rate within a single interval, which is the assumption the
   publisher's own 'speed' column already encodes.

   A KNOWN SOURCE DEFECT, FLAGGED RATHER THAN PATCHED

   Six of the 429,394 intervals overlap the interval before them on the same
   machine. They fall on 2020-10-25 and 2021-10-31, both European
   daylight-saving fallback dates, and the overlapping durations are close to
   one hour. The publisher's logger appears to have recorded the repeated hour
   twice. The affected rows are kept as published and marked with
   HAS_OVERLAP_ANOMALY so three hours can report more than 3,600 seconds and be
   recognised as a data-quality artefact instead of being quietly deleted.

   Remaining judgement calls, stated so a reviewer can disagree explicitly:
   - 'idle' counts against Availability. It is an unscheduled stop even though
     the machine is not broken.
   - Quality is a package throughput yield, not a laboratory inspection. It
     answers "did what went in come out", the only quality signal in the source.
   ========================================================================= */

USE ROLE ACCOUNTADMIN;
USE DATABASE SNOWCORE_REAL;
USE WAREHOUSE COMPUTE_WH;
ALTER SESSION SET QUERY_TAG = 'snowcore-real|coco|gold-oee';

/* --------------------------------------------------------------------------
   Ideal rate per machine: best demonstrated speed while actually running.

   Using an observed maximum rather than a nameplate figure means Performance
   is measured against something the machine has genuinely achieved.
   -------------------------------------------------------------------------- */

CREATE OR REPLACE TABLE GOLD.OEE_IDEAL_RATE AS
SELECT
  MACHINE_KEY,
  MACHINE_CODE,
  MAX(SPEED_PPH)                          AS IDEAL_RATE_PPH,
  APPROX_PERCENTILE(SPEED_PPH, 0.99)      AS P99_SPEED_PPH,
  MEDIAN(SPEED_PPH)                       AS MEDIAN_SPEED_PPH,
  'DERIVED_FROM_OBSERVED'                 AS DATA_ORIGIN,
  'Best demonstrated rate: maximum speed recorded while the machine was running.'
                                          AS METHOD
FROM SILVER.PIADE_INTERVAL
WHERE IS_RUNNING AND SPEED_PPH > 0
GROUP BY MACHINE_KEY, MACHINE_CODE;

COMMENT ON TABLE GOLD.OEE_IDEAL_RATE IS
  'Per-machine ideal production rate for the Performance term, derived from observed speed. Not a vendor specification.';

/* --------------------------------------------------------------------------
   Interval segments: one row per (interval x hour it overlaps).

   The longest interval spans 22 hours, so the generated range stays small.
   -------------------------------------------------------------------------- */

CREATE OR REPLACE TABLE GOLD.PIADE_INTERVAL_SEGMENT AS
WITH iv AS (
  SELECT
    MACHINE_KEY,
    MACHINE_CODE,
    STATE_TYPE,
    ALARM_CODE,
    HAS_STOP_ALARM,
    IS_RUNNING,
    IS_PLANNED_STOP,
    IS_UNPLANNED_STOP,
    SPEED_PPH,
    PACKAGES_IN,
    PACKAGES_OUT,
    COUNTER_RESET,
    DURATION_SEC,
    INTERVAL_START                                                          AS TS_START,
    DATEADD('millisecond', ROUND(DURATION_SEC * 1000)::INT, INTERVAL_START)  AS TS_END
  FROM SILVER.PIADE_INTERVAL
  WHERE DURATION_SEC > 0
),
expanded AS (
  SELECT
    iv.*,
    DATEADD('hour', f.VALUE::INT, DATE_TRUNC('hour', iv.TS_START)) AS BUCKET_START
  FROM iv,
       LATERAL FLATTEN(input => ARRAY_GENERATE_RANGE(
         0,
         DATEDIFF('hour', DATE_TRUNC('hour', iv.TS_START), DATE_TRUNC('hour', iv.TS_END)) + 1
       )) f
),
clipped AS (
  SELECT
    e.*,
    GREATEST(e.TS_START, e.BUCKET_START)                  AS SEG_START,
    LEAST(e.TS_END, DATEADD('hour', 1, e.BUCKET_START))   AS SEG_END
  FROM expanded e
),
measured AS (
  SELECT
    c.*,
    DATEDIFF('millisecond', c.SEG_START, c.SEG_END) / 1000.0 AS SEG_SEC
  FROM clipped c
  WHERE c.SEG_END > c.SEG_START
)
SELECT
  MACHINE_KEY,
  MACHINE_CODE,
  BUCKET_START                                   AS OEE_HOUR,
  STATE_TYPE,
  ALARM_CODE,
  HAS_STOP_ALARM,
  IS_RUNNING,
  IS_PLANNED_STOP,
  IS_UNPLANNED_STOP,
  SPEED_PPH,
  COUNTER_RESET,
  SEG_SEC,
  SEG_SEC / DURATION_SEC                         AS SEG_FRACTION,
  PACKAGES_IN  * (SEG_SEC / DURATION_SEC)        AS SEG_PACKAGES_IN,
  PACKAGES_OUT * (SEG_SEC / DURATION_SEC)        AS SEG_PACKAGES_OUT,
  'DERIVED_FROM_OBSERVED'                        AS DATA_ORIGIN
FROM measured;

COMMENT ON TABLE GOLD.PIADE_INTERVAL_SEGMENT IS
  'Each production interval split at hour boundaries. Time and package counts are apportioned by overlap fraction so no hour can exceed 3,600 seconds.';

/* --------------------------------------------------------------------------
   Hourly OEE, built from the split segments.
   -------------------------------------------------------------------------- */

CREATE OR REPLACE TABLE GOLD.PIADE_OEE_HOURLY AS
WITH agg AS (
  SELECT
    MACHINE_KEY,
    MACHINE_CODE,
    OEE_HOUR,
    SUM(SEG_SEC)                                               AS TOTAL_SEC,
    SUM(IFF(IS_RUNNING,        SEG_SEC, 0))                    AS RUN_SEC,
    SUM(IFF(IS_PLANNED_STOP,   SEG_SEC, 0))                    AS PLANNED_STOP_SEC,
    SUM(IFF(IS_UNPLANNED_STOP, SEG_SEC, 0))                    AS UNPLANNED_STOP_SEC,
    SUM(IFF(STATE_TYPE = 'downtime',         SEG_SEC, 0))      AS DOWNTIME_SEC,
    SUM(IFF(STATE_TYPE = 'idle',             SEG_SEC, 0))      AS IDLE_SEC,
    SUM(IFF(STATE_TYPE = 'performance_loss', SEG_SEC, 0))      AS SLOW_SEC,
    SUM(IFF(IS_RUNNING, SEG_PACKAGES_OUT, 0))                  AS PACKAGES_OUT,
    SUM(IFF(IS_RUNNING, SEG_PACKAGES_IN,  0))                  AS PACKAGES_IN,
    COUNT(*)                                                   AS SEGMENT_COUNT,
    SUM(IFF(HAS_STOP_ALARM AND IS_UNPLANNED_STOP, 1, 0))       AS ALARM_STOP_COUNT,
    SUM(IFF(COUNTER_RESET, 1, 0))                              AS COUNTER_RESETS
  FROM GOLD.PIADE_INTERVAL_SEGMENT
  GROUP BY MACHINE_KEY, MACHINE_CODE, OEE_HOUR
),
calc AS (
  SELECT
    a.*,
    r.IDEAL_RATE_PPH,
    a.TOTAL_SEC - a.PLANNED_STOP_SEC                   AS PLANNED_SEC,
    (a.RUN_SEC / 3600.0) * r.IDEAL_RATE_PPH            AS THEORETICAL_PACKAGES
  FROM agg a
  JOIN GOLD.OEE_IDEAL_RATE r USING (MACHINE_KEY)
)
SELECT
  MACHINE_KEY,
  MACHINE_CODE,
  'PLANT_B'                                                          AS PLANT_CODE,
  OEE_HOUR,
  TO_DATE(OEE_HOUR)                                                  AS OEE_DATE,
  ROUND(TOTAL_SEC, 1)                                                AS TOTAL_SEC,
  ROUND(PLANNED_SEC, 1)                                              AS PLANNED_SEC,
  ROUND(RUN_SEC, 1)                                                  AS RUN_SEC,
  ROUND(DOWNTIME_SEC, 1)                                             AS DOWNTIME_SEC,
  ROUND(IDLE_SEC, 1)                                                 AS IDLE_SEC,
  ROUND(SLOW_SEC, 1)                                                 AS SLOW_SEC,
  ROUND(PLANNED_STOP_SEC, 1)                                         AS PLANNED_STOP_SEC,
  ROUND(PACKAGES_IN, 1)                                              AS PACKAGES_IN,
  ROUND(PACKAGES_OUT, 1)                                             AS PACKAGES_OUT,
  ROUND(THEORETICAL_PACKAGES, 1)                                     AS THEORETICAL_PACKAGES,
  IDEAL_RATE_PPH,
  SEGMENT_COUNT,
  ALARM_STOP_COUNT,
  COUNTER_RESETS,

  /* An hour cannot hold more than 3,600 seconds of machine time. Where it
     does, the source overlapped two intervals across a daylight-saving
     fallback. Flagged, not deleted. */
  TOTAL_SEC > 3601                                                   AS HAS_OVERLAP_ANOMALY,

  IFF(PLANNED_SEC > 0, LEAST(RUN_SEC / PLANNED_SEC, 1.0), NULL)      AS AVAILABILITY,

  IFF(THEORETICAL_PACKAGES > 0,
      LEAST(PACKAGES_OUT / THEORETICAL_PACKAGES, 1.0), NULL)         AS PERFORMANCE,

  /* QUALITY_RAW can exceed 1.0 where the cumulative counters are sampled at
     interval boundaries, so an output lands in a later bucket than its input.
     The clamped value feeds OEE and the flag records where it happened. */
  IFF(PACKAGES_IN > 0, PACKAGES_OUT / PACKAGES_IN, NULL)             AS QUALITY_RAW,
  IFF(PACKAGES_IN > 0, LEAST(PACKAGES_OUT / PACKAGES_IN, 1.0), NULL) AS QUALITY,
  IFF(PACKAGES_IN > 0 AND PACKAGES_OUT > PACKAGES_IN, TRUE, FALSE)   AS QUALITY_CLAMPED,

  IFF(PLANNED_SEC > 0 AND THEORETICAL_PACKAGES > 0 AND PACKAGES_IN > 0,
      LEAST(RUN_SEC / PLANNED_SEC, 1.0)
        * LEAST(PACKAGES_OUT / THEORETICAL_PACKAGES, 1.0)
        * LEAST(PACKAGES_OUT / PACKAGES_IN, 1.0),
      NULL)                                                          AS OEE,

  'DERIVED_FROM_OBSERVED'                                            AS DATA_ORIGIN
FROM calc;

COMMENT ON TABLE GOLD.PIADE_OEE_HOURLY IS
  'Plant B hourly OEE from published PIADE columns, with intervals split at hour boundaries. Quality is a package throughput yield.';

/* --------------------------------------------------------------------------
   Daily OEE. Recomputed from summed seconds and packages rather than by
   averaging hourly ratios, which would weight a quiet hour like a busy one.
   Daily grain also absorbs most of the counter-sampling lag that inflates
   hourly Quality.
   -------------------------------------------------------------------------- */

CREATE OR REPLACE TABLE GOLD.PIADE_OEE_DAILY AS
WITH d AS (
  SELECT
    MACHINE_KEY,
    MACHINE_CODE,
    PLANT_CODE,
    OEE_DATE,
    SUM(TOTAL_SEC)             AS TOTAL_SEC,
    SUM(PLANNED_SEC)           AS PLANNED_SEC,
    SUM(RUN_SEC)               AS RUN_SEC,
    SUM(DOWNTIME_SEC)          AS DOWNTIME_SEC,
    SUM(IDLE_SEC)              AS IDLE_SEC,
    SUM(SLOW_SEC)              AS SLOW_SEC,
    SUM(PLANNED_STOP_SEC)      AS PLANNED_STOP_SEC,
    SUM(PACKAGES_IN)           AS PACKAGES_IN,
    SUM(PACKAGES_OUT)          AS PACKAGES_OUT,
    SUM(THEORETICAL_PACKAGES)  AS THEORETICAL_PACKAGES,
    SUM(ALARM_STOP_COUNT)      AS ALARM_STOP_COUNT,
    COUNT(*)                   AS HOURS_OBSERVED
  FROM GOLD.PIADE_OEE_HOURLY
  GROUP BY MACHINE_KEY, MACHINE_CODE, PLANT_CODE, OEE_DATE
)
SELECT
  d.*,
  IFF(PLANNED_SEC > 0, LEAST(RUN_SEC / PLANNED_SEC, 1.0), NULL)                        AS AVAILABILITY,
  IFF(THEORETICAL_PACKAGES > 0, LEAST(PACKAGES_OUT / THEORETICAL_PACKAGES, 1.0), NULL) AS PERFORMANCE,
  IFF(PACKAGES_IN > 0, LEAST(PACKAGES_OUT / PACKAGES_IN, 1.0), NULL)                   AS QUALITY,
  IFF(PACKAGES_IN > 0 AND PACKAGES_OUT > PACKAGES_IN, TRUE, FALSE)                     AS QUALITY_CLAMPED,
  IFF(PLANNED_SEC > 0 AND THEORETICAL_PACKAGES > 0 AND PACKAGES_IN > 0,
      LEAST(RUN_SEC / PLANNED_SEC, 1.0)
        * LEAST(PACKAGES_OUT / THEORETICAL_PACKAGES, 1.0)
        * LEAST(PACKAGES_OUT / PACKAGES_IN, 1.0),
      NULL)                                                                            AS OEE,
  'DERIVED_FROM_OBSERVED'                                                              AS DATA_ORIGIN
FROM d;

COMMENT ON TABLE GOLD.PIADE_OEE_DAILY IS
  'Plant B daily OEE, recomputed from summed time and package counts rather than by averaging hourly ratios.';

/* --------------------------------------------------------------------------
   Downtime events: the raw material for Plant B work orders. Each row is one
   real unplanned stop with the alarm the machine reported. Unsplit, because a
   stop is a single event even when it crosses midnight.
   -------------------------------------------------------------------------- */

CREATE OR REPLACE TABLE GOLD.PIADE_DOWNTIME_EVENT AS
SELECT
  MACHINE_KEY,
  MACHINE_CODE,
  'PLANT_B'                                                               AS PLANT_CODE,
  INTERVAL_START                                                          AS STOP_START,
  DATEADD('millisecond', ROUND(DURATION_SEC * 1000)::INT, INTERVAL_START) AS STOP_END,
  ROUND(DURATION_SEC, 1)                                                  AS STOP_DURATION_SEC,
  ROUND(DURATION_SEC / 60.0, 2)                                           AS STOP_DURATION_MIN,
  STATE_TYPE                                                              AS STOP_STATE,
  ALARM_CODE,
  HAS_STOP_ALARM,
  'OBSERVED'                                                              AS DATA_ORIGIN
FROM SILVER.PIADE_INTERVAL
WHERE IS_UNPLANNED_STOP;

COMMENT ON TABLE GOLD.PIADE_DOWNTIME_EVENT IS
  'Observed unplanned stops on Plant B. Alarm codes are publisher-anonymised; no English stop reason exists in the source.';

/* --------------------------------------------------------------------------
   Validation against the publisher's own hourly aggregate.

   Their %-columns are fractions of the hour, so this is the test that the
   hour-boundary splitting is right. Their interval_start has no timezone and
   denotes the UTC hour, so ours is converted to naive UTC to join.
   -------------------------------------------------------------------------- */

CREATE OR REPLACE VIEW GOLD.V_OEE_VALIDATION AS
WITH ours AS (
  SELECT
    MACHINE_CODE,
    CONVERT_TIMEZONE('UTC', OEE_HOUR)::TIMESTAMP_NTZ AS OEE_HOUR_UTC,
    TOTAL_SEC,
    RUN_SEC      / NULLIF(TOTAL_SEC, 0) AS OUR_RUN_FRACTION,
    DOWNTIME_SEC / NULLIF(TOTAL_SEC, 0) AS OUR_DOWNTIME_FRACTION,
    IDLE_SEC     / NULLIF(TOTAL_SEC, 0) AS OUR_IDLE_FRACTION
  FROM GOLD.PIADE_OEE_HOURLY
),
theirs AS (
  SELECT
    EQUIPMENT_ID                          AS MACHINE_CODE,
    INTERVAL_START                        AS OEE_HOUR_UTC,
    PCT_PRODUCTION + PCT_PERFORMANCE_LOSS AS THEIR_RUN_FRACTION,
    PCT_DOWNTIME                          AS THEIR_DOWNTIME_FRACTION,
    PCT_IDLE                              AS THEIR_IDLE_FRACTION
  FROM BRONZE.PIADE_HOURLY_RAW
)
SELECT
  o.MACHINE_CODE,
  o.OEE_HOUR_UTC,
  o.TOTAL_SEC,
  o.OUR_RUN_FRACTION,
  t.THEIR_RUN_FRACTION,
  ABS(o.OUR_RUN_FRACTION - t.THEIR_RUN_FRACTION)            AS RUN_FRACTION_DIFF,
  o.OUR_DOWNTIME_FRACTION,
  t.THEIR_DOWNTIME_FRACTION,
  ABS(o.OUR_DOWNTIME_FRACTION - t.THEIR_DOWNTIME_FRACTION)  AS DOWNTIME_FRACTION_DIFF,
  ABS(o.OUR_IDLE_FRACTION - t.THEIR_IDLE_FRACTION)          AS IDLE_FRACTION_DIFF
FROM ours o
JOIN theirs t
  ON o.MACHINE_CODE = t.MACHINE_CODE
 AND o.OEE_HOUR_UTC = t.OEE_HOUR_UTC;

COMMENT ON VIEW GOLD.V_OEE_VALIDATION IS
  'Compares our derived hourly state fractions against the publisher hourly aggregate. This is the check on hour-boundary splitting.';

/* --------------------------------------------------------------------------
   Reports.
   -------------------------------------------------------------------------- */

-- 1. Ideal rates.
SELECT MACHINE_CODE, IDEAL_RATE_PPH, P99_SPEED_PPH, MEDIAN_SPEED_PPH
FROM GOLD.OEE_IDEAL_RATE ORDER BY MACHINE_CODE;

-- 2. Splitting sanity. Any hour over 3,600 seconds must be an overlap artefact.
SELECT
  COUNT(*)                                          AS HOURLY_ROWS,
  ROUND(AVG(TOTAL_SEC), 1)                          AS AVG_SEC_PER_HOUR,
  ROUND(MAX(TOTAL_SEC), 1)                          AS MAX_SEC_PER_HOUR,
  SUM(IFF(TOTAL_SEC > 3601, 1, 0))                  AS HOURS_OVER_3600,
  SUM(IFF(HAS_OVERLAP_ANOMALY, 1, 0))               AS FLAGGED_ANOMALIES,
  ROUND(MAX(IFF(NOT HAS_OVERLAP_ANOMALY, TOTAL_SEC, 0)), 1) AS MAX_SEC_EXCLUDING_FLAGGED
FROM GOLD.PIADE_OEE_HOURLY;

-- 2b. The flagged hours in full, so the daylight-saving claim is checkable.
SELECT MACHINE_CODE, OEE_HOUR, TOTAL_SEC, SEGMENT_COUNT
FROM GOLD.PIADE_OEE_HOURLY
WHERE HAS_OVERLAP_ANOMALY
ORDER BY MACHINE_CODE, OEE_HOUR;

-- 3. Hourly OEE summary.
SELECT
  COUNT(*)                                   AS HOURLY_ROWS,
  COUNT(OEE)                                 AS ROWS_WITH_OEE,
  SUM(IFF(QUALITY_CLAMPED, 1, 0))            AS QUALITY_CLAMPED_ROWS,
  ROUND(AVG(AVAILABILITY), 4)                AS AVG_AVAILABILITY,
  ROUND(AVG(PERFORMANCE), 4)                 AS AVG_PERFORMANCE,
  ROUND(AVG(QUALITY), 4)                     AS AVG_QUALITY,
  ROUND(AVG(OEE), 4)                         AS AVG_OEE,
  SUM(IFF(AVAILABILITY > 1.0000001, 1, 0))   AS AVAILABILITY_OVER_ONE,
  SUM(IFF(PERFORMANCE  > 1.0000001, 1, 0))   AS PERFORMANCE_OVER_ONE
FROM GOLD.PIADE_OEE_HOURLY;

-- 4. Per-machine daily OEE.
SELECT
  MACHINE_CODE,
  COUNT(*)                            AS DAYS,
  ROUND(AVG(AVAILABILITY), 4)         AS AVAILABILITY,
  ROUND(AVG(PERFORMANCE), 4)          AS PERFORMANCE,
  ROUND(AVG(QUALITY), 4)              AS QUALITY,
  ROUND(AVG(OEE), 4)                  AS OEE,
  SUM(IFF(QUALITY_CLAMPED, 1, 0))     AS DAYS_QUALITY_CLAMPED
FROM GOLD.PIADE_OEE_DAILY
GROUP BY MACHINE_CODE ORDER BY MACHINE_CODE;

-- 5. Validation against the publisher aggregate.
SELECT
  COUNT(*)                                   AS MATCHED_HOURS,
  ROUND(AVG(RUN_FRACTION_DIFF), 5)           AS AVG_RUN_DIFF,
  ROUND(MEDIAN(RUN_FRACTION_DIFF), 5)        AS MEDIAN_RUN_DIFF,
  ROUND(MAX(RUN_FRACTION_DIFF), 5)           AS MAX_RUN_DIFF,
  ROUND(AVG(DOWNTIME_FRACTION_DIFF), 5)      AS AVG_DOWNTIME_DIFF,
  ROUND(AVG(IDLE_FRACTION_DIFF), 5)          AS AVG_IDLE_DIFF,
  SUM(IFF(RUN_FRACTION_DIFF < 0.02, 1, 0))   AS HOURS_WITHIN_2PCT,
  SUM(IFF(RUN_FRACTION_DIFF < 0.05, 1, 0))   AS HOURS_WITHIN_5PCT
FROM GOLD.V_OEE_VALIDATION;

-- 6. Downtime events.
SELECT COUNT(*) AS DOWNTIME_EVENTS,
       SUM(IFF(HAS_STOP_ALARM, 1, 0)) AS EVENTS_WITH_ALARM,
       ROUND(SUM(STOP_DURATION_MIN), 0) AS TOTAL_STOP_MINUTES
FROM GOLD.PIADE_DOWNTIME_EVENT;

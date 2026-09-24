/* ============================================================================
   ML — Plant A (CoMoPI) predictive maintenance.

   WHAT IS BEING PREDICTED, STATED PRECISELY

   For each 10-minute sensor window, will a target-module alarm fire in the
   NEXT 60 minutes? The current window's own alarms are deliberately excluded
   from the label, so this is a forecast and not a restatement of the present.

   WHY THIS LABEL AND NOT THE PUBLISHED ONE

   The publisher's documented fault target is AL_53 + AL_54. Profiling measured
   41 such windows across the whole dataset, of which 10 coincide with a sensor
   row. Ten positives cannot train or evaluate anything. The label here is the
   wider 16-alarm target-module set. This is a real, deliberate departure from
   the published benchmark and no result below should be compared against
   published AL_53/54 figures.

   MEASURED LABEL COUNTS (scripts/probe_label_timeline.py, not estimated)

     sensor rows                                 15,704
     module-alarm windows in the alarm table      1,555
     forward-label positives (alarm within 60m)   3,028  (19.28%)
     concurrent-label positives                     455  ( 2.90%)
     distinct events after merging runs             680

   The forward label is far denser than the concurrent one because sensor rows
   are 10 minutes apart, so a single alarm can be preceded by up to six windows.
   That is the whole point of a lead-time label, but it also means the positives
   are clustered rather than independent. Event-level recall is therefore
   reported alongside row-level metrics, because row-level recall flatters a
   model that fires once inside a long cluster.

   THE SPLIT

   Chronological, never random. Rows before 2022-12-08 08:52 UTC train; rows
   from that moment on are held out. Measured at that cutoff:

     train 12,563 rows / 2,443 positives
     test   3,141 rows /   585 positives

   A 60-minute purge gap is removed from the end of the training period. A
   training row's label looks up to an hour into the future, and without the
   purge the last hour of training would peek across the cutoff.

   KNOWN LIMITS, SO THEY ARE NOT DISCOVERED LATER

   - 16 sensor channels are anonymised and rescaled to [0,1]. Feature
     importance can say which channel matters, never which physical quantity.
   - Machine C004 has no B-side sensors at all (196 rows) and zero positives.
   - 8.9% of consecutive sensor gaps exceed an hour; the largest is 29 days.
     Every rolling feature is therefore time-bounded, not row-bounded, and the
     window's actual sample count is carried as a feature so the model can
     discount a thin window.
   - Positives cluster in time. A high row-level score can come from getting a
     few long clusters right. Read the event-level number first.
   ========================================================================= */

USE ROLE ACCOUNTADMIN;
USE DATABASE SNOWCORE_REAL;
USE WAREHOUSE COMPUTE_WH;
ALTER SESSION SET QUERY_TAG = 'snowcore-real|coco|ml-comopi';

/* --------------------------------------------------------------------------
   Feature store.

   Rolling statistics are computed by an explicit time-bounded self-join rather
   than a row-count window, because the sampling is irregular. "Last hour"
   means the last hour of clock time, including when that holds one row.

   B-side nulls are replaced with -1. The sensors are rescaled into [0,1], so
   -1 is unreachable by a real reading and is therefore a sentinel the model
   can separate rather than a value it will average into the distribution.
   SENSOR_B_AVAILABLE carries the same fact as an explicit flag.
   -------------------------------------------------------------------------- */

CREATE OR REPLACE TABLE ML.COMOPI_FEATURES AS
WITH base AS (
  SELECT
    s.MACHINE_KEY,
    s.MACHINE_CODE,
    s.TIME_UTC,
    s.SENSOR_B_AVAILABLE,
    s.AE, s.AF, s.APP, s.AP, s.ALE, s.ALP, s.ADS, s.AES,
    COALESCE(s.BE,  -1) AS BE,
    COALESCE(s.BF,  -1) AS BF,
    COALESCE(s.BPP, -1) AS BPP,
    COALESCE(s.BP,  -1) AS BP,
    COALESCE(s.BLE, -1) AS BLE,
    COALESCE(s.BLP, -1) AS BLP,
    COALESCE(s.BDS, -1) AS BDS,
    COALESCE(s.BES, -1) AS BES
  FROM SILVER.COMOPI_SENSOR_10MIN s
),
/* Alarms split into the target-module set and everything else. Only the
   "everything else" stream is allowed into the features: feeding the model
   recent module alarms would let it predict the next alarm from the last one
   and learn nothing from the sensors. */
alarm AS (
  SELECT
    MACHINE_KEY,
    TIME_UTC,
    IS_MODULE_ALARM,
    MODULE_ALARM_COUNT,
    ALARM_COUNT_ALL - MODULE_ALARM_COUNT AS OTHER_ALARM_COUNT
  FROM SILVER.COMOPI_ALARM_10MIN
),
roll_1h AS (
  SELECT
    b.MACHINE_KEY, b.TIME_UTC,
    COUNT(*)            AS SAMPLES_1H,
    AVG(h.AE)  AS AE_M1,  STDDEV_POP(h.AE)  AS AE_S1,
    AVG(h.AF)  AS AF_M1,  STDDEV_POP(h.AF)  AS AF_S1,
    AVG(h.APP) AS APP_M1, STDDEV_POP(h.APP) AS APP_S1,
    AVG(h.AP)  AS AP_M1,  STDDEV_POP(h.AP)  AS AP_S1,
    AVG(h.ALE) AS ALE_M1, STDDEV_POP(h.ALE) AS ALE_S1,
    AVG(h.ALP) AS ALP_M1, STDDEV_POP(h.ALP) AS ALP_S1,
    AVG(h.ADS) AS ADS_M1, STDDEV_POP(h.ADS) AS ADS_S1,
    AVG(h.AES) AS AES_M1, STDDEV_POP(h.AES) AS AES_S1,
    AVG(h.BE)  AS BE_M1,  STDDEV_POP(h.BE)  AS BE_S1,
    AVG(h.BF)  AS BF_M1,  STDDEV_POP(h.BF)  AS BF_S1,
    AVG(h.BPP) AS BPP_M1, STDDEV_POP(h.BPP) AS BPP_S1,
    AVG(h.BP)  AS BP_M1,  STDDEV_POP(h.BP)  AS BP_S1,
    AVG(h.BLE) AS BLE_M1, STDDEV_POP(h.BLE) AS BLE_S1,
    AVG(h.BLP) AS BLP_M1, STDDEV_POP(h.BLP) AS BLP_S1,
    AVG(h.BDS) AS BDS_M1, STDDEV_POP(h.BDS) AS BDS_S1,
    AVG(h.BES) AS BES_M1, STDDEV_POP(h.BES) AS BES_S1
  FROM base b
  JOIN base h
    ON  h.MACHINE_KEY = b.MACHINE_KEY
    AND h.TIME_UTC   <= b.TIME_UTC
    AND h.TIME_UTC    > DATEADD('minute', -60, b.TIME_UTC)
  GROUP BY b.MACHINE_KEY, b.TIME_UTC
),
roll_6h AS (
  SELECT
    b.MACHINE_KEY, b.TIME_UTC,
    COUNT(*)   AS SAMPLES_6H,
    AVG(h.AE)  AS AE_M6,  AVG(h.AF)  AS AF_M6,  AVG(h.APP) AS APP_M6,
    AVG(h.AP)  AS AP_M6,  AVG(h.ALE) AS ALE_M6, AVG(h.ALP) AS ALP_M6,
    AVG(h.ADS) AS ADS_M6, AVG(h.AES) AS AES_M6, AVG(h.BE)  AS BE_M6,
    AVG(h.BF)  AS BF_M6,  AVG(h.BPP) AS BPP_M6, AVG(h.BP)  AS BP_M6,
    AVG(h.BLE) AS BLE_M6, AVG(h.BLP) AS BLP_M6, AVG(h.BDS) AS BDS_M6,
    AVG(h.BES) AS BES_M6
  FROM base b
  JOIN base h
    ON  h.MACHINE_KEY = b.MACHINE_KEY
    AND h.TIME_UTC   <= b.TIME_UTC
    AND h.TIME_UTC    > DATEADD('hour', -6, b.TIME_UTC)
  GROUP BY b.MACHINE_KEY, b.TIME_UTC
),
/* Non-module alarm pressure over the previous hour. Past information only. */
other_1h AS (
  SELECT
    b.MACHINE_KEY, b.TIME_UTC,
    SUM(a.OTHER_ALARM_COUNT) AS OTHER_ALARMS_1H
  FROM base b
  JOIN alarm a
    ON  a.MACHINE_KEY = b.MACHINE_KEY
    AND a.TIME_UTC   <= b.TIME_UTC
    AND a.TIME_UTC    > DATEADD('minute', -60, b.TIME_UTC)
  GROUP BY b.MACHINE_KEY, b.TIME_UTC
),
/* The label. Strictly future: an alarm in the same window does not count. */
label AS (
  SELECT
    b.MACHINE_KEY, b.TIME_UTC,
    MAX(IFF(a.IS_MODULE_ALARM, 1, 0)) AS LABEL_RAW
  FROM base b
  LEFT JOIN alarm a
    ON  a.MACHINE_KEY = b.MACHINE_KEY
    AND a.TIME_UTC    > b.TIME_UTC
    AND a.TIME_UTC   <= DATEADD('minute', 60, b.TIME_UTC)
  GROUP BY b.MACHINE_KEY, b.TIME_UTC
),
gaps AS (
  SELECT
    MACHINE_KEY, TIME_UTC,
    DATEDIFF('second', LAG(TIME_UTC) OVER (
      PARTITION BY MACHINE_KEY ORDER BY TIME_UTC), TIME_UTC) AS SEC_SINCE_PREV
  FROM base
)
SELECT
  /* identifiers, not features */
  HASH(b.MACHINE_KEY, b.TIME_UTC)                     AS ROW_ID,
  b.MACHINE_KEY,
  b.TIME_UTC,

  /* categorical feature: which machine. Legitimate — machines differ. */
  b.MACHINE_CODE,

  /* raw readings */
  b.AE, b.AF, b.APP, b.AP, b.ALE, b.ALP, b.ADS, b.AES,
  b.BE, b.BF, b.BPP, b.BP, b.BLE, b.BLP, b.BDS, b.BES,

  /* one-hour level and volatility */
  r1.AE_M1,  r1.AE_S1,  r1.AF_M1,  r1.AF_S1,
  r1.APP_M1, r1.APP_S1, r1.AP_M1,  r1.AP_S1,
  r1.ALE_M1, r1.ALE_S1, r1.ALP_M1, r1.ALP_S1,
  r1.ADS_M1, r1.ADS_S1, r1.AES_M1, r1.AES_S1,
  r1.BE_M1,  r1.BE_S1,  r1.BF_M1,  r1.BF_S1,
  r1.BPP_M1, r1.BPP_S1, r1.BP_M1,  r1.BP_S1,
  r1.BLE_M1, r1.BLE_S1, r1.BLP_M1, r1.BLP_S1,
  r1.BDS_M1, r1.BDS_S1, r1.BES_M1, r1.BES_S1,

  /* drift: current reading against its own six-hour level */
  b.AE  - r6.AE_M6  AS AE_D6,   b.AF  - r6.AF_M6  AS AF_D6,
  b.APP - r6.APP_M6 AS APP_D6,  b.AP  - r6.AP_M6  AS AP_D6,
  b.ALE - r6.ALE_M6 AS ALE_D6,  b.ALP - r6.ALP_M6 AS ALP_D6,
  b.ADS - r6.ADS_M6 AS ADS_D6,  b.AES - r6.AES_M6 AS AES_D6,
  b.BE  - r6.BE_M6  AS BE_D6,   b.BF  - r6.BF_M6  AS BF_D6,
  b.BPP - r6.BPP_M6 AS BPP_D6,  b.BP  - r6.BP_M6  AS BP_D6,
  b.BLE - r6.BLE_M6 AS BLE_D6,  b.BLP - r6.BLP_M6 AS BLP_D6,
  b.BDS - r6.BDS_M6 AS BDS_D6,  b.BES - r6.BES_M6 AS BES_D6,

  /* context: how much data the rolling stats actually rest on */
  r1.SAMPLES_1H,
  r6.SAMPLES_6H,
  COALESCE(g.SEC_SINCE_PREV, -1)         AS SEC_SINCE_PREV,
  IFF(b.SENSOR_B_AVAILABLE, 1, 0)        AS SENSOR_B_AVAILABLE,
  COALESCE(o.OTHER_ALARMS_1H, 0)         AS OTHER_ALARMS_1H,
  HOUR(b.TIME_UTC)                       AS HOUR_OF_DAY,
  DAYOFWEEK(b.TIME_UTC)                  AS DAY_OF_WEEK,

  /* target */
  IFF(l.LABEL_RAW = 1, 'ALARM_60M', 'NORMAL') AS LABEL_ALARM_60M,
  l.LABEL_RAW                                 AS LABEL_INT,
  'DERIVED_FROM_OBSERVED'                     AS DATA_ORIGIN
FROM base b
JOIN roll_1h  r1 ON r1.MACHINE_KEY = b.MACHINE_KEY AND r1.TIME_UTC = b.TIME_UTC
JOIN roll_6h  r6 ON r6.MACHINE_KEY = b.MACHINE_KEY AND r6.TIME_UTC = b.TIME_UTC
JOIN label    l  ON l.MACHINE_KEY  = b.MACHINE_KEY AND l.TIME_UTC  = b.TIME_UTC
LEFT JOIN other_1h o ON o.MACHINE_KEY = b.MACHINE_KEY AND o.TIME_UTC = b.TIME_UTC
LEFT JOIN gaps     g ON g.MACHINE_KEY = b.MACHINE_KEY AND g.TIME_UTC = b.TIME_UTC;

COMMENT ON TABLE ML.COMOPI_FEATURES IS
  'Plant A feature store. Label is a target-module alarm in the next 60 minutes, strictly future. Recent module alarms are excluded from the features on purpose.';

/* --------------------------------------------------------------------------
   Chronological split with a purge gap.
   -------------------------------------------------------------------------- */

CREATE OR REPLACE TABLE ML.COMOPI_SPLIT AS
SELECT
  ROW_ID,
  CASE
    WHEN TIME_UTC <  DATEADD('minute', -60, '2022-12-08 08:52:00'::TIMESTAMP_NTZ) THEN 'TRAIN'
    WHEN TIME_UTC >= '2022-12-08 08:52:00'::TIMESTAMP_NTZ                         THEN 'TEST'
    ELSE 'PURGED'
  END AS SPLIT_PART
FROM ML.COMOPI_FEATURES;

COMMENT ON TABLE ML.COMOPI_SPLIT IS
  'Time-ordered split. PURGED is the 60 minutes before the cutoff, removed because a training label there would look past the cutoff.';

/* Training view: features plus target, no identifiers or leakage columns. */
CREATE OR REPLACE VIEW ML.COMOPI_TRAIN AS
SELECT f.* EXCLUDE (ROW_ID, MACHINE_KEY, TIME_UTC, LABEL_INT, DATA_ORIGIN)
FROM ML.COMOPI_FEATURES f
JOIN ML.COMOPI_SPLIT s ON s.ROW_ID = f.ROW_ID
WHERE s.SPLIT_PART = 'TRAIN';

/* Scoring view: same features, target removed, ROW_ID kept to join back. */
CREATE OR REPLACE VIEW ML.COMOPI_TEST_X AS
SELECT f.* EXCLUDE (MACHINE_KEY, TIME_UTC, LABEL_ALARM_60M, LABEL_INT, DATA_ORIGIN)
FROM ML.COMOPI_FEATURES f
JOIN ML.COMOPI_SPLIT s ON s.ROW_ID = f.ROW_ID
WHERE s.SPLIT_PART = 'TEST';

/* Split reconciliation. Expected from local measurement, allowing for the
   purge: TRAIN near 12,500 with ~2,430 positives, TEST 3,141 with 585. */
SELECT
  s.SPLIT_PART,
  COUNT(*)                                     AS ROWS_IN_PART,
  SUM(f.LABEL_INT)                             AS POSITIVES,
  ROUND(AVG(f.LABEL_INT) * 100, 2)             AS POSITIVE_PCT,
  MIN(f.TIME_UTC)                              AS FIRST_TS,
  MAX(f.TIME_UTC)                              AS LAST_TS
FROM ML.COMOPI_FEATURES f
JOIN ML.COMOPI_SPLIT s ON s.ROW_ID = f.ROW_ID
GROUP BY s.SPLIT_PART
ORDER BY FIRST_TS;

/* --------------------------------------------------------------------------
   Train. Snowflake-native classification, no external library.
   -------------------------------------------------------------------------- */

CREATE OR REPLACE SNOWFLAKE.ML.CLASSIFICATION ML.COMOPI_ALARM_MODEL(
  INPUT_DATA      => SYSTEM$REFERENCE('VIEW', 'ML.COMOPI_TRAIN'),
  TARGET_COLNAME  => 'LABEL_ALARM_60M',
  CONFIG_OBJECT   => {'on_error': 'skip'}
);

/* These come from the model's own internal validation on the TRAINING period.
   They are not the holdout result and must never be quoted as such. */
CALL ML.COMOPI_ALARM_MODEL!SHOW_EVALUATION_METRICS();
CALL ML.COMOPI_ALARM_MODEL!SHOW_GLOBAL_EVALUATION_METRICS();
CALL ML.COMOPI_ALARM_MODEL!SHOW_FEATURE_IMPORTANCE();

/* --------------------------------------------------------------------------
   Score the held-out period.
   -------------------------------------------------------------------------- */

CREATE OR REPLACE TABLE ML.COMOPI_PREDICTIONS AS
WITH scored AS (
  SELECT
    x.ROW_ID,
    ML.COMOPI_ALARM_MODEL!PREDICT(
      INPUT_DATA => OBJECT_CONSTRUCT(*),
      CONFIG_OBJECT => {'ON_ERROR': 'SKIP'}
    ) AS PRED
  FROM ML.COMOPI_TEST_X x
)
SELECT
  f.ROW_ID,
  f.MACHINE_KEY,
  f.MACHINE_CODE,
  f.TIME_UTC,
  f.LABEL_INT                                            AS ACTUAL,
  s.PRED:class::STRING                                   AS PREDICTED_CLASS,
  s.PRED:probability:ALARM_60M::FLOAT                    AS P_ALARM,
  'DERIVED_FROM_OBSERVED'                                AS DATA_ORIGIN
FROM scored s
JOIN ML.COMOPI_FEATURES f ON f.ROW_ID = s.ROW_ID;

COMMENT ON TABLE ML.COMOPI_PREDICTIONS IS
  'Held-out predictions for Plant A, 2022-12-08 onward. Never scored on rows the model trained on.';

/* --------------------------------------------------------------------------
   Evaluation on the held-out period.
   -------------------------------------------------------------------------- */

/* 1. The baseline anyone can beat without a model: always say ALARM.
      Any model whose precision is not clearly above BASE_RATE_PCT is worthless
      no matter how good its recall looks. */
SELECT
  COUNT(*)                            AS TEST_ROWS,
  SUM(ACTUAL)                         AS POSITIVES,
  ROUND(AVG(ACTUAL) * 100, 2)         AS BASE_RATE_PCT,
  ROUND(AVG(P_ALARM), 4)              AS MEAN_PREDICTED_PROB
FROM ML.COMOPI_PREDICTIONS;

/* 2. Row-level performance across thresholds. Precision below the base rate
      at any threshold means the model is worse than guessing there. */
WITH t AS (
  SELECT VALUE::FLOAT AS THRESHOLD
  FROM TABLE(FLATTEN(input => [0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80]))
)
SELECT
  t.THRESHOLD,
  SUM(IFF(p.P_ALARM >= t.THRESHOLD AND p.ACTUAL = 1, 1, 0))      AS TRUE_POS,
  SUM(IFF(p.P_ALARM >= t.THRESHOLD AND p.ACTUAL = 0, 1, 0))      AS FALSE_POS,
  SUM(IFF(p.P_ALARM <  t.THRESHOLD AND p.ACTUAL = 1, 1, 0))      AS FALSE_NEG,
  SUM(IFF(p.P_ALARM <  t.THRESHOLD AND p.ACTUAL = 0, 1, 0))      AS TRUE_NEG,
  ROUND(DIV0(SUM(IFF(p.P_ALARM >= t.THRESHOLD AND p.ACTUAL = 1, 1, 0)),
             SUM(IFF(p.P_ALARM >= t.THRESHOLD, 1, 0))) * 100, 2) AS PRECISION_PCT,
  ROUND(DIV0(SUM(IFF(p.P_ALARM >= t.THRESHOLD AND p.ACTUAL = 1, 1, 0)),
             SUM(p.ACTUAL)) * 100, 2)                            AS RECALL_PCT
FROM ML.COMOPI_PREDICTIONS p, t
GROUP BY t.THRESHOLD
ORDER BY t.THRESHOLD;

/* 3. Event-level recall, which is the number a maintenance planner cares
      about. Consecutive positive windows on one machine are one event. The
      event counts as caught if the model crossed the threshold anywhere
      inside it. Row-level recall overstates this whenever events are long. */
WITH ordered AS (
  SELECT
    MACHINE_KEY, TIME_UTC, ACTUAL, P_ALARM,
    LAG(ACTUAL) OVER (PARTITION BY MACHINE_KEY ORDER BY TIME_UTC) AS PREV_ACTUAL
  FROM ML.COMOPI_PREDICTIONS
),
marked AS (
  SELECT *,
    IFF(ACTUAL = 1 AND COALESCE(PREV_ACTUAL, 0) = 0, 1, 0) AS IS_EVENT_START
  FROM ordered
),
grouped AS (
  SELECT *,
    SUM(IS_EVENT_START) OVER (
      PARTITION BY MACHINE_KEY ORDER BY TIME_UTC
      ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS EVENT_ID
  FROM marked
  WHERE ACTUAL = 1
),
events AS (
  SELECT
    MACHINE_KEY, EVENT_ID,
    COUNT(*)       AS EVENT_WINDOWS,
    MAX(P_ALARM)   AS PEAK_PROB,
    MIN(TIME_UTC)  AS EVENT_START
  FROM grouped
  GROUP BY MACHINE_KEY, EVENT_ID
)
SELECT
  COUNT(*)                                                  AS TEST_EVENTS,
  ROUND(AVG(EVENT_WINDOWS), 2)                              AS AVG_WINDOWS_PER_EVENT,
  SUM(IFF(PEAK_PROB >= 0.30, 1, 0))                         AS CAUGHT_AT_030,
  SUM(IFF(PEAK_PROB >= 0.50, 1, 0))                         AS CAUGHT_AT_050,
  ROUND(AVG(IFF(PEAK_PROB >= 0.30, 1, 0)) * 100, 2)         AS EVENT_RECALL_030_PCT,
  ROUND(AVG(IFF(PEAK_PROB >= 0.50, 1, 0)) * 100, 2)         AS EVENT_RECALL_050_PCT
FROM events;

/* 4. Per machine, at the 0.50 threshold. A model can look fine overall while
      being useless on the machines with least data, and a fleet dashboard
      would hide that. */
SELECT
  MACHINE_CODE,
  COUNT(*)                                                       AS TEST_ROWS,
  SUM(ACTUAL)                                                    AS POSITIVES,
  ROUND(DIV0(SUM(IFF(P_ALARM >= 0.5 AND ACTUAL = 1, 1, 0)),
             SUM(IFF(P_ALARM >= 0.5, 1, 0))) * 100, 2)           AS PRECISION_PCT,
  ROUND(DIV0(SUM(IFF(P_ALARM >= 0.5 AND ACTUAL = 1, 1, 0)),
             SUM(ACTUAL)) * 100, 2)                              AS RECALL_PCT
FROM ML.COMOPI_PREDICTIONS
GROUP BY MACHINE_CODE
ORDER BY TEST_ROWS DESC;

/* 5. Does the score separate the two classes at all? If these two averages
      are close, the threshold table above is noise. */
SELECT
  ACTUAL,
  COUNT(*)                     AS ROWS_IN_CLASS,
  ROUND(AVG(P_ALARM), 4)       AS MEAN_PROB,
  ROUND(MEDIAN(P_ALARM), 4)    AS MEDIAN_PROB,
  ROUND(APPROX_PERCENTILE(P_ALARM, 0.9), 4) AS P90_PROB
FROM ML.COMOPI_PREDICTIONS
GROUP BY ACTUAL
ORDER BY ACTUAL;

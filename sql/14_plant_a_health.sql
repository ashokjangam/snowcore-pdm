/* ============================================================================
   Plant A (CoMoPI) — condition monitoring, not failure prediction.

   WHY THIS REPLACED A SUPERVISED MODEL

   The first attempt trained a classifier to predict a target-module alarm one
   hour ahead. It failed, and the failure was measured rather than assumed
   (scripts/diagnose_comopi_signal.py):

     held-out mean probability, alarm rows        0.2110
     held-out mean probability, non-alarm rows    0.2179   (inverted)
     AUC across every feature set and model       0.48 - 0.54
     AUC at horizons 10, 30, 60, 180, 360 min     0.50 - 0.53
     AUC for the CONCURRENT alarm, not forward    0.49 - 0.54
     adversarial train-vs-test AUC                0.944

   The last figure is the important one. It says a model can tell the training
   period from the test period almost perfectly, so the two periods are not
   samples of the same process. Machine E002 appears only before the cutoff and
   C003 only after, and A005's positive rate falls from 38.3% to 17.3%.

   The only genuine signal is that alarms repeat: an alarm in the current
   window lifts the next-hour alarm rate from 19.3% to 43.1%. That is
   autocorrelation, not condition monitoring, and is not worth a model.

   WHAT THIS BUILDS INSTEAD

   An unsupervised health index. For each machine, a reference period defines
   what normal looks like for that machine on each of its 16 channels. Every
   later window is scored by how far it has moved from that baseline. No labels
   are used, so none of the problems above apply.

   Robust statistics are used throughout — median and interquartile range
   rather than mean and standard deviation — because a handful of extreme
   windows would otherwise inflate the baseline spread and hide everything.

   WHAT THIS DOES AND DOES NOT CLAIM

   Claims: this window's readings differ from this machine's own established
   normal, by this much, and these named channels are responsible.

   Does not claim: that a fault is coming, or that a high score warrants
   intervention. That link cannot be established from this dataset, and query 4
   at the bottom measures how weak it is rather than hiding it. Read that
   number before presenting the index to anyone.
   ========================================================================= */

USE ROLE ACCOUNTADMIN;
USE DATABASE SNOWCORE_REAL;
USE WAREHOUSE COMPUTE_WH;
ALTER SESSION SET TIMEZONE = 'UTC';
ALTER SESSION SET QUERY_TAG = 'snowcore-real|coco|plant-a-health';

/* Remove the failed supervised attempt so nothing downstream can read it by
   mistake. Its findings live in git history and in the header above. */
DROP TABLE IF EXISTS ML.COMOPI_PREDICTIONS;
DROP VIEW  IF EXISTS ML.COMOPI_TEST_X;
DROP VIEW  IF EXISTS ML.COMOPI_TRAIN;
DROP TABLE IF EXISTS ML.COMOPI_SPLIT;
DROP TABLE IF EXISTS ML.COMOPI_FEATURES;
DROP PROCEDURE IF EXISTS ML.TRAIN_AND_SCORE_COMOPI();

/* --------------------------------------------------------------------------
   Long form. Sixteen columns become sixteen rows per window, so that every
   statistic below is written once instead of sixteen times, and so a channel
   can be added or removed without touching any arithmetic.
   -------------------------------------------------------------------------- */

CREATE OR REPLACE TABLE ML.PLANT_A_READING AS
SELECT
  MACHINE_KEY,
  MACHINE_CODE,
  TIME_UTC,
  f.KEY::STRING  AS CHANNEL,
  f.VALUE::FLOAT AS READING,
  /* A/B are the two elements performing the closure operation. Keeping the
     side separate lets the app compare one against the other. */
  LEFT(f.KEY::STRING, 1) AS ELEMENT_SIDE
FROM SILVER.COMOPI_SENSOR_10MIN,
     LATERAL FLATTEN(input => OBJECT_CONSTRUCT(
       'AE', AE, 'BE', BE, 'AF', AF, 'BF', BF,
       'APP', APP, 'BPP', BPP, 'AP', AP, 'BP', BP,
       'ALE', ALE, 'BLE', BLE, 'ALP', ALP, 'BLP', BLP,
       'ADS', ADS, 'BDS', BDS, 'AES', AES, 'BES', BES
     )) f
WHERE f.VALUE IS NOT NULL;

COMMENT ON TABLE ML.PLANT_A_READING IS
  'Plant A sensor readings in long form. Machine C004 contributes no B-side rows because it has no B-side instrumentation.';

/* --------------------------------------------------------------------------
   Baseline: each machine's first 200 sampled windows.

   Per machine, not fleet-wide, because the machines are not interchangeable
   and a fleet baseline would mark the quietest machine permanently abnormal.

   The first attempt used "the first 14 days" and that was wrong. Plant A's
   sampling is bursty, so a fixed span of clock time yields wildly different
   sample counts (scripts/check_baseline_coverage.py):

     machine  windows  in first 14 days
     B002       7,286        63
     E002       1,442        20
     C004         196        36
     A005       3,360       244

   Under that rule E002 and C004 fell below the 50-sample floor and were left
   unscored entirely, and B002 — the machine with the most history of all —
   had its baseline resting on 63 windows. Only 89.3% of windows could be
   scored. Counting windows instead of days covers 99.7%, and the only machine
   still excluded is C003, which has 46 windows in total and genuinely cannot
   support a baseline.

   200 is a choice rather than a measurement: enough for a stable median and
   interquartile range, small enough to leave the bulk of each machine's
   history available for scoring.
   -------------------------------------------------------------------------- */

CREATE OR REPLACE TABLE ML.PLANT_A_BASELINE AS
WITH ranked AS (
  SELECT
    MACHINE_KEY, CHANNEL, READING, TIME_UTC,
    DENSE_RANK() OVER (PARTITION BY MACHINE_KEY ORDER BY TIME_UTC) AS WINDOW_RANK
  FROM ML.PLANT_A_READING
),
ref AS (
  SELECT MACHINE_KEY, CHANNEL, READING
  FROM ranked
  WHERE WINDOW_RANK <= 200
),
span AS (
  SELECT
    MACHINE_KEY,
    MIN(TIME_UTC)                                       AS FIRST_SEEN,
    /* A machine with 200 windows or fewer is entirely baseline and has
       nothing left to score. C004, with 196, is in exactly that position.
       The sentinel keeps IS_SCORED_PERIOD false for all of its rows instead
       of letting a NULL comparison decide silently. */
    COALESCE(
      MIN(IFF(WINDOW_RANK > 200, TIME_UTC, NULL)),
      '9999-12-31'::TIMESTAMP_TZ
    )                                                   AS BASELINE_END
  FROM ranked
  GROUP BY MACHINE_KEY
)
SELECT
  ref.MACHINE_KEY,
  ref.CHANNEL,
  COUNT(*)                                        AS BASELINE_SAMPLES,
  MEDIAN(ref.READING)                             AS BASELINE_MEDIAN,
  APPROX_PERCENTILE(ref.READING, 0.25)            AS BASELINE_P25,
  APPROX_PERCENTILE(ref.READING, 0.75)            AS BASELINE_P75,
  /* 1.349 converts an interquartile range into the equivalent standard
     deviation for a normal distribution, so the score below reads on a
     familiar scale. The floor of 0.01 stops a channel that barely moved
     during the baseline from producing enormous scores forever after. */
  GREATEST(
    (APPROX_PERCENTILE(ref.READING, 0.75)
       - APPROX_PERCENTILE(ref.READING, 0.25)) / 1.349,
    0.01
  )                                               AS BASELINE_SCALE,
  s.FIRST_SEEN                                    AS BASELINE_START,
  s.BASELINE_END,
  'DERIVED_FROM_OBSERVED'                         AS DATA_ORIGIN
FROM ref
JOIN span s ON s.MACHINE_KEY = ref.MACHINE_KEY
GROUP BY ref.MACHINE_KEY, ref.CHANNEL, s.FIRST_SEEN, s.BASELINE_END
HAVING COUNT(*) >= 50;

COMMENT ON TABLE ML.PLANT_A_BASELINE IS
  'Per machine and channel, what normal looked like across that machine first 200 windows. Robust statistics; scale floored at 0.01. Channels with under 50 baseline samples are excluded, which removes C003 entirely.';

/* --------------------------------------------------------------------------
   Deviation per channel per window.
   -------------------------------------------------------------------------- */

CREATE OR REPLACE TABLE ML.PLANT_A_CHANNEL_DEVIATION AS
SELECT
  r.MACHINE_KEY,
  r.MACHINE_CODE,
  r.TIME_UTC,
  r.CHANNEL,
  r.ELEMENT_SIDE,
  r.READING,
  b.BASELINE_MEDIAN,
  b.BASELINE_SCALE,
  (r.READING - b.BASELINE_MEDIAN) / b.BASELINE_SCALE          AS ROBUST_Z,
  ABS((r.READING - b.BASELINE_MEDIAN) / b.BASELINE_SCALE)     AS ABS_Z,
  r.TIME_UTC >= b.BASELINE_END                                AS IS_SCORED_PERIOD,
  'DERIVED_FROM_OBSERVED'                                     AS DATA_ORIGIN
FROM ML.PLANT_A_READING r
JOIN ML.PLANT_A_BASELINE b
  ON  b.MACHINE_KEY = r.MACHINE_KEY
  AND b.CHANNEL     = r.CHANNEL;

COMMENT ON TABLE ML.PLANT_A_CHANNEL_DEVIATION IS
  'Signed and absolute robust z per channel per window. Rows inside the baseline window are kept with IS_SCORED_PERIOD false so the app can draw the reference period.';

/* --------------------------------------------------------------------------
   Health index per window.

   The window score is the mean absolute robust z across that window's
   channels, then inverted onto 0-100 where 100 is indistinguishable from
   baseline. The 6.0 divisor maps a mean deviation of six robust standard
   deviations to a health of zero; beyond that the machine is simply "as bad as
   the scale goes" and a finer distinction would be false precision.

   The worst channel is carried alongside, because a maintenance engineer needs
   to know which measurement moved, not only that something did.
   -------------------------------------------------------------------------- */

CREATE OR REPLACE TABLE ML.PLANT_A_HEALTH AS
WITH agg AS (
  SELECT
    MACHINE_KEY, MACHINE_CODE, TIME_UTC,
    COUNT(*)              AS CHANNELS_SCORED,
    AVG(ABS_Z)            AS MEAN_ABS_Z,
    MAX(ABS_Z)            AS MAX_ABS_Z,
    SUM(IFF(ABS_Z > 3, 1, 0)) AS CHANNELS_BEYOND_3Z,
    IS_SCORED_PERIOD
  FROM ML.PLANT_A_CHANNEL_DEVIATION
  GROUP BY MACHINE_KEY, MACHINE_CODE, TIME_UTC, IS_SCORED_PERIOD
),
worst AS (
  SELECT MACHINE_KEY, TIME_UTC, CHANNEL AS WORST_CHANNEL, ROBUST_Z AS WORST_Z
  FROM ML.PLANT_A_CHANNEL_DEVIATION
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY MACHINE_KEY, TIME_UTC ORDER BY ABS_Z DESC) = 1
)
SELECT
  a.MACHINE_KEY,
  a.MACHINE_CODE,
  a.TIME_UTC,
  DATE_TRUNC('day', a.TIME_UTC)                     AS HEALTH_DATE,
  a.CHANNELS_SCORED,
  ROUND(a.MEAN_ABS_Z, 4)                            AS MEAN_ABS_Z,
  ROUND(a.MAX_ABS_Z, 4)                             AS MAX_ABS_Z,
  a.CHANNELS_BEYOND_3Z,
  ROUND(GREATEST(0, 100 * (1 - a.MEAN_ABS_Z / 6.0)), 2) AS HEALTH_INDEX,
  w.WORST_CHANNEL,
  ROUND(w.WORST_Z, 4)                               AS WORST_CHANNEL_Z,
  a.IS_SCORED_PERIOD,
  'DERIVED_FROM_OBSERVED'                           AS DATA_ORIGIN
FROM agg a
JOIN worst w ON w.MACHINE_KEY = a.MACHINE_KEY AND w.TIME_UTC = a.TIME_UTC;

COMMENT ON TABLE ML.PLANT_A_HEALTH IS
  'Unsupervised health index, 100 = matches this machine own baseline, 0 = mean deviation of six robust SDs or worse. No failure labels are used and none are implied.';

/* Daily roll-up for the fleet view. */
CREATE OR REPLACE TABLE ML.PLANT_A_HEALTH_DAILY AS
SELECT
  MACHINE_KEY,
  MACHINE_CODE,
  HEALTH_DATE,
  COUNT(*)                                  AS WINDOWS,
  ROUND(AVG(HEALTH_INDEX), 2)               AS HEALTH_INDEX_AVG,
  ROUND(MIN(HEALTH_INDEX), 2)               AS HEALTH_INDEX_WORST,
  ROUND(AVG(MEAN_ABS_Z), 4)                 AS MEAN_ABS_Z,
  SUM(CHANNELS_BEYOND_3Z)                   AS CHANNEL_EXCURSIONS,
  MODE(WORST_CHANNEL)                       AS DOMINANT_CHANNEL,
  BOOLOR_AGG(IS_SCORED_PERIOD)              AS ANY_SCORED_PERIOD,
  'DERIVED_FROM_OBSERVED'                   AS DATA_ORIGIN
FROM ML.PLANT_A_HEALTH
GROUP BY MACHINE_KEY, MACHINE_CODE, HEALTH_DATE;

/* --------------------------------------------------------------------------
   Channel drift: has a channel's whole distribution moved, as opposed to one
   window being odd? This is the effect that produced the 0.944 adversarial
   AUC, expressed in a form an engineer can act on.
   -------------------------------------------------------------------------- */

CREATE OR REPLACE TABLE ML.PLANT_A_CHANNEL_DRIFT AS
WITH monthly AS (
  SELECT
    MACHINE_KEY, MACHINE_CODE, CHANNEL,
    DATE_TRUNC('month', TIME_UTC)        AS DRIFT_MONTH,
    COUNT(*)                             AS SAMPLES,
    MEDIAN(READING)                      AS MONTH_MEDIAN,
    AVG(ROBUST_Z)                        AS MEAN_SIGNED_Z,
    ANY_VALUE(BASELINE_MEDIAN)           AS BASELINE_MEDIAN
  FROM ML.PLANT_A_CHANNEL_DEVIATION
  GROUP BY MACHINE_KEY, MACHINE_CODE, CHANNEL, DATE_TRUNC('month', TIME_UTC)
)
SELECT
  *,
  ROUND(MONTH_MEDIAN - BASELINE_MEDIAN, 4)  AS MEDIAN_SHIFT,
  /* A sustained signed z beyond 2 is a distribution that has moved, not noise.
     Unsigned excursions are already covered by the health index. */
  ABS(MEAN_SIGNED_Z) > 2                    AS IS_DRIFTED,
  'DERIVED_FROM_OBSERVED'                   AS DATA_ORIGIN
FROM monthly
WHERE SAMPLES >= 30;

COMMENT ON TABLE ML.PLANT_A_CHANNEL_DRIFT IS
  'Per channel per month, how far the whole distribution has moved from baseline. Months with under 30 samples are dropped as too thin to judge.';

/* ==========================================================================
   Verification.
   ========================================================================== */

/* 1. Shape. PLANT_A_READING should be under 8 * 15,704 because machine C004
      contributes no B-side rows. HEALTH should be at most 15,704. */
SELECT 'PLANT_A_READING'           AS OBJECT, COUNT(*) AS ROW_COUNT FROM ML.PLANT_A_READING
UNION ALL SELECT 'PLANT_A_BASELINE',          COUNT(*) FROM ML.PLANT_A_BASELINE
UNION ALL SELECT 'PLANT_A_CHANNEL_DEVIATION', COUNT(*) FROM ML.PLANT_A_CHANNEL_DEVIATION
UNION ALL SELECT 'PLANT_A_HEALTH',            COUNT(*) FROM ML.PLANT_A_HEALTH
UNION ALL SELECT 'PLANT_A_HEALTH_DAILY',      COUNT(*) FROM ML.PLANT_A_HEALTH_DAILY
UNION ALL SELECT 'PLANT_A_CHANNEL_DRIFT',     COUNT(*) FROM ML.PLANT_A_CHANNEL_DRIFT;

/* 2. Baseline coverage per machine. Expect 7 of the 8 machines; C003 has 46
      windows in total and is correctly absent. Any machine missing here must
      be shown as "not assessed" in the app rather than as healthy. */
SELECT
  b.MACHINE_KEY,
  COUNT(DISTINCT b.CHANNEL)      AS CHANNELS_WITH_BASELINE,
  MIN(b.BASELINE_SAMPLES)        AS MIN_BASELINE_SAMPLES,
  ANY_VALUE(b.BASELINE_START)    AS BASELINE_START,
  ANY_VALUE(b.BASELINE_END)      AS BASELINE_END
FROM ML.PLANT_A_BASELINE b
GROUP BY b.MACHINE_KEY
ORDER BY b.MACHINE_KEY;

/* 3. Sanity: inside its own baseline window a machine should score near 100.
      If BASELINE_PERIOD_HEALTH is not clearly higher than SCORED_PERIOD_HEALTH,
      the baseline is not describing normal and the index means nothing.

      C004 has 196 windows, all of them baseline, so its SCORED_PERIOD_HEALTH
      is expected to be NULL rather than zero. */
SELECT
  MACHINE_CODE,
  ROUND(AVG(IFF(NOT IS_SCORED_PERIOD, HEALTH_INDEX, NULL)), 2) AS BASELINE_PERIOD_HEALTH,
  ROUND(AVG(IFF(IS_SCORED_PERIOD, HEALTH_INDEX, NULL)), 2)     AS SCORED_PERIOD_HEALTH,
  COUNT(*)                                                     AS WINDOWS
FROM ML.PLANT_A_HEALTH
GROUP BY MACHINE_CODE
ORDER BY MACHINE_CODE;

/* 4. The honest check, and the one that must not be skipped.

      Do low-health windows actually precede module alarms? The supervised work
      says they should not, and this quantifies by how little. If ALARM_RATE is
      flat across health deciles, the index measures deviation from normal and
      nothing more — which is still a legitimate condition-monitoring output,
      but it must be presented as that and never as a failure forecast. */
WITH scored AS (
  SELECT
    h.MACHINE_KEY, h.TIME_UTC, h.HEALTH_INDEX,
    NTILE(10) OVER (ORDER BY h.HEALTH_INDEX) AS HEALTH_DECILE
  FROM ML.PLANT_A_HEALTH h
  WHERE h.IS_SCORED_PERIOD
),
labelled AS (
  SELECT
    s.HEALTH_DECILE,
    s.HEALTH_INDEX,
    MAX(IFF(a.IS_MODULE_ALARM, 1, 0)) AS ALARM_NEXT_60M
  FROM scored s
  LEFT JOIN SILVER.COMOPI_ALARM_10MIN a
    ON  a.MACHINE_KEY = s.MACHINE_KEY
    AND a.TIME_UTC    > s.TIME_UTC
    AND a.TIME_UTC   <= DATEADD('minute', 60, s.TIME_UTC)
  GROUP BY s.HEALTH_DECILE, s.HEALTH_INDEX, s.MACHINE_KEY, s.TIME_UTC
)
SELECT
  HEALTH_DECILE,
  COUNT(*)                                  AS WINDOWS,
  ROUND(AVG(HEALTH_INDEX), 2)               AS AVG_HEALTH,
  SUM(ALARM_NEXT_60M)                       AS ALARMS_FOLLOWED,
  ROUND(AVG(ALARM_NEXT_60M) * 100, 2)       AS ALARM_RATE_PCT
FROM labelled
GROUP BY HEALTH_DECILE
ORDER BY HEALTH_DECILE;

/* 5. Which channels drifted, and when. This is the Plant A story: not
      "machine will fail" but "these measurements no longer resemble how this
      machine behaved when we started watching it". */
SELECT
  MACHINE_CODE,
  CHANNEL,
  COUNT(*)                                   AS MONTHS_OBSERVED,
  SUM(IFF(IS_DRIFTED, 1, 0))                 AS MONTHS_DRIFTED,
  ROUND(MIN(MEAN_SIGNED_Z), 3)               AS MOST_NEGATIVE_Z,
  ROUND(MAX(MEAN_SIGNED_Z), 3)               AS MOST_POSITIVE_Z
FROM ML.PLANT_A_CHANNEL_DRIFT
GROUP BY MACHINE_CODE, CHANNEL
HAVING SUM(IFF(IS_DRIFTED, 1, 0)) > 0
ORDER BY MONTHS_DRIFTED DESC, MACHINE_CODE, CHANNEL
LIMIT 25;

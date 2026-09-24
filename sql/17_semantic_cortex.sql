/* ============================================================================
   Presentation views, a semantic view for Cortex Analyst, and Cortex-written
   narrative.

   THE ONE RULE THIS LAYER ENFORCES

   Nothing above this point lets a caller mix the two plants, and nothing here
   introduces that ability. Plant A and Plant B are separate factories with no
   published relationship. Every view below carries PLANT_CODE and every
   measure is defined so that it is only ever aggregated within a plant.

   PROVENANCE TRAVELS WITH THE NUMBER

   Each presentation view exposes DATA_ORIGIN so the application can badge a
   figure without having to remember where it came from:

     OBSERVED               published by the dataset author
     DERIVED_FROM_OBSERVED  computed by us from published values only
     SYNTHETIC_IT           invented by us; work orders, technicians, costs

   WHICH CORTEX MODELS ARE USED AND WHY

   docs/cortex-audit/009-capability-check-result.md measured what this account
   can actually call. Working: llama3.3-70b, llama3.1-70b, llama3.1-8b,
   mistral-7b. Not working: every Claude model and the Mistral-large family,
   all reported as legacy or deprecated in this region. llama3.3-70b is used
   for narrative and llama3.1-8b for short classification work, because paying
   70b prices to bucket a stop reason is waste.

   Narrative generation is deliberately bounded. It runs over aggregates —
   tens of rows — not over the 5,103 work orders or the 45,625 OEE hours. An
   LLM call per fact row would cost real credits to produce text nobody reads.
   ========================================================================= */

USE ROLE ACCOUNTADMIN;
USE DATABASE SNOWCORE_REAL;
USE WAREHOUSE COMPUTE_WH;
ALTER SESSION SET TIMEZONE = 'UTC';
ALTER SESSION SET QUERY_TAG = 'snowcore-real|coco|semantic';

/* ==========================================================================
   1. Presentation views.
   ========================================================================== */

/* Fleet roster across both plants, with what each machine can and cannot
   report. The app uses CAPABILITY_NOTE to decide which panels to grey out
   rather than showing an empty chart. */
CREATE OR REPLACE VIEW GOLD.V_FLEET AS
SELECT
  m.PLANT_CODE,
  p.PLANT_LABEL,
  p.PLANT_ROLE,
  m.MACHINE_KEY,
  m.MACHINE_CODE,
  m.FIRST_SEEN,
  m.LAST_SEEN,
  m.SENSOR_WINDOWS                                      AS SOURCE_ROWS,
  p.SOURCE_DOI,
  p.SOURCE_LICENSE,
  CASE m.PLANT_CODE
    WHEN 'PLANT_B' THEN 'OEE, downtime and stop-risk available. No analogue sensors exist for this plant.'
    ELSE 'Condition monitoring available. No production counts exist, so OEE and lost-output cost cannot be computed.'
  END                                                   AS CAPABILITY_NOTE,
  'OBSERVED'                                            AS DATA_ORIGIN
FROM SILVER.DIM_MACHINE m
JOIN SILVER.DIM_PLANT p USING (PLANT_CODE);

/* Plant B daily OEE, renamed for humans and with the loss breakdown that
   makes A, P and Q actionable rather than merely reported. */
CREATE OR REPLACE VIEW GOLD.V_OEE_DAILY AS
SELECT
  PLANT_CODE,
  MACHINE_KEY,
  MACHINE_CODE,
  OEE_DATE,
  HOURS_OBSERVED,
  ROUND(PLANNED_SEC / 3600.0, 2)                        AS PLANNED_HOURS,
  ROUND(RUN_SEC / 3600.0, 2)                            AS RUN_HOURS,
  ROUND(DOWNTIME_SEC / 3600.0, 2)                       AS UNPLANNED_DOWN_HOURS,
  ROUND(IDLE_SEC / 3600.0, 2)                           AS IDLE_HOURS,
  ROUND(SLOW_SEC / 3600.0, 2)                           AS SLOW_RUNNING_HOURS,
  ROUND(PLANNED_STOP_SEC / 3600.0, 2)                   AS PLANNED_STOP_HOURS,
  PACKAGES_IN,
  PACKAGES_OUT,
  THEORETICAL_PACKAGES,
  ROUND(AVAILABILITY, 4)                                AS AVAILABILITY,
  ROUND(PERFORMANCE, 4)                                 AS PERFORMANCE,
  ROUND(QUALITY, 4)                                     AS QUALITY,
  ROUND(OEE, 4)                                         AS OEE,
  QUALITY_CLAMPED,
  /* Which of the three terms is costing the most. Stated as the gap from a
     perfect 1.0, because that is what an improvement effort would close. */
  CASE
    WHEN AVAILABILITY IS NULL THEN NULL
    WHEN (1 - AVAILABILITY) >= (1 - PERFORMANCE)
     AND (1 - AVAILABILITY) >= (1 - QUALITY)     THEN 'AVAILABILITY'
    WHEN (1 - PERFORMANCE)  >= (1 - QUALITY)     THEN 'PERFORMANCE'
    ELSE 'QUALITY'
  END                                                   AS BIGGEST_LOSS,
  ROUND(THEORETICAL_PACKAGES - PACKAGES_OUT, 0)         AS PACKAGES_FORGONE,
  DATA_ORIGIN
FROM GOLD.PIADE_OEE_DAILY;

/* The single canonical OEE number per plant and per machine.

   This view exists because there are three defensible ways to state a
   plant-level OEE and they disagree badly on this data: the mean of hourly
   ratios gives 57.1%, the mean of daily ratios gives 43.2%, and recomputing
   from summed seconds and packages gives a third figure. Only the last is
   correct, because averaging ratios weights a quiet hour the same as a busy
   one. Every part of the application reads this view so that one number
   appears everywhere. */
CREATE OR REPLACE VIEW GOLD.V_OEE_ROLLUP AS
SELECT
  PLANT_CODE,
  MACHINE_CODE,
  MIN(OEE_DATE)                                                   AS FROM_DATE,
  MAX(OEE_DATE)                                                   AS TO_DATE,
  COUNT(*)                                                        AS DAYS_OBSERVED,
  ROUND(SUM(PLANNED_SEC) / 3600.0, 1)                             AS PLANNED_HOURS,
  ROUND(SUM(RUN_SEC) / 3600.0, 1)                                 AS RUN_HOURS,
  ROUND(SUM(DOWNTIME_SEC) / 3600.0, 1)                            AS BREAKDOWN_HOURS,
  ROUND(SUM(IDLE_SEC) / 3600.0, 1)                                AS IDLE_HOURS,
  ROUND(SUM(SLOW_SEC) / 3600.0, 1)                                AS SLOW_RUNNING_HOURS,
  SUM(PACKAGES_OUT)                                               AS PACKAGES_OUT,
  /* Weighted, not averaged. */
  ROUND(SUM(RUN_SEC) / NULLIF(SUM(PLANNED_SEC), 0), 4)            AS AVAILABILITY,
  ROUND(SUM(PACKAGES_OUT) / NULLIF(SUM(THEORETICAL_PACKAGES), 0), 4) AS PERFORMANCE,
  ROUND(SUM(PACKAGES_OUT) / NULLIF(SUM(PACKAGES_IN), 0), 4)       AS QUALITY,
  ROUND(
      (SUM(RUN_SEC) / NULLIF(SUM(PLANNED_SEC), 0))
    * (SUM(PACKAGES_OUT) / NULLIF(SUM(THEORETICAL_PACKAGES), 0))
    * (SUM(PACKAGES_OUT) / NULLIF(SUM(PACKAGES_IN), 0)), 4)       AS OEE,
  'DERIVED_FROM_OBSERVED'                                         AS DATA_ORIGIN
FROM GOLD.PIADE_OEE_DAILY
GROUP BY ROLLUP (PLANT_CODE, MACHINE_CODE)
HAVING PLANT_CODE IS NOT NULL;

/* Downtime Pareto per plant, split by whether the machine was faulted or
   merely waiting.

   The first version of this view mapped alarm code A_000 to 'UNDIAGNOSED',
   which produced a top line of 10,266 hours of apparently unexplained
   breakdown and was wrong. scripts/probe_stop_state_alarm.py established that
   the absence of an alarm coincides exactly with the 'idle' state: all 92,084
   downtime intervals carry a code and all 50,149 idle intervals carry none.
   Those hours were never undiagnosed failures. The line was available and
   waiting, which is a planning problem rather than a maintenance one, and it
   is labelled as such here. */
CREATE OR REPLACE VIEW GOLD.V_DOWNTIME_PARETO AS
WITH stops AS (
  SELECT
    PLANT_CODE,
    MACHINE_CODE,
    IFF(STOP_STATE = 'idle', 'IDLE_NO_ALARM', ALARM_CODE) AS CAUSE_CODE,
    IFF(STOP_STATE = 'idle', 'WAITING', 'FAULTED')        AS LOSS_NATURE,
    IFF(STOP_STATE = 'idle', 'PLANNING', 'MAINTENANCE')   AS OWNING_FUNCTION,
    STOP_DURATION_MIN
  FROM GOLD.PIADE_DOWNTIME_EVENT
)
SELECT
  PLANT_CODE,
  CAUSE_CODE,
  LOSS_NATURE,
  OWNING_FUNCTION,
  COUNT(*)                                              AS STOP_COUNT,
  ROUND(SUM(STOP_DURATION_MIN) / 60.0, 1)               AS STOP_HOURS,
  ROUND(MEDIAN(STOP_DURATION_MIN), 1)                   AS MEDIAN_STOP_MIN,
  ROUND(MAX(STOP_DURATION_MIN), 1)                      AS LONGEST_STOP_MIN,
  COUNT(DISTINCT MACHINE_CODE)                          AS MACHINES_AFFECTED,
  ROUND(100.0 * SUM(STOP_DURATION_MIN)
        / SUM(SUM(STOP_DURATION_MIN)) OVER (PARTITION BY PLANT_CODE), 2)
                                                        AS PCT_OF_STOP_TIME,
  ROUND(100.0 * SUM(SUM(STOP_DURATION_MIN)) OVER (
          PARTITION BY PLANT_CODE ORDER BY SUM(STOP_DURATION_MIN) DESC
          ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
        / SUM(SUM(STOP_DURATION_MIN)) OVER (PARTITION BY PLANT_CODE), 2)
                                                        AS CUMULATIVE_PCT,
  /* A short-and-frequent cause needs a different response from a rare-and-long
     one. This is a deterministic rule rather than an LLM call: the first
     attempt asked llama3.1-8b to make this judgement and it returned the same
     label for all 19 causes, which is worse than a threshold and costs money.
     Language models are used in this build for writing prose, not for
     bucketing two numbers. */
  CASE
    WHEN COUNT(*) >= 5000 AND MEDIAN(STOP_DURATION_MIN) < 5  THEN 'CHRONIC_SHORT'
    WHEN COUNT(*) <  200  AND MEDIAN(STOP_DURATION_MIN) >= 30 THEN 'RARE_MAJOR'
    WHEN MEDIAN(STOP_DURATION_MIN) >= 10                      THEN 'OCCASIONAL_LONG'
    ELSE 'INTERMITTENT'
  END                                                   AS STOP_PATTERN,
  'OBSERVED'                                            AS DATA_ORIGIN
FROM stops
GROUP BY PLANT_CODE, CAUSE_CODE, LOSS_NATURE, OWNING_FUNCTION;

/* Money, per machine, with maintenance and idle kept apart.

   Keeping them in separate columns rather than one total is the whole point.
   A single TOTAL_COST would put the idle bill in the maintenance manager's
   lap, and on Plant B the idle bill is the larger of the two by an order of
   magnitude. */
CREATE OR REPLACE VIEW GOLD.V_COST_BY_MACHINE AS
WITH maint AS (
  SELECT
    PLANT_CODE,
    MACHINE_CODE,
    COUNT(*)                                            AS WORK_ORDERS,
    ROUND(SUM(SOURCE_EVENT_MINUTES) / 60.0, 1)          AS BREAKDOWN_HOURS,
    ROUND(SUM(LABOUR_COST), 2)                          AS LABOUR_COST,
    ROUND(SUM(PARTS_COST), 2)                           AS PARTS_COST,
    ROUND(SUM(LOST_PRODUCTION_COST), 2)                 AS BREAKDOWN_FORGONE_MARGIN,
    ROUND(SUM(TOTAL_COST), 2)                           AS MAINTENANCE_COST,
    ROUND(AVG(TOTAL_COST), 2)                           AS AVG_COST_PER_ORDER,
    ANY_VALUE(COST_LIMITATION)                          AS COST_LIMITATION
  FROM GOLD.WORK_ORDER
  GROUP BY PLANT_CODE, MACHINE_CODE
),
idle AS (
  SELECT
    PLANT_CODE,
    MACHINE_CODE,
    COUNT(*)                                            AS IDLE_INCIDENTS,
    ROUND(SUM(LOSS_MINUTES) / 60.0, 1)                  AS IDLE_HOURS,
    ROUND(SUM(FORGONE_MARGIN), 2)                       AS IDLE_FORGONE_MARGIN
  FROM GOLD.PRODUCTION_LOSS_INCIDENT
  GROUP BY PLANT_CODE, MACHINE_CODE
)
SELECT
  m.PLANT_CODE,
  m.MACHINE_CODE,
  m.WORK_ORDERS,
  m.BREAKDOWN_HOURS,
  m.LABOUR_COST,
  m.PARTS_COST,
  m.BREAKDOWN_FORGONE_MARGIN,
  m.MAINTENANCE_COST,
  m.AVG_COST_PER_ORDER,
  COALESCE(i.IDLE_INCIDENTS, 0)                         AS IDLE_INCIDENTS,
  COALESCE(i.IDLE_HOURS, 0)                             AS IDLE_HOURS,
  i.IDLE_FORGONE_MARGIN,
  /* How much of this machine's attributed money is waiting rather than
     repairing. NULL for Plant A, which has no idle records and no output. */
  ROUND(100.0 * DIV0(
    COALESCE(i.IDLE_FORGONE_MARGIN, 0),
    m.MAINTENANCE_COST + COALESCE(i.IDLE_FORGONE_MARGIN, 0)), 2)
                                                        AS PCT_COST_FROM_IDLING,
  m.COST_LIMITATION,
  'SYNTHETIC_IT'                                        AS DATA_ORIGIN
FROM maint m
LEFT JOIN idle i
  ON  i.PLANT_CODE   = m.PLANT_CODE
  AND i.MACHINE_CODE = m.MACHINE_CODE;

/* Plant A condition monitoring, with the honesty note attached to the data
   rather than left in a document nobody opens. */
CREATE OR REPLACE VIEW GOLD.V_PLANT_A_HEALTH AS
SELECT
  'PLANT_A'                                             AS PLANT_CODE,
  h.MACHINE_CODE,
  h.HEALTH_DATE,
  h.WINDOWS,
  h.HEALTH_INDEX_AVG,
  h.HEALTH_INDEX_WORST,
  h.MEAN_ABS_Z,
  h.CHANNEL_EXCURSIONS,
  h.DOMINANT_CHANNEL,
  h.ANY_SCORED_PERIOD,
  'Deviation from this machine own baseline. Measured to have no relationship to subsequent alarms: 21.2% alarm rate at worst health against 17.7% at best.'
                                                        AS INTERPRETATION_LIMIT,
  h.DATA_ORIGIN
FROM ML.PLANT_A_HEALTH_DAILY h;

/* Plant B stop risk, joined to the metrics that say how much to trust it. */
CREATE OR REPLACE VIEW GOLD.V_PLANT_B_RISK AS
SELECT
  'PLANT_B'                                             AS PLANT_CODE,
  r.MACHINE_CODE,
  r.HOUR_TS,
  TO_DATE(r.HOUR_TS)                                    AS RISK_DATE,
  ROUND(r.RISK_SCORE, 4)                                AS RISK_SCORE,
  r.RISK_BAND,
  r.IS_FLAGGED,
  r.LABEL_HEAVY_STOP                                    AS ACTUAL_HEAVY_STOP,
  ROUND(r.NEXT_HOUR_DOWNTIME * 100, 2)                  AS ACTUAL_NEXT_HOUR_DOWNTIME_PCT,
  ROUND(m.AUC, 4)                                       AS MODEL_AUC_THIS_MACHINE,
  ROUND(m.TOP_DECILE_PRECISION * 100, 2)                AS MODEL_PRECISION_PCT,
  ROUND(m.BASELINE_TOP_DECILE_PRECISION * 100, 2)       AS BASELINE_PRECISION_PCT,
  ROUND(m.BASE_RATE * 100, 2)                           AS BASE_RATE_PCT,
  m.BASELINE_TOP_DECILE_PRECISION > m.TOP_DECILE_PRECISION AS MODEL_LOSES_TO_BASELINE,
  r.DATA_ORIGIN
FROM ML.PLANT_B_RISK_SCORE r
LEFT JOIN ML.PLANT_B_MODEL_METRICS m ON m.SCOPE = r.MACHINE_CODE;

/* One place the app can read to state what it is and is not claiming. */
CREATE OR REPLACE VIEW GOLD.V_PROVENANCE AS
SELECT 'PLANT_A' AS PLANT_CODE, 'Sensor readings'        AS SUBJECT, 'OBSERVED' AS DATA_ORIGIN,
       'CoMoPI, DOI 10.5281/zenodo.7572501, CC BY 4.0'   AS SOURCE,
       'Sixteen channels, anonymised and rescaled to [0,1]. Physical units are not recoverable.' AS NOTE
UNION ALL SELECT 'PLANT_A', 'Alarm counts', 'OBSERVED',
       'CoMoPI, DOI 10.5281/zenodo.7572501, CC BY 4.0',
       'Alarm codes are anonymised. The published fault target AL_53/AL_54 appears in only 41 windows and is too rare to model.'
UNION ALL SELECT 'PLANT_A', 'Health index', 'DERIVED_FROM_OBSERVED',
       'Computed here from CoMoPI sensors only',
       'Robust deviation from each machine first 200 windows. Not validated against failures, because the data does not support that.'
UNION ALL SELECT 'PLANT_B', 'Production intervals', 'OBSERVED',
       'PIADE, DOI 10.5281/zenodo.7071747, CC BY 4.0',
       'State, alarm, duration, cumulative package counters and speed per interval.'
UNION ALL SELECT 'PLANT_B', 'OEE', 'DERIVED_FROM_OBSERVED',
       'Computed here from PIADE intervals only',
       'Availability x Performance x Quality from published columns. Ideal rate is each machine best demonstrated speed, not a vendor specification.'
UNION ALL SELECT 'PLANT_B', 'Stop risk', 'DERIVED_FROM_OBSERVED',
       'Computed here from PIADE hourly aggregates only',
       'Chronological holdout. Top-decile precision 67.6% against a 40.3% base rate and a 55.7% do-nothing baseline. Feature importance is dominated by recent downtime, so this is a smoothed persistence rule.'
UNION ALL SELECT 'BOTH', 'Work orders, technicians, costs', 'SYNTHETIC_IT',
       'Generated here from each plant own events',
       'Invented. Anchored one-to-one to real events, never blended across plants, deterministic from a fixed seed. Rates and margins are chosen and have no basis in either source.';

/* ==========================================================================
   2. Semantic view for Cortex Analyst.

   Kept to Plant B's OEE and cost, because that is where a natural-language
   question has a well-defined answer. Plant A has no production measures and
   inviting free-form questions about it would produce confident nonsense.
   ========================================================================== */

CREATE OR REPLACE SEMANTIC VIEW GOLD.SEM_SNOWCORE_OEE

  TABLES (
    oee AS GOLD.PIADE_OEE_DAILY
      PRIMARY KEY (MACHINE_KEY, OEE_DATE)
      WITH SYNONYMS ('oee', 'overall equipment effectiveness', 'line performance')
      COMMENT = 'Plant B daily OEE, derived from published production intervals.',

    machine AS SILVER.DIM_MACHINE
      PRIMARY KEY (MACHINE_KEY)
      WITH SYNONYMS ('machine', 'equipment', 'asset', 'line')
      COMMENT = 'Machines across both plants. Codes are publisher-assigned mock identifiers.',

    wo AS GOLD.WORK_ORDER
      PRIMARY KEY (WORK_ORDER_ID)
      WITH SYNONYMS ('work order', 'ticket', 'maintenance job', 'repair')
      COMMENT = 'SYNTHETIC maintenance records. Invented, but anchored to real observed events.'
  )

  RELATIONSHIPS (
    oee_to_machine AS oee (MACHINE_KEY) REFERENCES machine,
    wo_to_machine  AS wo  (MACHINE_KEY) REFERENCES machine
  )

  FACTS (
    oee.run_seconds       AS RUN_SEC,
    oee.planned_seconds   AS PLANNED_SEC,
    oee.downtime_seconds  AS DOWNTIME_SEC,
    oee.packages_out      AS PACKAGES_OUT,
    oee.packages_in       AS PACKAGES_IN,
    oee.theoretical_packages AS THEORETICAL_PACKAGES,
    wo.total_cost         AS TOTAL_COST,
    wo.labour_cost        AS LABOUR_COST,
    wo.parts_cost         AS PARTS_COST,
    wo.event_minutes      AS SOURCE_EVENT_MINUTES
  )

  DIMENSIONS (
    oee.oee_date          AS OEE_DATE
      WITH SYNONYMS ('date', 'day') COMMENT = 'Production day, UTC.',
    oee.plant             AS PLANT_CODE
      WITH SYNONYMS ('plant', 'site', 'factory')
      COMMENT = 'PLANT_A and PLANT_B are different factories and must never be combined.',
    machine.machine_code  AS MACHINE_CODE
      WITH SYNONYMS ('machine name', 'equipment id'),
    machine.plant_code    AS PLANT_CODE,
    wo.priority           AS PRIORITY
      WITH SYNONYMS ('urgency', 'severity') COMMENT = 'P1 is the longest stop band, P4 the shortest.',
    wo.cause_code         AS CAUSE_CODE
      WITH SYNONYMS ('cause', 'stop reason', 'alarm')
      COMMENT = 'UNDIAGNOSED means the source recorded no alarm for the stop, which covers most of Plant B long stops.',
    wo.technician         AS TECH_NAME
      WITH SYNONYMS ('technician', 'engineer') COMMENT = 'Invented staff name.'
  )

  METRICS (
    /* Ratios are recomputed from summed seconds and counts, never averaged
       from daily ratios, so that a week's Availability is not the mean of
       seven fractions with different denominators. */
    oee.availability  AS SUM(oee.run_seconds) / NULLIF(SUM(oee.planned_seconds), 0)
      WITH SYNONYMS ('availability', 'uptime')
      COMMENT = 'Run time over planned production time.',
    oee.performance   AS SUM(oee.packages_out) / NULLIF(SUM(oee.theoretical_packages), 0)
      WITH SYNONYMS ('performance', 'speed loss')
      COMMENT = 'Actual output over what the best demonstrated rate would have produced in the run time.',
    oee.quality       AS SUM(oee.packages_out) / NULLIF(SUM(oee.packages_in), 0)
      WITH SYNONYMS ('quality', 'yield')
      COMMENT = 'Packages out over packages in. A throughput yield, not a laboratory inspection result.',
    oee.oee_pct       AS (SUM(oee.run_seconds) / NULLIF(SUM(oee.planned_seconds), 0))
                       * (SUM(oee.packages_out) / NULLIF(SUM(oee.theoretical_packages), 0))
                       * (SUM(oee.packages_out) / NULLIF(SUM(oee.packages_in), 0))
      WITH SYNONYMS ('oee', 'overall equipment effectiveness'),
    oee.downtime_hours AS SUM(oee.downtime_seconds) / 3600
      WITH SYNONYMS ('downtime', 'unplanned downtime', 'lost hours'),
    oee.good_packages  AS SUM(oee.packages_out)
      WITH SYNONYMS ('output', 'good count', 'packages produced'),
    wo.maintenance_cost AS SUM(wo.total_cost)
      WITH SYNONYMS ('cost', 'maintenance cost', 'spend')
      COMMENT = 'SYNTHETIC. Rests on chosen labour rates and margins, not on any published figure.',
    wo.order_count      AS COUNT(wo.WORK_ORDER_ID)
      WITH SYNONYMS ('work orders', 'tickets', 'jobs')
  )

  COMMENT = 'Plant B OEE and its synthetic maintenance cost. Plant A is deliberately excluded because it publishes no production counts.';

/* ==========================================================================
   3. Cortex-written narrative.

   Bounded by design: the input is a handful of aggregate rows, not the fact
   tables. Every prompt states which figures are synthetic, because a model
   given only numbers will describe invented costs as though they were
   measured.
   ========================================================================== */

CREATE OR REPLACE TABLE GOLD.CORTEX_BRIEFING AS
WITH plant_b_facts AS (
  /* Read from the rollup, so the narrative quotes the same OEE the rest of
     the application shows rather than a mean of ratios. */
  SELECT
    ROUND(OEE * 100, 1)                                         AS OEE_PCT,
    ROUND(AVAILABILITY * 100, 1)                                AS AVAIL_PCT,
    ROUND(PERFORMANCE * 100, 1)                                 AS PERF_PCT,
    ROUND(QUALITY * 100, 1)                                     AS QUAL_PCT,
    BREAKDOWN_HOURS,
    IDLE_HOURS,
    SLOW_RUNNING_HOURS
  FROM GOLD.V_OEE_ROLLUP
  WHERE PLANT_CODE = 'PLANT_B' AND MACHINE_CODE IS NULL
),
plant_b_cost AS (
  SELECT
    ROUND(SUM(MAINTENANCE_COST), 0)                             AS MAINT_COST,
    ROUND(SUM(IDLE_FORGONE_MARGIN), 0)                          AS IDLE_COST,
    ROUND(SUM(IDLE_HOURS), 0)                                   AS IDLE_HOURS,
    ROUND(SUM(BREAKDOWN_HOURS), 0)                              AS BREAKDOWN_HOURS
  FROM GOLD.V_COST_BY_MACHINE WHERE PLANT_CODE = 'PLANT_B'
),
plant_a_facts AS (
  SELECT
    COUNT(DISTINCT MACHINE_CODE)                                AS MACHINES,
    ROUND(AVG(HEALTH_INDEX_AVG), 1)                             AS AVG_HEALTH,
    ROUND(MIN(HEALTH_INDEX_WORST), 1)                           AS WORST_HEALTH,
    MODE(DOMINANT_CHANNEL)                                      AS DOMINANT_CHANNEL
  FROM GOLD.V_PLANT_A_HEALTH
),
model AS (
  SELECT
    ROUND(TOP_DECILE_PRECISION * 100, 1)                        AS PRECISION_PCT,
    ROUND(BASE_RATE * 100, 1)                                   AS BASE_RATE_PCT,
    ROUND(BASELINE_TOP_DECILE_PRECISION * 100, 1)               AS BASELINE_PCT,
    ROUND(AUC, 3)                                               AS AUC
  FROM ML.PLANT_B_MODEL_METRICS WHERE SCOPE = 'FLEET'
)
SELECT
  'PLANT_B_OEE' AS BRIEFING_KEY,
  SNOWFLAKE.CORTEX.COMPLETE('llama3.3-70b',
    'You are writing three sentences for a plant manager. Use only these figures and invent nothing. '
    || 'Do not use bullet points or headings. State the OEE, name which of the three terms is losing the most, '
    || 'and separate idle hours from breakdown hours because they have different owners: idle time means the '
    || 'machine was available and waiting, breakdown time means it was faulted. '
    || 'Figures: OEE ' || f.OEE_PCT::VARCHAR || '%, Availability ' || f.AVAIL_PCT::VARCHAR
    || '%, Performance ' || f.PERF_PCT::VARCHAR || '%, Quality ' || f.QUAL_PCT::VARCHAR
    || '%. Hours lost: ' || f.IDLE_HOURS::VARCHAR || ' idle, '
    || f.BREAKDOWN_HOURS::VARCHAR || ' breakdown, '
    || f.SLOW_RUNNING_HOURS::VARCHAR || ' running below rate.'
  ) AS NARRATIVE,
  'DERIVED_FROM_OBSERVED' AS INPUT_ORIGIN,
  'llama3.3-70b'          AS MODEL_USED,
  CURRENT_TIMESTAMP()     AS GENERATED_AT
FROM plant_b_facts f

UNION ALL
SELECT
  'PLANT_B_COST',
  SNOWFLAKE.CORTEX.COMPLETE('llama3.3-70b',
    'Write four sentences for a plant manager. These cost figures are SYNTHETIC, generated from real stop '
    || 'durations using assumed labour rates and an assumed contribution margin. Say so explicitly in your first '
    || 'sentence. Then make the central point: the idle cost is not a maintenance problem. Every recorded '
    || 'breakdown on this line carries an alarm code and every idle period carries none, so the idle hours are '
    || 'a line that was available and waiting, not an unexplained failure. Say who should own each number: '
    || 'maintenance owns the breakdown cost, planning owns the idle cost. No bullet points. '
    || 'Figures: attributed maintenance cost ' || c.MAINT_COST::VARCHAR || ' EUR across '
    || c.BREAKDOWN_HOURS::VARCHAR || ' breakdown hours; forgone margin from idling '
    || c.IDLE_COST::VARCHAR || ' EUR across ' || c.IDLE_HOURS::VARCHAR || ' idle hours.'
  ),
  'SYNTHETIC_IT',
  'llama3.3-70b',
  CURRENT_TIMESTAMP()
FROM plant_b_cost c

UNION ALL
SELECT
  'PLANT_B_MODEL',
  SNOWFLAKE.CORTEX.COMPLETE('llama3.3-70b',
    'Write three sentences describing how much to trust a stop-risk model, for a reader who will act on it. '
    || 'Be sceptical rather than promotional. The honest comparison is the model against the do-nothing baseline, '
    || 'not against the base rate. No bullet points. '
    || 'Figures: flagging the riskiest 10% of hours gives ' || m.PRECISION_PCT
    || '% precision; the base rate is ' || m.BASE_RATE_PCT
    || '%; a trivial rule of "this hour already had downtime" gives ' || m.BASELINE_PCT
    || '%; AUC is ' || m.AUC || '. Feature importance is dominated by 24-hour rolling downtime.'
  ),
  'DERIVED_FROM_OBSERVED',
  'llama3.3-70b',
  CURRENT_TIMESTAMP()
FROM model m

UNION ALL
SELECT
  'PLANT_A_HEALTH',
  SNOWFLAKE.CORTEX.COMPLETE('llama3.3-70b',
    'Write three sentences about a condition-monitoring index for a maintenance engineer. It measures how far a '
    || 'machine has moved from its own early-life baseline across sixteen anonymised sensor channels. It has been '
    || 'measured to have NO relationship to subsequent alarms: the alarm rate is 21.2% at worst health and 17.7% '
    || 'at best. Say clearly what it does tell you and what it does not. Do not call it predictive. No bullet points. '
    || 'Figures: ' || a.MACHINES || ' machines monitored, average health index '
    || a.AVG_HEALTH || ' out of 100, worst observed ' || a.WORST_HEALTH
    || ', and the channel most often responsible is ' || a.DOMINANT_CHANNEL || '.'
  ),
  'DERIVED_FROM_OBSERVED',
  'llama3.3-70b',
  CURRENT_TIMESTAMP()
FROM plant_a_facts a;

COMMENT ON TABLE GOLD.CORTEX_BRIEFING IS
  'Cortex-written narrative over aggregates. INPUT_ORIGIN says whether the figures behind each briefing are observed or synthetic.';

/* Per-cause recommendations.

   The previous version asked llama3.1-8b to CLASSIFY each cause into one of
   four buckets. It returned 'OCCASIONAL_LONG' for all nineteen, including for
   a cause with 50,149 occurrences at a 1.3-minute median and one with 64
   occurrences at 2.7 minutes. Valid output, useless answer, and it cost
   nineteen LLM calls to be worse than an IF statement. The classification is
   now a deterministic rule inside GOLD.V_DOWNTIME_PARETO.

   What remains for the model is the thing it is actually good at: turning a
   pattern and a set of numbers into a sentence a supervisor can act on. The
   label is supplied to it rather than asked of it, and the prompt states that
   the alarm code is anonymised so no mechanism can be inferred from it. */
CREATE OR REPLACE TABLE GOLD.CORTEX_CAUSE_ADVICE AS
SELECT
  PLANT_CODE,
  CAUSE_CODE,
  LOSS_NATURE,
  OWNING_FUNCTION,
  STOP_PATTERN,
  STOP_COUNT,
  STOP_HOURS,
  MEDIAN_STOP_MIN,
  PCT_OF_STOP_TIME,
  TRIM(SNOWFLAKE.CORTEX.COMPLETE('llama3.3-70b',
    'Write one sentence of advice for a shift supervisor about a single stop cause. '
    || 'The alarm code is anonymised by the data publisher, so do not speculate about a mechanism, a component '
    || 'or a root cause; talk about the pattern and what to do about a pattern of that shape. '
    || 'Be concrete and do not pad. One sentence only, no preamble. '
    || 'Cause code: ' || CAUSE_CODE
    || '. Nature: ' || LOSS_NATURE
    || '. Owned by: ' || OWNING_FUNCTION
    || '. Pattern: ' || STOP_PATTERN
    || '. Occurrences: ' || STOP_COUNT::VARCHAR
    || '. Median duration: ' || MEDIAN_STOP_MIN::VARCHAR || ' minutes'
    || '. Total hours lost: ' || STOP_HOURS::VARCHAR
    || '. Share of all stop time: ' || PCT_OF_STOP_TIME::VARCHAR || '%.'
  )) AS ADVICE,
  'DERIVED_FROM_OBSERVED' AS DATA_ORIGIN,
  'llama3.3-70b'          AS MODEL_USED
FROM GOLD.V_DOWNTIME_PARETO
/* Bounded on purpose. The tail below 0.5% of stop time is a hundred-odd codes
   nobody will act on, and every row here is a paid LLM call. */
WHERE PCT_OF_STOP_TIME >= 0.5;

DROP TABLE IF EXISTS GOLD.CORTEX_CAUSE_GROUP;

/* ==========================================================================
   4. Verification.
   ========================================================================== */

/* 1. Every presentation view returns rows, and none of them has quietly
      merged the plants. */
SELECT 'V_FLEET' AS VIEW_NAME, COUNT(*) AS ROW_COUNT,
       COUNT(DISTINCT PLANT_CODE) AS PLANTS FROM GOLD.V_FLEET
UNION ALL SELECT 'V_OEE_DAILY',       COUNT(*), COUNT(DISTINCT PLANT_CODE) FROM GOLD.V_OEE_DAILY
UNION ALL SELECT 'V_OEE_ROLLUP',      COUNT(*), COUNT(DISTINCT PLANT_CODE) FROM GOLD.V_OEE_ROLLUP
UNION ALL SELECT 'V_DOWNTIME_PARETO', COUNT(*), COUNT(DISTINCT PLANT_CODE) FROM GOLD.V_DOWNTIME_PARETO
UNION ALL SELECT 'V_COST_BY_MACHINE', COUNT(*), COUNT(DISTINCT PLANT_CODE) FROM GOLD.V_COST_BY_MACHINE
UNION ALL SELECT 'V_PLANT_A_HEALTH',  COUNT(*), COUNT(DISTINCT PLANT_CODE) FROM GOLD.V_PLANT_A_HEALTH
UNION ALL SELECT 'V_PLANT_B_RISK',    COUNT(*), COUNT(DISTINCT PLANT_CODE) FROM GOLD.V_PLANT_B_RISK
UNION ALL SELECT 'V_PROVENANCE',      COUNT(*), COUNT(DISTINCT PLANT_CODE) FROM GOLD.V_PROVENANCE;

/* 1b. The canonical OEE. One plant row and five machine rows. This is the
       only OEE figure the application is allowed to display. */
SELECT PLANT_CODE, COALESCE(MACHINE_CODE, 'ALL MACHINES') AS SCOPE,
       PLANNED_HOURS, RUN_HOURS, BREAKDOWN_HOURS, IDLE_HOURS, SLOW_RUNNING_HOURS,
       AVAILABILITY, PERFORMANCE, QUALITY, OEE
FROM GOLD.V_OEE_ROLLUP
ORDER BY PLANT_CODE, MACHINE_CODE NULLS FIRST;

/* 2. The Pareto must reach 100% cumulatively. IDLE_NO_ALARM should be at the
      top and must be labelled WAITING and owned by PLANNING, not
      MAINTENANCE. That labelling is the correction this view exists for. */
SELECT CAUSE_CODE, LOSS_NATURE, OWNING_FUNCTION, STOP_PATTERN,
       STOP_COUNT, STOP_HOURS, MEDIAN_STOP_MIN, PCT_OF_STOP_TIME, CUMULATIVE_PCT
FROM GOLD.V_DOWNTIME_PARETO
WHERE PLANT_CODE = 'PLANT_B'
ORDER BY STOP_HOURS DESC
LIMIT 12;

/* 2b. Maintenance against idling, per machine. PCT_COST_FROM_IDLING is the
       number that tells a maintenance manager which of these is theirs. */
SELECT PLANT_CODE, MACHINE_CODE, WORK_ORDERS, BREAKDOWN_HOURS,
       MAINTENANCE_COST, IDLE_INCIDENTS, IDLE_HOURS, IDLE_FORGONE_MARGIN,
       PCT_COST_FROM_IDLING
FROM GOLD.V_COST_BY_MACHINE
ORDER BY PLANT_CODE, MACHINE_CODE;

/* 3. The semantic view answers a question the way the metric definitions
      intend. Availability here must match the ratio computed directly from
      GOLD.PIADE_OEE_DAILY; if it does not, a metric is defined wrongly. */
SELECT * FROM SEMANTIC_VIEW(
  GOLD.SEM_SNOWCORE_OEE
  DIMENSIONS machine.machine_code
  METRICS oee.availability, oee.performance, oee.quality, oee.oee_pct,
          oee.downtime_hours
) ORDER BY MACHINE_CODE;

/* The independent check of the same numbers. */
SELECT
  MACHINE_CODE,
  ROUND(SUM(RUN_SEC) / NULLIF(SUM(PLANNED_SEC), 0), 4)                 AS AVAILABILITY_DIRECT,
  ROUND(SUM(PACKAGES_OUT) / NULLIF(SUM(THEORETICAL_PACKAGES), 0), 4)   AS PERFORMANCE_DIRECT,
  ROUND(SUM(PACKAGES_OUT) / NULLIF(SUM(PACKAGES_IN), 0), 4)            AS QUALITY_DIRECT,
  ROUND(SUM(DOWNTIME_SEC) / 3600.0, 1)                                 AS DOWNTIME_HOURS_DIRECT
FROM GOLD.PIADE_OEE_DAILY
GROUP BY MACHINE_CODE
ORDER BY MACHINE_CODE;

/* 4. The narrative. Read it, do not just count the rows: a model handed
      synthetic costs will describe them as measured unless the prompt stops
      it, and the PLANT_B_COST briefing is the one to check for that. */
SELECT BRIEFING_KEY, INPUT_ORIGIN, MODEL_USED, NARRATIVE
FROM GOLD.CORTEX_BRIEFING
ORDER BY BRIEFING_KEY;

/* 5. Per-cause advice. Read the sentences. The failure mode to look for is a
      model inventing a mechanism for an anonymised code — anything naming a
      bearing, a seal, a gripper or a sensor is fabrication and the prompt has
      failed. */
SELECT CAUSE_CODE, LOSS_NATURE, STOP_PATTERN, STOP_HOURS, ADVICE
FROM GOLD.CORTEX_CAUSE_ADVICE
ORDER BY STOP_HOURS DESC;

/* 5b. The deterministic classification that replaced the LLM one, so the
       spread can be seen at a glance. Anything that puts every cause in one
       bucket has the same problem the LLM had. */
SELECT STOP_PATTERN, COUNT(*) AS CAUSES,
       ROUND(SUM(STOP_HOURS), 1) AS STOP_HOURS,
       ROUND(SUM(PCT_OF_STOP_TIME), 2) AS PCT_OF_STOP_TIME
FROM GOLD.V_DOWNTIME_PARETO
WHERE PLANT_CODE = 'PLANT_B'
GROUP BY STOP_PATTERN
ORDER BY STOP_HOURS DESC;

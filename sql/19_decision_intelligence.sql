/* ============================================================================
   PIADE-only decision support.

   Five bounded views that turn the existing GOLD and ML contracts into
   something an analyst can reason over without re-deriving anything. Nothing
   new is generated here: every view is a projection of objects built by
   sql/13_gold_oee.sql, sql/15_plant_b_risk.sql, sql/16_it_synthetic.sql and
   sql/18_piade_erp.sql.

   WHAT THIS FILE DELIBERATELY DOES NOT DO

   1. It does not call anything revenue. PIADE publishes package counts and
      nothing else: no price, no currency, no order book. The only money in
      here is contribution margin taken from the assumptions that already
      exist, multiplied by a package count, and every such column is named
      SCENARIO_* and carries SYNTHETIC_ERP origin. If a price is ever
      supplied, revenue becomes a new column; it is not smuggled in by
      renaming margin.
   2. It does not resurrect ERP_TARGET_UPLIFT. That assumption was retired in
      sql/18_piade_erp.sql and GOLD.V_ASSUMPTIONS_ACTIVE excludes it by name.
      A gate at the bottom fails if it reappears.
   3. It does not touch CoMoPI. Plant A has no production counts, so no loss
      here could be costed and no lever could be ranked against Plant B's.
      Every view filters to PLANT_B or to assumption scopes PLANT_B / BOTH.
   4. It does not claim causality. GOLD.V_IMPROVEMENT_LEVERS is a size-of-loss
      ordering over observed history. It says where the hours went, not what
      would happen if someone acted, and CAUSAL_CAVEAT says so on every row.

   WHY THE LOSS SPLIT IS THREE BUCKETS AND HOW IT RECONCILES

   The loss view deliberately uses one internally consistent path from the
   rounded daily source columns. It derives planned seconds as RUN_SEC +
   DOWNTIME_SEC + IDLE_SEC and running theoretical packages as RUN_SEC x the
   observed ideal rate. It does not mix the separately rounded PLANNED_SEC or
   THEORETICAL_PACKAGES columns into the identity. On that one path:

     planned capacity
       = packages out
       + idle seconds     x rate      (PLANNING, line waiting, no alarm)
       + downtime seconds x rate      (MAINTENANCE, line faulted, alarm present)
       + (theoretical - packages out) (PERFORMANCE, produced below rate while running)

   The third bucket is a residual over running time, so it absorbs both slow
   running and throughput-yield loss. Splitting those two would double count,
   because a package that went in and did not come out is also a package the
   ideal rate expected. YIELD_SUBSET_UNITS reports the yield part separately
   as a subset, explicitly not an additional bucket.

   The residual can be negative on a day where the counters sampled an output
   into a later bucket than its input. The identity is preserved rather than
   clamped, and DAYS_OUTPUT_ABOVE_RUNNING_THEORETICAL keeps that artefact
   countable. Exactness is checked from unrounded CTE expressions; rounded
   view columns are presentation values and are not used by that gate.

   ROW BUDGET

     GOLD.V_ASSUMPTIONS_ACTIVE          17
     GOLD.V_MARGIN_SCENARIO_BASE         6   5 lines + site
     GOLD.V_OEE_LOSS_ATTRIBUTION        18   6 subjects x 3 buckets
     GOLD.V_IMPROVEMENT_LEVERS          15   5 lines x 3 buckets
     GOLD.V_ANALYST_DECISION_CONTEXT    76   long form, one fact per row

   The whole set stays under 100 rows per view so it can be handed to a
   narrative layer whole, without sampling and without a TOP N that silently
   drops the thing someone wanted to ask about.

   Run after sql/18_piade_erp.sql.
   ========================================================================== */

USE ROLE ACCOUNTADMIN;
USE DATABASE SNOWCORE_REAL;
USE WAREHOUSE COMPUTE_WH;
ALTER SESSION SET TIMEZONE = 'UTC';
ALTER SESSION SET QUERY_TAG = 'snowcore-real|piade|decision-intelligence';

/* Fail immediately with an object-not-found error if sequencing is wrong.
   Required order is 16 -> 15 -> 18 -> 19. */
SELECT COUNT(*) AS ERP_DEPENDENCY_CHECK       FROM GOLD.PRODUCTION_ORDER  WHERE 1=0;
SELECT COUNT(*) AS EXECUTIVE_DEPENDENCY_CHECK FROM GOLD.V_EXECUTIVE_KPI   WHERE 1=0;
SELECT COUNT(*) AS FLEET_DEPENDENCY_CHECK     FROM GOLD.V_EXECUTIVE_FLEET WHERE 1=0;

/* --------------------------------------------------------------------------
   1. Active assumptions.

   Active constants behind the existing PIADE business objects and the
   decision views in this file. CONSUMED_BY names the actual object that reads
   each value; documented but currently unconsumed lead-time bounds say so
   explicitly. Plant A scopes are excluded, and ERP_TARGET_UPLIFT is excluded
   by name so an older draft cannot quietly put it back on screen.
   -------------------------------------------------------------------------- */

CREATE OR REPLACE VIEW GOLD.V_ASSUMPTIONS_ACTIVE AS
SELECT
  a.ASSUMPTION_SET_ID,
  a.PLANT_SCOPE,
  a.NAME                                                     AS ASSUMPTION_NAME,
  a.VALUE                                                    AS ASSUMPTION_VALUE,
  a.UNIT,
  a.IS_MEASURED,
  IFF(a.IS_MEASURED, 'MEASURED_FROM_SOURCE', 'CHOSEN_BY_US') AS EVIDENCE_CLASS,
  a.BASIS,
  CASE a.NAME
    WHEN 'WORK_ORDER_MIN_BREAKDOWN_MINUTES' THEN 'NOT_CONSUMED: documented threshold; GOLD.WORK_ORDER currently uses equivalent fixed threshold 10'
    WHEN 'IDLE_INCIDENT_MIN_MINUTES'        THEN 'NOT_CONSUMED: documented threshold; GOLD.PRODUCTION_LOSS_INCIDENT currently uses equivalent fixed threshold 30'
    WHEN 'CONTRIBUTION_MARGIN_PER_PACKAGE'  THEN 'GOLD.WORK_ORDER; GOLD.PRODUCTION_LOSS_INCIDENT'
    WHEN 'ERP_MARGIN_PER_PACKAGE'           THEN 'GOLD.PRODUCTION_ORDER; GOLD.V_MARGIN_SCENARIO_BASE; GOLD.V_OEE_LOSS_ATTRIBUTION; GOLD.V_IMPROVEMENT_LEVERS'
    WHEN 'ERP_REORDER_DAYS'                 THEN 'GOLD.INVENTORY_SNAPSHOT'
    WHEN 'ERP_STOCK_COVER_MULTIPLIER'       THEN 'GOLD.INVENTORY_SNAPSHOT'
    WHEN 'ERP_LEAD_TIME_MIN_DAYS'           THEN 'NOT_CONSUMED: documented bound; GOLD.INVENTORY_SNAPSHOT currently uses equivalent fixed lower bound 2'
    WHEN 'ERP_LEAD_TIME_MAX_DAYS'           THEN 'NOT_CONSUMED: documented bound; GOLD.INVENTORY_SNAPSHOT currently uses equivalent fixed upper bound 14'
    WHEN 'LABOUR_RATE_PER_HOUR'             THEN 'GOLD.WORK_ORDER'
    WHEN 'RESPONSE_MINUTES_MIN'             THEN 'GOLD.WORK_ORDER'
    WHEN 'RESPONSE_MINUTES_MAX'             THEN 'GOLD.WORK_ORDER'
    WHEN 'WRENCH_TIME_FRACTION'             THEN 'GOLD.WORK_ORDER'
    WHEN 'PARTS_COST_MAX'                   THEN 'GOLD.WORK_ORDER'
    WHEN 'PARTS_PROBABILITY_P4'             THEN 'GOLD.WORK_ORDER'
    WHEN 'PARTS_PROBABILITY_P3'             THEN 'GOLD.WORK_ORDER'
    WHEN 'PARTS_PROBABILITY_P2'             THEN 'GOLD.WORK_ORDER'
    WHEN 'PARTS_PROBABILITY_P1'             THEN 'GOLD.WORK_ORDER'
    ELSE 'NOT_CONSUMED'
  END                                                        AS CONSUMED_BY,
  IFF(a.ASSUMPTION_SET_ID = 'AS-PIADE-ERP-2026-09-25',
      'SYNTHETIC_ERP', 'SYNTHETIC_IT')                       AS DATA_ORIGIN,
  /* An assumption is never observed data, whatever its basis. IS_MEASURED
     says the number was counted from the source; it does not promote the
     figure it produces to a fact. */
  'SCENARIO_ASSUMPTION'                                      AS CLAIM_CLASS,
  'GOLD.IT_ASSUMPTION'                                       AS SOURCE_VIEW
FROM GOLD.IT_ASSUMPTION a
WHERE a.ASSUMPTION_SET_ID IN ('AS-2026-09-24', 'AS-PIADE-ERP-2026-09-25')
  AND a.PLANT_SCOPE       IN ('PLANT_B', 'BOTH')
  AND a.NAME <> 'ERP_TARGET_UPLIFT';

COMMENT ON VIEW GOLD.V_ASSUMPTIONS_ACTIVE IS
  'Active PIADE business assumptions with their basis and actual consuming object. Plant A scopes and retired ERP_TARGET_UPLIFT are excluded; documented but unconsumed bounds are explicit.';

/* --------------------------------------------------------------------------
   2. Scenario base.

   Units are derived from observed PIADE seconds and observed ideal rates.
   The euros are a scenario: one assumed contribution margin per package,
   nothing else. This is not revenue and the view says so in its own columns.
   -------------------------------------------------------------------------- */

CREATE OR REPLACE VIEW GOLD.V_MARGIN_SCENARIO_BASE AS
WITH cfg AS (
  SELECT MAX(IFF(NAME = 'ERP_MARGIN_PER_PACKAGE', VALUE, NULL)) AS MARGIN
  FROM GOLD.IT_ASSUMPTION
  WHERE ASSUMPTION_SET_ID = 'AS-PIADE-ERP-2026-09-25'
    AND PLANT_SCOPE       = 'PLANT_B'
),
rolled AS (
  SELECT
    IFF(MACHINE_CODE IS NULL, 'SITE', 'LINE') AS GRAIN,
    COALESCE(MACHINE_CODE, 'PLANT_B')         AS SUBJECT,
    COUNT(*)                                  AS PRODUCTION_ORDER_ROWS,
    COUNT(DISTINCT PRODUCTION_DATE)           AS DAYS_OBSERVED,
    MIN(PRODUCTION_DATE)                      AS FROM_DATE,
    MAX(PRODUCTION_DATE)                      AS TO_DATE,
    SUM(ACTUAL_OUTPUT_UNITS)                  AS ACTUAL_OUTPUT_UNITS,
    SUM(TARGET_OUTPUT_UNITS)                  AS TARGET_OUTPUT_UNITS,
    SUM(OUTPUT_SHORTFALL_UNITS)               AS OUTPUT_SHORTFALL_UNITS,
    SUM(ACTUAL_MARGIN_EUR)                    AS ACTUAL_MARGIN_EUR,
    SUM(MARGIN_EXPOSURE_EUR)                  AS CLAMPED_SHORTFALL_MARGIN_EUR
  FROM GOLD.PRODUCTION_ORDER
  GROUP BY ROLLUP(MACHINE_CODE)
)
SELECT
  r.GRAIN,
  r.SUBJECT,
  r.PRODUCTION_ORDER_ROWS,
  r.DAYS_OBSERVED,
  r.FROM_DATE,
  r.TO_DATE,
  ROUND(r.ACTUAL_OUTPUT_UNITS, 0)                                    AS ACTUAL_OUTPUT_UNITS,
  ROUND(r.TARGET_OUTPUT_UNITS, 0)                                    AS TARGET_OUTPUT_UNITS,
  ROUND(r.OUTPUT_SHORTFALL_UNITS, 0)                                 AS OUTPUT_SHORTFALL_UNITS,
  ROUND(100 * DIV0(r.ACTUAL_OUTPUT_UNITS, r.TARGET_OUTPUT_UNITS), 2) AS ATTAINMENT_PCT,
  c.MARGIN                                                           AS SCENARIO_MARGIN_EUR_PER_UNIT,
  ROUND(r.ACTUAL_MARGIN_EUR, 2)                                      AS SCENARIO_ACTUAL_CONTRIBUTION_MARGIN_EUR,
  ROUND(r.CLAMPED_SHORTFALL_MARGIN_EUR, 2)                            AS SCENARIO_CLAMPED_SHORTFALL_MARGIN_EUR,
  /* Target is planned capacity at the machine's own best demonstrated rate.
     It is not a commercial commitment and no customer ordered it. */
  'Planned time at best demonstrated rate'                           AS TARGET_DEFINITION,
  'DERIVED_FROM_OBSERVED'                                            AS UNITS_ORIGIN,
  'SYNTHETIC_ERP'                                                    AS MONEY_ORIGIN,
  'DERIVED_FROM_OBSERVED + SYNTHETIC_ERP'                            AS DATA_ORIGIN,
  'AS-PIADE-ERP-2026-09-25'                                          AS ASSUMPTION_SET_ID,
  'SCENARIO'                                                         AS CLAIM_CLASS,
  'Contribution-margin scenario, not revenue. PIADE publishes package counts only: no price, no currency and no order book exist in the source. Supply a price and revenue becomes a separate column.'
                                                                     AS COMMERCIAL_NON_CLAIM,
  'GOLD.PRODUCTION_ORDER'                                            AS SOURCE_VIEW
FROM rolled r
CROSS JOIN cfg c;

COMMENT ON VIEW GOLD.V_MARGIN_SCENARIO_BASE IS
  'Actual, target and clamped shortfall packages per line and site, priced at one assumed contribution margin. This commercial scenario is not revenue and is not equivalent to signed OEE loss.';

/* --------------------------------------------------------------------------
   3. OEE loss attribution.

   The split that decides who owns the number. Idle is planning, faults are
   maintenance, and the running-time residual belongs to operations and
   engineering. Merging them would point the maintenance team at hours that
   were never theirs, which is the error sql/16_it_synthetic.sql already
   documents for work orders.
   -------------------------------------------------------------------------- */

CREATE OR REPLACE VIEW GOLD.V_OEE_LOSS_ATTRIBUTION AS
WITH cfg AS (
  SELECT MAX(IFF(NAME = 'ERP_MARGIN_PER_PACKAGE', VALUE, NULL)) AS MARGIN
  FROM GOLD.IT_ASSUMPTION
  WHERE ASSUMPTION_SET_ID = 'AS-PIADE-ERP-2026-09-25'
    AND PLANT_SCOPE       = 'PLANT_B'
),
daily AS (
  SELECT
    d.MACHINE_CODE,
    d.RUN_SEC, d.DOWNTIME_SEC, d.IDLE_SEC, d.SLOW_SEC,
    d.PACKAGES_IN, d.PACKAGES_OUT,
    r.IDEAL_RATE_PPH
  FROM GOLD.PIADE_OEE_DAILY d
  JOIN GOLD.OEE_IDEAL_RATE  r USING (MACHINE_KEY)
  WHERE d.PLANT_CODE = 'PLANT_B'
),
agg AS (
  SELECT
    IFF(MACHINE_CODE IS NULL, 'SITE', 'LINE')      AS GRAIN,
    COALESCE(MACHINE_CODE, 'PLANT_B')              AS SUBJECT,
    COUNT(*)                                       AS MACHINE_DAYS,
    SUM(IDLE_SEC)     / 3600.0                     AS IDLE_HOURS,
    SUM(DOWNTIME_SEC) / 3600.0                     AS FAULT_HOURS,
    SUM(SLOW_SEC)     / 3600.0                     AS SLOW_RUNNING_HOURS,
    SUM(IDLE_SEC     / 3600.0 * IDEAL_RATE_PPH)    AS IDLE_FORGONE_UNITS_RAW,
    SUM(DOWNTIME_SEC / 3600.0 * IDEAL_RATE_PPH)    AS FAULT_FORGONE_UNITS_RAW,
    /* Signed on purpose. Clamping this term would break the capacity
       identity the gates below check. */
    SUM(RUN_SEC / 3600.0 * IDEAL_RATE_PPH
        - PACKAGES_OUT)                            AS RUNNING_FORGONE_UNITS_RAW,
    SUM(PACKAGES_IN - PACKAGES_OUT)                AS YIELD_SUBSET_UNITS_RAW,
    /* Derive both sides from the same rounded daily seconds path. Do not use
       separately rounded PLANNED_SEC or THEORETICAL_PACKAGES here. */
    SUM((RUN_SEC + DOWNTIME_SEC + IDLE_SEC)
        / 3600.0 * IDEAL_RATE_PPH)                 AS PLANNED_CAPACITY_UNITS_RAW,
    SUM(RUN_SEC / 3600.0 * IDEAL_RATE_PPH)         AS RUNNING_THEORETICAL_UNITS_RAW,
    SUM(PACKAGES_OUT)                              AS ACTUAL_OUTPUT_UNITS_RAW,
    COUNT_IF(PACKAGES_OUT >
      RUN_SEC / 3600.0 * IDEAL_RATE_PPH)           AS DAYS_OUTPUT_ABOVE_RUNNING_THEORETICAL
  FROM daily
  GROUP BY ROLLUP(MACHINE_CODE)
),
totals AS (
  SELECT a.*,
    a.IDLE_FORGONE_UNITS_RAW + a.FAULT_FORGONE_UNITS_RAW
      + a.RUNNING_FORGONE_UNITS_RAW AS TOTAL_FORGONE_UNITS_RAW
  FROM agg a
),
buckets AS (
  SELECT
    t.GRAIN, t.SUBJECT, t.MACHINE_DAYS,
    'PLANNING_IDLE'                 AS LOSS_BUCKET,
    'PLANNING'                      AS OWNER_FUNCTION,
    'idle'                          AS OBSERVED_STATE,
    t.IDLE_HOURS                    AS LOSS_HOURS,
    t.IDLE_FORGONE_UNITS_RAW        AS FORGONE_UNITS_RAW,
    CAST(NULL AS FLOAT)             AS YIELD_SUBSET_UNITS,
    'Line available and not faulted. The source records no alarm for any idle interval, so this is waiting time.'
                                    AS BUCKET_DEFINITION,
    t.TOTAL_FORGONE_UNITS_RAW, t.PLANNED_CAPACITY_UNITS_RAW,
    t.RUNNING_THEORETICAL_UNITS_RAW, t.ACTUAL_OUTPUT_UNITS_RAW,
    t.DAYS_OUTPUT_ABOVE_RUNNING_THEORETICAL
  FROM totals t
  UNION ALL
  SELECT
    t.GRAIN, t.SUBJECT, t.MACHINE_DAYS,
    'MAINTENANCE_FAULT', 'MAINTENANCE', 'downtime',
    t.FAULT_HOURS,
    t.FAULT_FORGONE_UNITS_RAW,
    CAST(NULL AS FLOAT),
    'Line stopped with an alarm present. Every observed downtime interval carries an alarm code.',
    t.TOTAL_FORGONE_UNITS_RAW, t.PLANNED_CAPACITY_UNITS_RAW,
    t.RUNNING_THEORETICAL_UNITS_RAW, t.ACTUAL_OUTPUT_UNITS_RAW,
    t.DAYS_OUTPUT_ABOVE_RUNNING_THEORETICAL
  FROM totals t
  UNION ALL
  SELECT
    t.GRAIN, t.SUBJECT, t.MACHINE_DAYS,
    'PERFORMANCE_SLOW_RUNNING', 'OPERATIONS', 'performance_loss',
    t.SLOW_RUNNING_HOURS,
    t.RUNNING_FORGONE_UNITS_RAW,
    t.YIELD_SUBSET_UNITS_RAW,
    'Residual over running time: theoretical packages at best demonstrated rate less packages out. LOSS_HOURS counts only the performance_loss state, while FORGONE_UNITS spans all running time. YIELD_SUBSET_UNITS is the throughput-yield part of the same number, not an extra bucket.',
    t.TOTAL_FORGONE_UNITS_RAW, t.PLANNED_CAPACITY_UNITS_RAW,
    t.RUNNING_THEORETICAL_UNITS_RAW, t.ACTUAL_OUTPUT_UNITS_RAW,
    t.DAYS_OUTPUT_ABOVE_RUNNING_THEORETICAL
  FROM totals t
)
SELECT
  b.GRAIN,
  b.SUBJECT,
  b.LOSS_BUCKET,
  b.OWNER_FUNCTION,
  b.OBSERVED_STATE,
  b.MACHINE_DAYS,
  ROUND(b.LOSS_HOURS, 1)                                       AS LOSS_HOURS,
  ROUND(b.FORGONE_UNITS_RAW, 0)                                AS FORGONE_UNITS,
  ROUND(b.YIELD_SUBSET_UNITS, 0)                               AS YIELD_SUBSET_UNITS,
  ROUND(100 * DIV0(b.FORGONE_UNITS_RAW, b.TOTAL_FORGONE_UNITS_RAW), 2)
                                                               AS PCT_OF_SUBJECT_FORGONE,
  ROUND(b.TOTAL_FORGONE_UNITS_RAW, 0)                          AS SUBJECT_TOTAL_FORGONE_UNITS,
  ROUND(b.PLANNED_CAPACITY_UNITS_RAW, 0)                       AS PLANNED_CAPACITY_UNITS,
  ROUND(b.RUNNING_THEORETICAL_UNITS_RAW, 0)                    AS RUNNING_THEORETICAL_UNITS,
  ROUND(b.ACTUAL_OUTPUT_UNITS_RAW, 0)                          AS ACTUAL_OUTPUT_UNITS,
  b.DAYS_OUTPUT_ABOVE_RUNNING_THEORETICAL,
  ROUND(b.FORGONE_UNITS_RAW * c.MARGIN, 2)                     AS SCENARIO_SIGNED_LOSS_MARGIN_EUR,
  c.MARGIN                                                     AS SCENARIO_MARGIN_EUR_PER_UNIT,
  b.BUCKET_DEFINITION,
  'DERIVED_FROM_OBSERVED'                                      AS UNITS_ORIGIN,
  'SYNTHETIC_ERP'                                              AS MONEY_ORIGIN,
  'DERIVED_FROM_OBSERVED + SYNTHETIC_ERP'                      AS DATA_ORIGIN,
  'AS-PIADE-ERP-2026-09-25'                                    AS ASSUMPTION_SET_ID,
  'SCENARIO'                                                   AS CLAIM_CLASS,
  'GOLD.PIADE_OEE_DAILY; GOLD.OEE_IDEAL_RATE'                  AS SOURCE_VIEW
FROM buckets b
CROSS JOIN cfg c;

COMMENT ON VIEW GOLD.V_OEE_LOSS_ATTRIBUTION IS
  'Planning idle, maintenance fault and signed running residual per line and site. Capacity is derived consistently from rounded RUN_SEC, DOWNTIME_SEC and IDLE_SEC; exact reconciliation is checked on unrounded expressions, not presentation columns.';

/* --------------------------------------------------------------------------
   4. Improvement levers.

   One lever per line and loss bucket, ordered by the size of the loss.
   Ordering is deterministic: signed scenario loss margin, then units, then
   the subject and bucket names, all of which are stable strings.

   Historical concentration is reported two ways because they answer different
   questions. PCT_OF_SITE_BUCKET_LOSS says how much of the site's idle, fault
   or performance loss sits on this one line. PCT_OF_LINE_FORGONE says how
   much of this line's own problem this bucket is. A line can hold a small
   share of the site's faults while faults are still its own worst bucket, and
   a reader acting on one number needs the other.
   -------------------------------------------------------------------------- */

CREATE OR REPLACE VIEW GOLD.V_IMPROVEMENT_LEVERS AS
WITH line_loss AS (
  SELECT * FROM GOLD.V_OEE_LOSS_ATTRIBUTION WHERE GRAIN = 'LINE'
),
site_loss AS (
  SELECT LOSS_BUCKET, FORGONE_UNITS AS SITE_BUCKET_FORGONE_UNITS
  FROM GOLD.V_OEE_LOSS_ATTRIBUTION WHERE GRAIN = 'SITE'
),
/* Largest single anonymised alarm code by stopped minutes on each line.
   Ties break on the code so the pick is reproducible. */
top_fault_cause AS (
  SELECT
    MACHINE_CODE,
    ALARM_CODE AS CAUSE_CODE,
    ROUND(100 * DIV0(SUM(STOP_DURATION_MIN),
      SUM(SUM(STOP_DURATION_MIN)) OVER (PARTITION BY MACHINE_CODE)), 2) AS CAUSE_PCT
  FROM GOLD.PIADE_DOWNTIME_EVENT
  WHERE PLANT_CODE = 'PLANT_B' AND STOP_STATE = 'downtime'
  GROUP BY MACHINE_CODE, ALARM_CODE
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY MACHINE_CODE ORDER BY SUM(STOP_DURATION_MIN) DESC, ALARM_CODE) = 1
),
wo AS (
  SELECT MACHINE_CODE, COUNT(*) AS WORK_ORDERS
  FROM GOLD.WORK_ORDER WHERE PLANT_CODE = 'PLANT_B' GROUP BY MACHINE_CODE
),
pli AS (
  SELECT MACHINE_CODE, COUNT(*) AS IDLE_INCIDENTS,
         ROUND(MEDIAN(LOSS_MINUTES), 1) AS MEDIAN_IDLE_MINUTES
  FROM GOLD.PRODUCTION_LOSS_INCIDENT WHERE PLANT_CODE = 'PLANT_B'
  GROUP BY MACHINE_CODE
),
fleet AS (
  SELECT MACHINE_CODE, RISK_BAND, LAST_RISK_SCORE, MODEL_VS_BASELINE_TRUST
  FROM GOLD.V_EXECUTIVE_FLEET
),
levers AS (
  SELECT
    l.SUBJECT                     AS MACHINE_CODE,
    l.LOSS_BUCKET,
    l.OWNER_FUNCTION,
    l.MACHINE_DAYS,
    l.LOSS_HOURS                  AS OBSERVED_LOSS_HOURS,
    l.FORGONE_UNITS               AS OBSERVED_FORGONE_PACKAGES,
    l.ACTUAL_OUTPUT_UNITS         AS OBSERVED_PACKAGES_OUT,
    l.PCT_OF_SUBJECT_FORGONE      AS PCT_OF_LINE_FORGONE,
    ROUND(100 * DIV0(l.FORGONE_UNITS, s.SITE_BUCKET_FORGONE_UNITS), 2)
                                  AS PCT_OF_SITE_BUCKET_LOSS,
    l.SCENARIO_SIGNED_LOSS_MARGIN_EUR,
    l.SCENARIO_MARGIN_EUR_PER_UNIT,
    CASE l.LOSS_BUCKET
      WHEN 'MAINTENANCE_FAULT' THEN tc.CAUSE_CODE
      WHEN 'PLANNING_IDLE'     THEN 'IDLE_NO_ALARM'
      ELSE CAST(NULL AS VARCHAR)
    END                           AS TOP_CONTRIBUTING_CAUSE,
    CASE l.LOSS_BUCKET
      WHEN 'MAINTENANCE_FAULT' THEN tc.CAUSE_PCT
      WHEN 'PLANNING_IDLE'     THEN 100.00
      ELSE CAST(NULL AS FLOAT)
    END                           AS TOP_CAUSE_PCT_OF_BUCKET_TIME,
    IFF(l.LOSS_BUCKET = 'MAINTENANCE_FAULT',
        COALESCE(w.WORK_ORDERS, 0), NULL) AS WORK_ORDERS,
    IFF(l.LOSS_BUCKET = 'PLANNING_IDLE',
        COALESCE(p.IDLE_INCIDENTS, 0), NULL) AS IDLE_INCIDENTS,
    IFF(l.LOSS_BUCKET = 'PLANNING_IDLE',
        p.MEDIAN_IDLE_MINUTES, NULL) AS MEDIAN_IDLE_MINUTES,
    f.RISK_BAND                   AS LAST_RISK_BAND,
    f.LAST_RISK_SCORE,
    f.MODEL_VS_BASELINE_TRUST,
    CASE l.LOSS_BUCKET
      WHEN 'PLANNING_IDLE' THEN
        'Planning owns this. Check schedule, upstream supply and changeover sequencing before any maintenance work is raised.'
      WHEN 'MAINTENANCE_FAULT' THEN
        'Maintenance owns this. Review the alarm pattern behind the leading code and inspect only where operational evidence agrees. The code is publisher-anonymised, so do not infer a component.'
      ELSE
        'Operations and engineering own this. The line ran below its own best demonstrated rate; confirm that rate is still achievable for the current product mix before treating the gap as recoverable.'
    END                           AS RECOMMENDED_NEXT_STEP,
    'Size-of-loss ordering over observed history. Not causal, not a forecast, and not a claim that acting on this lever recovers the stated margin.'
                                  AS CAUSAL_CAVEAT,
    l.DATA_ORIGIN,
    l.ASSUMPTION_SET_ID
  FROM line_loss l
  JOIN      site_loss       s  USING (LOSS_BUCKET)
  LEFT JOIN top_fault_cause tc ON tc.MACHINE_CODE = l.SUBJECT
  LEFT JOIN wo              w  ON w.MACHINE_CODE  = l.SUBJECT
  LEFT JOIN pli             p  ON p.MACHINE_CODE  = l.SUBJECT
  LEFT JOIN fleet           f  ON f.MACHINE_CODE  = l.SUBJECT
)
SELECT
  ROW_NUMBER() OVER (
    ORDER BY SCENARIO_SIGNED_LOSS_MARGIN_EUR DESC, OBSERVED_FORGONE_PACKAGES DESC,
             MACHINE_CODE, LOSS_BUCKET)  AS LEVER_RANK,
  LOSS_BUCKET || '|' || MACHINE_CODE     AS LEVER_ID,
  *,
  'Observed loss hours=' || ROUND(OBSERVED_LOSS_HOURS, 1)
    || '; forgone packages=' || ROUND(OBSERVED_FORGONE_PACKAGES, 0)
    || '; ' || ROUND(PCT_OF_SITE_BUCKET_LOSS, 1) || '% of the site bucket'
                                         AS EVIDENCE_NOTE,
  'GOLD.V_OEE_LOSS_ATTRIBUTION; GOLD.PIADE_DOWNTIME_EVENT; GOLD.WORK_ORDER; GOLD.PRODUCTION_LOSS_INCIDENT; GOLD.V_EXECUTIVE_FLEET'
                                         AS SOURCE_VIEW,
  'SCENARIO'                             AS CLAIM_CLASS
FROM levers;

COMMENT ON VIEW GOLD.V_IMPROVEMENT_LEVERS IS
  'One lever per line and loss bucket, ranked deterministically by signed scenario loss margin. Work-order fields exist only for maintenance; idle-incident fields only for planning. Ranking asserts no causal effect.';

/* --------------------------------------------------------------------------
   5. Long-form analyst decision context.

   One fact per row so a narrative layer never has to guess which column of a
   wide row it is quoting, and so every number arrives with its own origin,
   claim class and source. Bounded well under 100 rows.

   OBJECT_CONSTRUCT drops NULL values, so a metric that is genuinely absent
   produces no row rather than a row asserting zero.
   -------------------------------------------------------------------------- */

CREATE OR REPLACE VIEW GOLD.V_ANALYST_DECISION_CONTEXT AS
WITH context_as_of AS (
  SELECT MAX(OEE_DATE)::TIMESTAMP_NTZ AS AS_OF_TS
  FROM GOLD.PIADE_OEE_DAILY WHERE PLANT_CODE = 'PLANT_B'
),

/* --- site OEE and volume: 7 rows --- */
site_kpi AS (
  SELECT
    1                      AS TOPIC_SORT,
    'SITE|' || f.KEY       AS CONTEXT_KEY,
    'SITE_PERFORMANCE'     AS TOPIC,
    'PLANT_B'              AS SUBJECT,
    'SITE'                 AS GRAIN,
    f.KEY                  AS METRIC_NAME,
    f.VALUE::FLOAT         AS METRIC_VALUE_NUM,
    CAST(NULL AS VARCHAR)  AS METRIC_VALUE_TEXT,
    CASE
      WHEN f.KEY LIKE '%HOURS'    THEN 'hours'
      WHEN f.KEY LIKE '%PACKAGES' THEN 'packages'
      ELSE 'ratio'
    END                    AS UNIT,
    'DERIVED_FROM_OBSERVED' AS DATA_ORIGIN,
    'GOLD.V_EXECUTIVE_KPI'  AS SOURCE_VIEW,
    CAST(NULL AS VARCHAR)   AS ASSUMPTION_SET_ID,
    'DERIVED_FROM_OBSERVED' AS CLAIM_CLASS,
    'Weighted from summed seconds and packages, not an average of daily ratios. Throughput yield is a package in/out ratio, not an inspection result.'
                            AS EVIDENCE_NOTE
  FROM GOLD.V_EXECUTIVE_KPI k,
  LATERAL FLATTEN(input => OBJECT_CONSTRUCT(
    'OEE',                    k.SITE_WEIGHTED_OEE,
    'AVAILABILITY',           k.AVAILABILITY,
    'PERFORMANCE',            k.PERFORMANCE,
    'THROUGHPUT_YIELD',       k.QUALITY,
    'ACTUAL_OUTPUT_PACKAGES', k.ACTUAL_OUTPUT_UNITS,
    'BREAKDOWN_HOURS',        k.BREAKDOWN_HOURS,
    'IDLE_HOURS',             k.IDLE_HOURS)) f
),

/* --- per-line OEE: 5 rows --- */
line_oee AS (
  SELECT
    2,
    'LINE|' || MACHINE_CODE || '|OEE',
    'LINE_PERFORMANCE',
    MACHINE_CODE,
    'LINE',
    'OEE',
    ROUND(OEE, 4),
    CAST(NULL AS VARCHAR),
    'ratio',
    'DERIVED_FROM_OBSERVED',
    'GOLD.V_EXECUTIVE_FLEET',
    CAST(NULL AS VARCHAR),
    'DERIVED_FROM_OBSERVED',
    'Weighted over the full observed period for this line.'
  FROM GOLD.V_EXECUTIVE_FLEET
),

/* --- per-line latest risk band: 5 rows --- */
line_risk AS (
  SELECT
    2,
    'LINE|' || MACHINE_CODE || '|RISK_BAND',
    'LINE_PERFORMANCE',
    MACHINE_CODE,
    'LINE',
    'LAST_RISK_BAND',
    CAST(NULL AS FLOAT),
    RISK_BAND,
    'band',
    'MODEL_DERIVED_FROM_OBSERVED',
    'GOLD.V_EXECUTIVE_FLEET',
    CAST(NULL AS VARCHAR),
    'MODEL_ESTIMATE',
    'Latest blind-test hourly ranking for this line. A band is a ranking position, not a probability of failure.'
  FROM GOLD.V_EXECUTIVE_FLEET
),

/* --- site loss attribution, 3 buckets x 3 metrics: 9 rows --- */
loss_ctx AS (
  SELECT
    3,
    'LOSS|' || l.LOSS_BUCKET || '|' || f.KEY,
    'LOSS_ATTRIBUTION',
    'PLANT_B',
    'SITE',
    l.LOSS_BUCKET || '_' || f.KEY,
    f.VALUE::FLOAT,
    CAST(NULL AS VARCHAR),
    CASE f.KEY
      WHEN 'LOSS_HOURS'       THEN 'hours'
      WHEN 'FORGONE_PACKAGES' THEN 'packages'
      ELSE 'EUR'
    END,
    IFF(f.KEY = 'SCENARIO_SIGNED_LOSS_MARGIN_EUR', 'SYNTHETIC_ERP', 'DERIVED_FROM_OBSERVED'),
    l.SOURCE_VIEW,
    l.ASSUMPTION_SET_ID,
    IFF(f.KEY = 'SCENARIO_SIGNED_LOSS_MARGIN_EUR', 'SCENARIO', 'DERIVED_FROM_OBSERVED'),
    'Loss bucket=' || l.LOSS_BUCKET || '; owner=' || l.OWNER_FUNCTION || '. ' || l.BUCKET_DEFINITION
  FROM GOLD.V_OEE_LOSS_ATTRIBUTION l,
  LATERAL FLATTEN(input => OBJECT_CONSTRUCT(
    'LOSS_HOURS',                   l.LOSS_HOURS,
    'FORGONE_PACKAGES',             l.FORGONE_UNITS,
    'SCENARIO_SIGNED_LOSS_MARGIN_EUR', l.SCENARIO_SIGNED_LOSS_MARGIN_EUR)) f
  WHERE l.GRAIN = 'SITE'
),

/* --- site scenario: 6 rows --- */
scenario_ctx AS (
  SELECT
    4,
    'SCENARIO|' || f.KEY,
    'MARGIN_SCENARIO',
    'PLANT_B',
    'SITE',
    f.KEY,
    f.VALUE::FLOAT,
    CAST(NULL AS VARCHAR),
    IFF(f.KEY LIKE '%EUR%', 'EUR', 'packages'),
    IFF(f.KEY LIKE '%EUR%', 'SYNTHETIC_ERP', 'DERIVED_FROM_OBSERVED'),
    s.SOURCE_VIEW,
    s.ASSUMPTION_SET_ID,
    IFF(f.KEY LIKE '%EUR%', 'SCENARIO', 'DERIVED_FROM_OBSERVED'),
    s.COMMERCIAL_NON_CLAIM
  FROM GOLD.V_MARGIN_SCENARIO_BASE s,
  LATERAL FLATTEN(input => OBJECT_CONSTRUCT(
    'ACTUAL_OUTPUT_PACKAGES',                  s.ACTUAL_OUTPUT_UNITS,
    'TARGET_OUTPUT_PACKAGES',                  s.TARGET_OUTPUT_UNITS,
    'OUTPUT_SHORTFALL_PACKAGES',               s.OUTPUT_SHORTFALL_UNITS,
    'SCENARIO_MARGIN_EUR_PER_PACKAGE',         s.SCENARIO_MARGIN_EUR_PER_UNIT,
    'SCENARIO_ACTUAL_CONTRIBUTION_MARGIN_EUR', s.SCENARIO_ACTUAL_CONTRIBUTION_MARGIN_EUR,
    'SCENARIO_CLAMPED_SHORTFALL_MARGIN_EUR',   s.SCENARIO_CLAMPED_SHORTFALL_MARGIN_EUR)) f
  WHERE s.GRAIN = 'SITE'
),

/* --- top five levers, 2 numeric facts each: 10 rows --- */
lever_num AS (
  SELECT
    5,
    'LEVER|' || v.LEVER_ID || '|' || f.KEY,
    'IMPROVEMENT_LEVER',
    v.LEVER_ID,
    'LINE_BUCKET',
    f.KEY,
    f.VALUE::FLOAT,
    CAST(NULL AS VARCHAR),
    IFF(f.KEY LIKE '%EUR%', 'EUR', 'packages'),
    IFF(f.KEY LIKE '%EUR%', 'SYNTHETIC_ERP', 'DERIVED_FROM_OBSERVED'),
    v.SOURCE_VIEW,
    v.ASSUMPTION_SET_ID,
    IFF(f.KEY LIKE '%EUR%', 'SCENARIO', 'DERIVED_FROM_OBSERVED'),
    'Rank ' || v.LEVER_RANK || '. ' || v.EVIDENCE_NOTE || '. ' || v.CAUSAL_CAVEAT
  FROM GOLD.V_IMPROVEMENT_LEVERS v,
  LATERAL FLATTEN(input => OBJECT_CONSTRUCT(
    'OBSERVED_FORGONE_PACKAGES',    v.OBSERVED_FORGONE_PACKAGES,
    'SCENARIO_SIGNED_LOSS_MARGIN_EUR', v.SCENARIO_SIGNED_LOSS_MARGIN_EUR)) f
  WHERE v.LEVER_RANK <= 5
),

/* --- owner of each of those five levers: 5 rows --- */
lever_owner AS (
  SELECT
    5,
    'LEVER|' || LEVER_ID || '|OWNER_FUNCTION',
    'IMPROVEMENT_LEVER',
    LEVER_ID,
    'LINE_BUCKET',
    'OWNER_FUNCTION',
    CAST(NULL AS FLOAT),
    OWNER_FUNCTION,
    'function',
    'DERIVED_FROM_OBSERVED',
    SOURCE_VIEW,
    ASSUMPTION_SET_ID,
    'DERIVED_FROM_OBSERVED',
    RECOMMENDED_NEXT_STEP
  FROM GOLD.V_IMPROVEMENT_LEVERS
  WHERE LEVER_RANK <= 5
),

/* --- model trust, numeric: 4 rows --- */
model_num AS (
  SELECT
    6,
    'MODEL|' || f.KEY,
    'MODEL_TRUST',
    'FLEET',
    'SITE',
    f.KEY,
    f.VALUE::FLOAT,
    CAST(NULL AS VARCHAR),
    'ratio',
    'MODEL_DERIVED_FROM_OBSERVED',
    'ML.PLANT_B_MODEL_METRICS',
    CAST(NULL AS VARCHAR),
    'MODEL_ESTIMATE',
    'Measured once on the blind period. Exactly the top 10% of machine-hours are flagged, so recall is bounded by construction.'
  FROM ML.PLANT_B_MODEL_METRICS m,
  LATERAL FLATTEN(input => OBJECT_CONSTRUCT(
    'AUC',                           m.AUC,
    'AVG_PRECISION',                 m.AVG_PRECISION,
    'TOP_DECILE_PRECISION',          m.TOP_DECILE_PRECISION,
    'BASELINE_TOP_DECILE_PRECISION', m.BASELINE_TOP_DECILE_PRECISION)) f
  WHERE m.SCOPE = 'FLEET'
),

/* --- model trust, text: 2 rows --- */
model_verdict AS (
  SELECT
    6,
    'MODEL|VERDICT_VS_PERSISTENCE',
    'MODEL_TRUST',
    'FLEET',
    'SITE',
    'VERDICT_VS_PERSISTENCE',
    CAST(NULL AS FLOAT),
    IFF(m.TOP_DECILE_PRECISION > m.BASELINE_TOP_DECILE_PRECISION,
        'MODEL_OUTPERFORMS_PERSISTENCE',
        'MODEL_DOES_NOT_OUTPERFORM_PERSISTENCE'),
    'text',
    'MODEL_DERIVED_FROM_OBSERVED',
    'ML.PLANT_B_MODEL_METRICS',
    CAST(NULL AS VARCHAR),
    'MODEL_ESTIMATE',
    'Recomputed from the persisted metrics on every read, never written in prose.'
  FROM ML.PLANT_B_MODEL_METRICS m
  WHERE m.SCOPE = 'FLEET'
),
model_caveat AS (
  SELECT
    6,
    'MODEL|CAVEAT',
    'MODEL_TRUST',
    'FLEET',
    'SITE',
    'CAVEAT',
    CAST(NULL AS FLOAT),
    m.CAVEAT,
    'text',
    'MODEL_DERIVED_FROM_OBSERVED',
    'ML.PLANT_B_MODEL_METRICS',
    CAST(NULL AS VARCHAR),
    'MODEL_ESTIMATE',
    'Caveat exactly as persisted by the training run.'
  FROM ML.PLANT_B_MODEL_METRICS m
  WHERE m.SCOPE = 'FLEET'
),

/* --- active assumptions: 17 rows --- */
assumption_ctx AS (
  SELECT
    7,
    'ASSUMPTION|' || a.ASSUMPTION_SET_ID || '|' || a.ASSUMPTION_NAME,
    'ASSUMPTION',
    a.ASSUMPTION_NAME,
    'ASSUMPTION',
    'ASSUMPTION_VALUE',
    a.ASSUMPTION_VALUE,
    a.EVIDENCE_CLASS,
    a.UNIT,
    a.DATA_ORIGIN,
    a.SOURCE_VIEW,
    a.ASSUMPTION_SET_ID,
    'SCENARIO_ASSUMPTION',
    'Scope=' || a.PLANT_SCOPE || '. ' || a.BASIS || ' Consumed by: ' || a.CONSUMED_BY
  FROM GOLD.V_ASSUMPTIONS_ACTIVE a
),

/* --- standing non-claims: 6 rows. These exist so a narrative layer has to
       read them before it invents one of them. DATA_ORIGIN is NOT_DATA
       because a non-claim is a boundary, not a measurement. --- */
non_claims AS (
  SELECT
    8,
    'NON_CLAIM|' || v.K,
    'NON_CLAIM',
    'PLANT_B',
    'SITE',
    v.K,
    CAST(NULL AS FLOAT),
    v.T,
    'text',
    'NOT_DATA',
    v.S,
    CAST(NULL AS VARCHAR),
    'NON_CLAIM',
    'Stated here so it cannot be asserted by omission.'
  FROM VALUES
    ('NO_REVENUE',
     'PIADE publishes package counts only. There is no price, currency or order book in the source, so no figure here is revenue. All euros are contribution-margin scenarios.',
     'GOLD.PRODUCTION_ORDER; GOLD.IT_ASSUMPTION'),
    ('NO_SENSORS',
     'PIADE contains no vibration, temperature or RPM channels. Nothing here is condition monitoring, remaining useful life or physics-based failure prediction.',
     'SILVER.PIADE_INTERVAL'),
    ('NO_COMPONENT_IDENTITY',
     'Alarm and cause codes are publisher-anonymised. Materials are generic service kits; no physical component is identified or implied.',
     'GOLD.PIADE_DOWNTIME_EVENT; GOLD.DIM_MATERIAL'),
    ('NO_SECOND_SITE',
     'This is one anonymised site with five lines. CoMoPI is a different factory with no join key and no production counts, and is excluded from every view in this file.',
     'SILVER.DIM_MACHINE'),
    ('NO_CAUSALITY',
     'Lever ordering and risk ranking describe observed history. Neither supports a counterfactual claim about what acting would recover.',
     'GOLD.PIADE_OEE_DAILY; ML.PLANT_B_MODEL_METRICS'),
    ('NO_SAVINGS_CLAIM',
     'No ROI, payback or saving is computed anywhere in this file. Signed loss margin and clamped shortfall margin are exposure scenarios, not recoverable amounts.',
     'GOLD.V_MARGIN_SCENARIO_BASE; GOLD.V_OEE_LOSS_ATTRIBUTION')
  v(K, T, S)
),

facts AS (
            SELECT * FROM site_kpi
  UNION ALL SELECT * FROM line_oee
  UNION ALL SELECT * FROM line_risk
  UNION ALL SELECT * FROM loss_ctx
  UNION ALL SELECT * FROM scenario_ctx
  UNION ALL SELECT * FROM lever_num
  UNION ALL SELECT * FROM lever_owner
  UNION ALL SELECT * FROM model_num
  UNION ALL SELECT * FROM model_verdict
  UNION ALL SELECT * FROM model_caveat
  UNION ALL SELECT * FROM assumption_ctx
  UNION ALL SELECT * FROM non_claims
)
SELECT
  f.CONTEXT_KEY,
  f.TOPIC,
  f.SUBJECT,
  f.GRAIN,
  f.METRIC_NAME,
  f.METRIC_VALUE_NUM,
  f.METRIC_VALUE_TEXT,
  f.UNIT,
  f.DATA_ORIGIN,
  f.SOURCE_VIEW,
  f.ASSUMPTION_SET_ID,
  a.AS_OF_TS,
  f.CLAIM_CLASS,
  f.EVIDENCE_NOTE,
  f.TOPIC_SORT
FROM facts f
CROSS JOIN context_as_of a;

COMMENT ON VIEW GOLD.V_ANALYST_DECISION_CONTEXT IS
  'Bounded long-form decision context: one fact per row with its unit, origin, source view, assumption set, as-of timestamp and claim class. Under 100 rows so it can be supplied whole.';

/* All dependencies have been moved to GOLD.V_MARGIN_SCENARIO_BASE. Remove the
   obsolete misleading name only after the context view has been replaced. */
DROP VIEW IF EXISTS GOLD.V_REVENUE_SCENARIO_BASE;

/* ==========================================================================
   Reconciliation, lineage and boundary gates.

   Everything below is a check. A non-zero failure count, or an actual that
   does not match its expected, is a deployment failure rather than an
   observation to be written up afterwards.
   ========================================================================== */

/* 1. Row budgets and context key uniqueness. Every row returns PASS or FAIL. */
WITH checks AS (
  SELECT 'V_ASSUMPTIONS_ACTIVE' VIEW_NAME, 17 EXPECTED_ROWS,
         (SELECT COUNT(*) FROM GOLD.V_ASSUMPTIONS_ACTIVE) ACTUAL_ROWS
  UNION ALL SELECT 'V_MARGIN_SCENARIO_BASE', 6,
         (SELECT COUNT(*) FROM GOLD.V_MARGIN_SCENARIO_BASE)
  UNION ALL SELECT 'V_OEE_LOSS_ATTRIBUTION', 18,
         (SELECT COUNT(*) FROM GOLD.V_OEE_LOSS_ATTRIBUTION)
  UNION ALL SELECT 'V_IMPROVEMENT_LEVERS', 15,
         (SELECT COUNT(*) FROM GOLD.V_IMPROVEMENT_LEVERS)
  UNION ALL SELECT 'V_ANALYST_DECISION_CONTEXT', 76,
         (SELECT COUNT(*) FROM GOLD.V_ANALYST_DECISION_CONTEXT)
)
SELECT VIEW_NAME, EXPECTED_ROWS, ACTUAL_ROWS,
       IFF(ACTUAL_ROWS = EXPECTED_ROWS, 'PASS', 'FAIL') AS RESULT
FROM checks ORDER BY VIEW_NAME;

WITH c AS (
  SELECT COUNT(*) CONTEXT_ROWS,
         COUNT(*) - COUNT(DISTINCT CONTEXT_KEY) DUPLICATE_CONTEXT_KEYS
  FROM GOLD.V_ANALYST_DECISION_CONTEXT
)
SELECT *, IFF(CONTEXT_ROWS < 100 AND DUPLICATE_CONTEXT_KEYS = 0,
              'PASS', 'FAIL') AS RESULT
FROM c;

/* 2. Retired uplift and PIADE-only scope. */
WITH c AS (
  SELECT
    (SELECT COUNT(*) FROM GOLD.IT_ASSUMPTION
     WHERE NAME = 'ERP_TARGET_UPLIFT') AS UPLIFT_IN_BASE_TABLE,
    (SELECT COUNT(*) FROM GOLD.V_ASSUMPTIONS_ACTIVE
     WHERE ASSUMPTION_NAME = 'ERP_TARGET_UPLIFT') AS UPLIFT_IN_ACTIVE_VIEW,
    (SELECT COUNT(*) FROM GOLD.V_ASSUMPTIONS_ACTIVE
     WHERE PLANT_SCOPE NOT IN ('PLANT_B','BOTH')) AS NON_PIADE_ASSUMPTIONS,
    (SELECT COUNT(*) FROM GOLD.V_MARGIN_SCENARIO_BASE s
     WHERE s.SUBJECT <> 'PLANT_B'
       AND NOT EXISTS (SELECT 1 FROM SILVER.DIM_MACHINE m
                       WHERE m.PLANT_CODE='PLANT_B'
                         AND m.MACHINE_CODE=s.SUBJECT)) AS NON_PIADE_MARGIN_SUBJECTS,
    (SELECT COUNT(*) FROM GOLD.V_OEE_LOSS_ATTRIBUTION l
     WHERE l.SUBJECT <> 'PLANT_B'
       AND NOT EXISTS (SELECT 1 FROM SILVER.DIM_MACHINE m
                       WHERE m.PLANT_CODE='PLANT_B'
                         AND m.MACHINE_CODE=l.SUBJECT)) AS NON_PIADE_LOSS_SUBJECTS,
    (SELECT COUNT(*) FROM GOLD.V_IMPROVEMENT_LEVERS v
     WHERE NOT EXISTS (SELECT 1 FROM SILVER.DIM_MACHINE m
                       WHERE m.PLANT_CODE='PLANT_B'
                         AND m.MACHINE_CODE=v.MACHINE_CODE)) AS NON_PIADE_LEVER_LINES
)
SELECT *, IFF(UPLIFT_IN_BASE_TABLE=0 AND UPLIFT_IN_ACTIVE_VIEW=0
  AND NON_PIADE_ASSUMPTIONS=0 AND NON_PIADE_MARGIN_SUBJECTS=0
  AND NON_PIADE_LOSS_SUBJECTS=0 AND NON_PIADE_LEVER_LINES=0,
  'PASS','FAIL') AS RESULT
FROM c;

/* 3. The two existing margin assumptions must agree and be present. */
WITH c AS (
  SELECT
    (SELECT VALUE FROM GOLD.IT_ASSUMPTION
     WHERE ASSUMPTION_SET_ID='AS-PIADE-ERP-2026-09-25'
       AND PLANT_SCOPE='PLANT_B' AND NAME='ERP_MARGIN_PER_PACKAGE') ERP_MARGIN,
    (SELECT VALUE FROM GOLD.IT_ASSUMPTION
     WHERE ASSUMPTION_SET_ID='AS-2026-09-24'
       AND PLANT_SCOPE='PLANT_B' AND NAME='CONTRIBUTION_MARGIN_PER_PACKAGE') IT_MARGIN,
    (SELECT COUNT_IF(SCENARIO_MARGIN_EUR_PER_UNIT IS NULL)
     FROM GOLD.V_MARGIN_SCENARIO_BASE) ROWS_WITHOUT_MARGIN
)
SELECT *, IFF(ERP_MARGIN=IT_MARGIN AND ROWS_WITHOUT_MARGIN=0,
              'PASS','FAIL') AS RESULT
FROM c;

/* 4. Exact algebraic capacity reconciliation from unrounded expressions.
      This gate repeats the same consistent source path as the view:
      planned=(run+downtime+idle)*rate and running theoretical=run*rate.
      The 0.000001-package tolerance covers floating-point accumulation only;
      no rounded presentation column participates. */
WITH daily AS (
  SELECT d.MACHINE_CODE,d.RUN_SEC,d.DOWNTIME_SEC,d.IDLE_SEC,
         d.PACKAGES_OUT,r.IDEAL_RATE_PPH
  FROM GOLD.PIADE_OEE_DAILY d
  JOIN GOLD.OEE_IDEAL_RATE r USING(MACHINE_KEY)
  WHERE d.PLANT_CODE='PLANT_B'
), rolled AS (
  SELECT IFF(MACHINE_CODE IS NULL,'SITE','LINE') GRAIN,
         COALESCE(MACHINE_CODE,'PLANT_B') SUBJECT,
         SUM((RUN_SEC+DOWNTIME_SEC+IDLE_SEC)/3600.0*IDEAL_RATE_PPH)
           AS PLANNED_CAPACITY_UNITS_RAW,
         SUM(IDLE_SEC/3600.0*IDEAL_RATE_PPH)
         +SUM(DOWNTIME_SEC/3600.0*IDEAL_RATE_PPH)
         +SUM(RUN_SEC/3600.0*IDEAL_RATE_PPH-PACKAGES_OUT)
         +SUM(PACKAGES_OUT) AS RECONSTRUCTED_CAPACITY_UNITS_RAW
  FROM daily GROUP BY ROLLUP(MACHINE_CODE)
)
SELECT GRAIN,SUBJECT,PLANNED_CAPACITY_UNITS_RAW,
       RECONSTRUCTED_CAPACITY_UNITS_RAW,
       PLANNED_CAPACITY_UNITS_RAW-RECONSTRUCTED_CAPACITY_UNITS_RAW
         AS DIFFERENCE_UNITS,
       0.000001 AS FLOATING_TOLERANCE_UNITS,
       IFF(ABS(PLANNED_CAPACITY_UNITS_RAW
             - RECONSTRUCTED_CAPACITY_UNITS_RAW)<=0.000001,
           'PASS','FAIL') AS RESULT
FROM rolled ORDER BY IFF(GRAIN='SITE',0,1),SUBJECT;

/* 4b. Counter-sampling artefact disclosure; informational, not a failure. */
SELECT SUBJECT,
       MAX(DAYS_OUTPUT_ABOVE_RUNNING_THEORETICAL)
         AS DAYS_OUTPUT_ABOVE_RUNNING_THEORETICAL,
       'INFORMATIONAL_DISCLOSURE' AS CHECK_TYPE,
       'PASS' AS RESULT
FROM GOLD.V_OEE_LOSS_ATTRIBUTION
GROUP BY SUBJECT ORDER BY SUBJECT;

/* 5. Site-to-line presentation rollups. Actual output compares five line
      values with one site value, so whole-package display rounding permits a
      measured 3-package bound. Signed loss compares fifteen line buckets with
      three site buckets, so its measured bound is 9 packages. Five line cents
      plus one site cent permit a 0.03-EUR bound. */
WITH checks AS (
  SELECT 'MARGIN_ACTUAL_UNITS_SITE_EQUALS_LINES' CHECK_NAME,
    (SELECT SUM(ACTUAL_OUTPUT_UNITS) FROM GOLD.V_MARGIN_SCENARIO_BASE
     WHERE GRAIN='LINE') LINE_TOTAL,
    (SELECT ACTUAL_OUTPUT_UNITS FROM GOLD.V_MARGIN_SCENARIO_BASE
     WHERE GRAIN='SITE') SITE_TOTAL,
    3.00 TOLERANCE
  UNION ALL
  SELECT 'CLAMPED_MARGIN_SITE_EQUALS_LINES',
    (SELECT SUM(SCENARIO_CLAMPED_SHORTFALL_MARGIN_EUR)
     FROM GOLD.V_MARGIN_SCENARIO_BASE WHERE GRAIN='LINE'),
    (SELECT SCENARIO_CLAMPED_SHORTFALL_MARGIN_EUR
     FROM GOLD.V_MARGIN_SCENARIO_BASE WHERE GRAIN='SITE'),
    0.03
  UNION ALL
  SELECT 'SIGNED_LOSS_UNITS_SITE_EQUALS_LINES',
    (SELECT SUM(FORGONE_UNITS) FROM GOLD.V_OEE_LOSS_ATTRIBUTION
     WHERE GRAIN='LINE'),
    (SELECT SUM(FORGONE_UNITS) FROM GOLD.V_OEE_LOSS_ATTRIBUTION
     WHERE GRAIN='SITE'),
    9.00
)
SELECT *, LINE_TOTAL-SITE_TOTAL AS DIFFERENCE,
       IFF(ABS(LINE_TOTAL-SITE_TOTAL)<=TOLERANCE,'PASS','FAIL') RESULT
FROM checks;

/* 6. Levers are a one-to-one projection of line losses. */
WITH c AS (
  SELECT
    (SELECT COUNT(*) FROM GOLD.V_IMPROVEMENT_LEVERS) LEVER_ROWS,
    (SELECT COUNT(*) FROM GOLD.V_OEE_LOSS_ATTRIBUTION
     WHERE GRAIN='LINE') EXPECTED_ROWS,
    (SELECT SUM(SCENARIO_SIGNED_LOSS_MARGIN_EUR)
     FROM GOLD.V_IMPROVEMENT_LEVERS)
    -(SELECT SUM(SCENARIO_SIGNED_LOSS_MARGIN_EUR)
      FROM GOLD.V_OEE_LOSS_ATTRIBUTION WHERE GRAIN='LINE') MARGIN_DRIFT_EUR,
    (SELECT COUNT(*)-COUNT(DISTINCT LEVER_RANK)
     FROM GOLD.V_IMPROVEMENT_LEVERS) DUPLICATE_RANKS,
    (SELECT COUNT(*)-COUNT(DISTINCT LEVER_ID)
     FROM GOLD.V_IMPROVEMENT_LEVERS) DUPLICATE_LEVER_IDS,
    (SELECT COUNT_IF(LOSS_BUCKET<>'MAINTENANCE_FAULT'
                     AND WORK_ORDERS IS NOT NULL)
     FROM GOLD.V_IMPROVEMENT_LEVERS) WO_FIELDS_OUTSIDE_MAINTENANCE,
    (SELECT COUNT_IF(LOSS_BUCKET<>'PLANNING_IDLE'
                     AND (IDLE_INCIDENTS IS NOT NULL
                          OR MEDIAN_IDLE_MINUTES IS NOT NULL))
     FROM GOLD.V_IMPROVEMENT_LEVERS) IDLE_FIELDS_OUTSIDE_PLANNING
)
SELECT *, IFF(LEVER_ROWS=EXPECTED_ROWS AND ABS(MARGIN_DRIFT_EUR)<=0.01
  AND DUPLICATE_RANKS=0 AND DUPLICATE_LEVER_IDS=0
  AND WO_FIELDS_OUTSIDE_MAINTENANCE=0 AND IDLE_FIELDS_OUTSIDE_PLANNING=0,
  'PASS','FAIL') RESULT
FROM c;

/* 7. The clamped production-order measure and signed OEE-loss measure are
      intentionally non-equivalent:
        - clamped: sum of daily MAX(target-output,0), already rounded by order;
        - signed: idle + fault + running residual from the consistent OEE path.
      Each is reconciled to its own source. Equality, if it happens, is only a
      numerical coincidence and does not make the definitions interchangeable. */
WITH cfg AS (
  SELECT MAX(IFF(NAME='ERP_MARGIN_PER_PACKAGE',VALUE,NULL)) MARGIN
  FROM GOLD.IT_ASSUMPTION
  WHERE ASSUMPTION_SET_ID='AS-PIADE-ERP-2026-09-25'
    AND PLANT_SCOPE='PLANT_B'
), measures AS (
  SELECT
    (SELECT SUM(MARGIN_EXPOSURE_EUR) FROM GOLD.PRODUCTION_ORDER)
      AS CLAMPED_SOURCE_EUR,
    (SELECT SCENARIO_CLAMPED_SHORTFALL_MARGIN_EUR
     FROM GOLD.V_MARGIN_SCENARIO_BASE WHERE GRAIN='SITE')
      AS CLAMPED_VIEW_EUR,
    (SELECT SUM(
       (d.IDLE_SEC+d.DOWNTIME_SEC+d.RUN_SEC)/3600.0*r.IDEAL_RATE_PPH
       -d.PACKAGES_OUT)*c.MARGIN
     FROM GOLD.PIADE_OEE_DAILY d
     JOIN GOLD.OEE_IDEAL_RATE r USING(MACHINE_KEY)
     CROSS JOIN cfg c
     WHERE d.PLANT_CODE='PLANT_B') AS SIGNED_SOURCE_EUR,
    (SELECT SUM(SCENARIO_SIGNED_LOSS_MARGIN_EUR)
     FROM GOLD.V_OEE_LOSS_ATTRIBUTION WHERE GRAIN='SITE')
      AS SIGNED_VIEW_EUR
)
SELECT *,
  CLAMPED_VIEW_EUR-SIGNED_VIEW_EUR AS CLAMPED_MINUS_SIGNED_EUR,
  IFF(ABS(CLAMPED_VIEW_EUR-SIGNED_VIEW_EUR)<=0.01,
      'COINCIDENTALLY_EQUAL_BUT_NON_EQUIVALENT',
      'NON_EQUIVALENT_VALUES') AS NUMERIC_RELATIONSHIP,
  'Clamped daily shortfall cannot offset over-target days; signed OEE loss can.'
    AS DEFINITION_RELATIONSHIP,
  IFF(ABS(CLAMPED_SOURCE_EUR-CLAMPED_VIEW_EUR)<=0.01
      AND ABS(SIGNED_SOURCE_EUR-SIGNED_VIEW_EUR)<=0.02,
      'PASS','FAIL') AS RESULT
FROM measures;

/* 8. Cross-path capacity check. Production orders round each daily target to
      a whole package. The daily OEE path sums hourly values where planned,
      run, downtime and idle were each rounded independently to 0.1 second.
      The explicit upper bound is therefore 0.5 package per order plus 0.2
      second x ideal rate per observed machine-hour. */
WITH c AS (
  SELECT
    (SELECT SUM(TARGET_OUTPUT_UNITS) FROM GOLD.PRODUCTION_ORDER)
      AS ERP_TARGET_UNITS,
    (SELECT SUM((d.RUN_SEC+d.DOWNTIME_SEC+d.IDLE_SEC)
                /3600.0*r.IDEAL_RATE_PPH)
     FROM GOLD.PIADE_OEE_DAILY d
     JOIN GOLD.OEE_IDEAL_RATE r USING(MACHINE_KEY)
     WHERE d.PLANT_CODE='PLANT_B') AS COMPONENT_CAPACITY_UNITS_RAW,
    (SELECT COUNT(*)*0.5
            +SUM(d.HOURS_OBSERVED*0.2/3600.0*r.IDEAL_RATE_PPH)
     FROM GOLD.PIADE_OEE_DAILY d
     JOIN GOLD.OEE_IDEAL_RATE r USING(MACHINE_KEY)
     WHERE d.PLANT_CODE='PLANT_B') AS EXPLICIT_ROUNDING_BOUND_UNITS
)
SELECT *, ERP_TARGET_UNITS-COMPONENT_CAPACITY_UNITS_RAW DIFFERENCE_UNITS,
       IFF(ABS(ERP_TARGET_UNITS-COMPONENT_CAPACITY_UNITS_RAW)
           <=EXPLICIT_ROUNDING_BOUND_UNITS,'PASS','FAIL') RESULT
FROM c;

/* 9. Lineage, origin and claim vocabulary. Model estimates get a distinct
      origin; no wide row containing scenario money may claim to be a derived
      actual. */
WITH c AS (
  SELECT
    (SELECT COUNT_IF(SOURCE_VIEW IS NULL)
     FROM GOLD.V_ANALYST_DECISION_CONTEXT) ROWS_WITHOUT_SOURCE,
    (SELECT COUNT_IF(DATA_ORIGIN IS NULL)
     FROM GOLD.V_ANALYST_DECISION_CONTEXT) ROWS_WITHOUT_ORIGIN,
    (SELECT COUNT_IF(AS_OF_TS IS NULL)
     FROM GOLD.V_ANALYST_DECISION_CONTEXT) ROWS_WITHOUT_AS_OF,
    (SELECT COUNT_IF(METRIC_VALUE_NUM IS NULL AND METRIC_VALUE_TEXT IS NULL)
     FROM GOLD.V_ANALYST_DECISION_CONTEXT) ROWS_WITHOUT_VALUE,
    (SELECT COUNT_IF(EVIDENCE_NOTE IS NULL)
     FROM GOLD.V_ANALYST_DECISION_CONTEXT) ROWS_WITHOUT_EVIDENCE,
    (SELECT COUNT_IF(CLAIM_CLASS NOT IN
      ('OBSERVED','DERIVED_FROM_OBSERVED','MODEL_ESTIMATE','SCENARIO',
       'SCENARIO_ASSUMPTION','NON_CLAIM'))
     FROM GOLD.V_ANALYST_DECISION_CONTEXT) UNKNOWN_CLAIM_CLASSES,
    (SELECT COUNT_IF(DATA_ORIGIN NOT IN
      ('OBSERVED','DERIVED_FROM_OBSERVED','MODEL_DERIVED_FROM_OBSERVED',
       'SYNTHETIC_IT','SYNTHETIC_ERP','NOT_DATA'))
     FROM GOLD.V_ANALYST_DECISION_CONTEXT) UNKNOWN_ORIGINS,
    (SELECT COUNT_IF(CLAIM_CLASS<>'SCENARIO')
     FROM GOLD.V_MARGIN_SCENARIO_BASE) MARGIN_WIDE_ROWS_NOT_SCENARIO,
    (SELECT COUNT_IF(CLAIM_CLASS<>'SCENARIO')
     FROM GOLD.V_OEE_LOSS_ATTRIBUTION) LOSS_WIDE_ROWS_NOT_SCENARIO,
    (SELECT COUNT_IF(CLAIM_CLASS<>'SCENARIO')
     FROM GOLD.V_IMPROVEMENT_LEVERS) LEVER_WIDE_ROWS_NOT_SCENARIO,
    (SELECT COUNT_IF(SOURCE_VIEW ILIKE '%V_IMPROVEMENT_LEVERS%')
     FROM GOLD.V_IMPROVEMENT_LEVERS) SELF_CITED_LEVERS
)
SELECT *, IFF(ROWS_WITHOUT_SOURCE=0 AND ROWS_WITHOUT_ORIGIN=0
  AND ROWS_WITHOUT_AS_OF=0 AND ROWS_WITHOUT_VALUE=0
  AND ROWS_WITHOUT_EVIDENCE=0 AND UNKNOWN_CLAIM_CLASSES=0
  AND UNKNOWN_ORIGINS=0 AND MARGIN_WIDE_ROWS_NOT_SCENARIO=0
  AND LOSS_WIDE_ROWS_NOT_SCENARIO=0 AND LEVER_WIDE_ROWS_NOT_SCENARIO=0
  AND SELF_CITED_LEVERS=0,'PASS','FAIL') RESULT
FROM c;

/* 10. Monetary context must be synthetic/scenario; model estimates must use
       model-derived origin; observed units must not be marked synthetic. */
WITH c AS (
  SELECT
    COUNT_IF(UNIT='EUR'
      AND (DATA_ORIGIN NOT IN ('SYNTHETIC_ERP','SYNTHETIC_IT')
           OR CLAIM_CLASS NOT IN ('SCENARIO','SCENARIO_ASSUMPTION')))
      AS INVALID_MONETARY_ROWS,
    COUNT_IF(CLAIM_CLASS='MODEL_ESTIMATE'
      AND DATA_ORIGIN<>'MODEL_DERIVED_FROM_OBSERVED') AS INVALID_MODEL_ORIGINS,
    COUNT_IF(TOPIC<>'ASSUMPTION' AND UNIT IN ('hours','packages')
      AND DATA_ORIGIN IN ('SYNTHETIC_ERP','SYNTHETIC_IT'))
      AS OBSERVED_UNITS_MARKED_SYNTHETIC
  FROM GOLD.V_ANALYST_DECISION_CONTEXT
)
SELECT *, IFF(INVALID_MONETARY_ROWS=0 AND INVALID_MODEL_ORIGINS=0
  AND OBSERVED_UNITS_MARKED_SYNTHETIC=0,'PASS','FAIL') RESULT
FROM c;

/* 11. Assumption context completeness and consumer accuracy sentinels. */
WITH c AS (
  SELECT
    (SELECT COUNT(*) FROM GOLD.V_ASSUMPTIONS_ACTIVE) ACTIVE_ASSUMPTIONS,
    (SELECT COUNT(*) FROM GOLD.V_ANALYST_DECISION_CONTEXT
     WHERE TOPIC='ASSUMPTION') ASSUMPTIONS_IN_CONTEXT,
    (SELECT COUNT_IF(BASIS IS NULL) FROM GOLD.V_ASSUMPTIONS_ACTIVE)
      ASSUMPTIONS_WITHOUT_BASIS,
    (SELECT COUNT_IF(CONSUMED_BY IS NULL OR CONSUMED_BY='')
     FROM GOLD.V_ASSUMPTIONS_ACTIVE) ASSUMPTIONS_WITHOUT_CONSUMER_STATUS,
    (SELECT COUNT_IF(ASSUMPTION_NAME IN
       ('ERP_LEAD_TIME_MIN_DAYS','ERP_LEAD_TIME_MAX_DAYS',
        'WORK_ORDER_MIN_BREAKDOWN_MINUTES','IDLE_INCIDENT_MIN_MINUTES')
       AND CONSUMED_BY NOT LIKE 'NOT_CONSUMED:%')
     FROM GOLD.V_ASSUMPTIONS_ACTIVE) MISLABELLED_DOCUMENTED_CONSTANTS
)
SELECT *, IFF(ACTIVE_ASSUMPTIONS=ASSUMPTIONS_IN_CONTEXT
  AND ASSUMPTIONS_WITHOUT_BASIS=0
  AND ASSUMPTIONS_WITHOUT_CONSUMER_STATUS=0
  AND MISLABELLED_DOCUMENTED_CONSTANTS=0,'PASS','FAIL') RESULT
FROM c;

/* ==========================================================================
   Reports.
   ========================================================================== */

SELECT ASSUMPTION_SET_ID, ASSUMPTION_NAME, ASSUMPTION_VALUE, UNIT, EVIDENCE_CLASS,
       CONSUMED_BY
FROM GOLD.V_ASSUMPTIONS_ACTIVE
ORDER BY ASSUMPTION_SET_ID, ASSUMPTION_NAME;

SELECT GRAIN, SUBJECT, ACTUAL_OUTPUT_UNITS, TARGET_OUTPUT_UNITS, OUTPUT_SHORTFALL_UNITS,
       ATTAINMENT_PCT, SCENARIO_CLAMPED_SHORTFALL_MARGIN_EUR, MONEY_ORIGIN
FROM GOLD.V_MARGIN_SCENARIO_BASE
ORDER BY IFF(GRAIN = 'SITE', 0, 1), SUBJECT;

SELECT GRAIN, SUBJECT, LOSS_BUCKET, OWNER_FUNCTION, LOSS_HOURS, FORGONE_UNITS,
       PCT_OF_SUBJECT_FORGONE, SCENARIO_SIGNED_LOSS_MARGIN_EUR
FROM GOLD.V_OEE_LOSS_ATTRIBUTION
ORDER BY IFF(GRAIN = 'SITE', 0, 1), SUBJECT, LOSS_BUCKET;

SELECT LEVER_RANK, LEVER_ID, OWNER_FUNCTION, OBSERVED_LOSS_HOURS,
       OBSERVED_FORGONE_PACKAGES, PCT_OF_SITE_BUCKET_LOSS, TOP_CONTRIBUTING_CAUSE,
       TOP_CAUSE_PCT_OF_BUCKET_TIME, SCENARIO_SIGNED_LOSS_MARGIN_EUR, LAST_RISK_BAND
FROM GOLD.V_IMPROVEMENT_LEVERS
ORDER BY LEVER_RANK;

SELECT TOPIC, SUBJECT, METRIC_NAME, METRIC_VALUE_NUM, METRIC_VALUE_TEXT, UNIT,
       CLAIM_CLASS, DATA_ORIGIN, SOURCE_VIEW, AS_OF_TS
FROM GOLD.V_ANALYST_DECISION_CONTEXT
ORDER BY TOPIC_SORT, SUBJECT, METRIC_NAME;

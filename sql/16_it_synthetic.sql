/* ============================================================================
   The IT layer — work orders, technicians and cost.

   THIS DATA IS INVENTED. Every row below carries DATA_ORIGIN = 'SYNTHETIC_IT'
   and the application must show that on screen wherever these figures appear.
   No public dataset ships factory sensors together with the maintenance
   tickets and costs that followed, so this is the one place where fabrication
   is unavoidable. The rules that constrain it are:

   1. Every work order is anchored to a real observed event on its own plant.
      There is a foreign key to that event and the count is checked. No order
      exists without an event behind it.
   2. Nothing crosses between plants. Plant A's orders come from Plant A's
      alarms and Plant B's from Plant B's stops. The two plants are different
      factories with no published relationship, and blending them would
      manufacture a connection that does not exist.
   3. No failure is invented. The generator adds cost, labour and paperwork to
      events that genuinely happened; it never adds an event.
   4. Nothing is random at runtime. Variation comes from HASH of the work
      order id, so re-running produces byte-identical output. RANDOM() is
      never used, because a dashboard whose numbers move between refreshes
      cannot be checked by anyone.
   5. Every constant lives in GOLD.IT_ASSUMPTION with a stated basis, and is
      marked as measured from the source or simply chosen.

   EVENT THRESHOLDS, MEASURED NOT GUESSED (scripts/probe_it_event_basis.py)

   Plant B has 142,233 unplanned stops totalling 13,413 hours, but a median
   stop lasts 0.98 minutes. Raising a ticket for a one-minute micro-stop would
   be fiction, so a threshold is needed and the candidates were counted:

     threshold   orders   per machine per day   share of stop time
       5 min     17,310          4.74                 82.8%
      10 min     10,176          2.78                 76.6%
      30 min      4,061          1.11                 64.1%
      60 min      2,383          0.65                 55.4%

   30 minutes is used. It yields roughly one order per machine per day, which
   is a plausible corrective workload, while still accounting for 64% of all
   unplanned stop time.

   An uncomfortable fact that is kept rather than hidden: 3,592 of those 4,061
   stops carry alarm code A_000, the publisher's placeholder for no alarm. So
   88% of the longest stops on Plant B have no recorded cause. That is a real
   property of the source and becomes CAUSE_CODE = 'UNDIAGNOSED'.

   Plant A's 1,555 module-alarm windows merge into 1,042 incidents once
   consecutive windows within 30 minutes are treated as one event. Median
   incident is a single 10-minute window; the longest runs 230 minutes.

   WHAT THIS CANNOT DO

   Plant A has no production counts of any kind. Lost output therefore cannot
   be costed for Plant A, and LOST_PRODUCTION_COST is NULL there rather than
   filled with a plausible number. Plant A's financial view is labour and
   parts only, and the app must say so instead of showing a smaller bar.
   ========================================================================= */

USE ROLE ACCOUNTADMIN;
USE DATABASE SNOWCORE_REAL;
USE WAREHOUSE COMPUTE_WH;
ALTER SESSION SET TIMEZONE = 'UTC';
ALTER SESSION SET QUERY_TAG = 'snowcore-real|coco|it-synthetic';

/* --------------------------------------------------------------------------
   Assumptions. Displayed in the application, not buried here.

   IS_MEASURED separates the two kinds of number in this file. A measured
   assumption was counted from the source data. A chosen one was picked by us
   and has no basis in either dataset; those are the ones a reviewer should
   attack first, and they are labelled so the reviewer can find them.
   -------------------------------------------------------------------------- */

CREATE OR REPLACE TABLE GOLD.IT_ASSUMPTION (
  ASSUMPTION_SET_ID  VARCHAR,
  PLANT_SCOPE        VARCHAR,
  NAME               VARCHAR,
  VALUE              FLOAT,
  UNIT               VARCHAR,
  IS_MEASURED        BOOLEAN,
  BASIS              VARCHAR
);

INSERT INTO GOLD.IT_ASSUMPTION
  (ASSUMPTION_SET_ID, PLANT_SCOPE, NAME, VALUE, UNIT, IS_MEASURED, BASIS)
VALUES
  ('AS-2026-09-24', 'PLANT_B', 'WORK_ORDER_MIN_STOP_MINUTES', 30, 'minutes', TRUE,
   'Chosen from a measured sweep: yields 4,061 orders, 1.11 per machine per day, covering 64.1% of unplanned stop time.'),
  ('AS-2026-09-24', 'PLANT_A', 'INCIDENT_MERGE_GAP_MINUTES', 30, 'minutes', TRUE,
   'Merges 1,555 module-alarm windows into 1,042 incidents. Below this gap, consecutive windows are the same event still running.'),
  ('AS-2026-09-24', 'BOTH', 'LABOUR_RATE_PER_HOUR', 45, 'EUR/hour', FALSE,
   'Chosen. Neither dataset records labour cost, rates, or even a currency. EUR is used because both datasets are European in origin.'),
  ('AS-2026-09-24', 'BOTH', 'RESPONSE_MINUTES_MIN', 8, 'minutes', FALSE,
   'Chosen. Time from a stop being recorded to a technician arriving. Nothing in either source measures this.'),
  ('AS-2026-09-24', 'BOTH', 'RESPONSE_MINUTES_MAX', 35, 'minutes', FALSE,
   'Chosen. Upper end of the same response window.'),
  ('AS-2026-09-24', 'PLANT_B', 'WRENCH_TIME_FRACTION', 0.75, 'fraction', FALSE,
   'Chosen. Share of a recorded stop assumed to be hands-on repair rather than waiting. Not derivable from the source.'),
  ('AS-2026-09-24', 'PLANT_A', 'INCIDENT_LABOUR_MINUTES', 45, 'minutes', FALSE,
   'Chosen. Plant A records no stop duration at all, only that an alarm occurred, so repair time cannot be derived and a flat allowance is used.'),
  ('AS-2026-09-24', 'BOTH', 'PARTS_COST_MAX', 850, 'EUR', FALSE,
   'Chosen. Upper bound for a line-side corrective repair. No parts catalogue exists in either source.'),
  /* The first version drew a parts cost for every order regardless of how
     serious it was. That put an average of 291 EUR of spares behind Plant A's
     typical ten-minute alarm blip and made parts eight times its labour bill,
     which is not how a maintenance store behaves. Parts are now conditional:
     most short jobs consume nothing, and the chance of needing a part rises
     with the length of the stop. */
  ('AS-2026-09-24', 'BOTH', 'PARTS_PROBABILITY_P4', 0.10, 'probability', FALSE,
   'Chosen. Chance that a job under one hour consumes any spare part at all.'),
  ('AS-2026-09-24', 'BOTH', 'PARTS_PROBABILITY_P3', 0.30, 'probability', FALSE,
   'Chosen. One to two hours.'),
  ('AS-2026-09-24', 'BOTH', 'PARTS_PROBABILITY_P2', 0.55, 'probability', FALSE,
   'Chosen. Two to four hours.'),
  ('AS-2026-09-24', 'BOTH', 'PARTS_PROBABILITY_P1', 0.80, 'probability', FALSE,
   'Chosen. Four hours or more; a stop this long usually means something was replaced.'),
  ('AS-2026-09-24', 'PLANT_B', 'CONTRIBUTION_MARGIN_PER_PACKAGE', 0.18, 'EUR/package', FALSE,
   'Chosen. Used only to convert lost packages into money. The lost package count itself is derived from observed ideal rate and observed stop duration.'),
  ('AS-2026-09-24', 'PLANT_A', 'CONTRIBUTION_MARGIN_PER_PACKAGE', NULL, 'EUR/package', FALSE,
   'Deliberately absent. Plant A publishes no production counts, so lost output cannot be costed and is left NULL rather than estimated.');

COMMENT ON TABLE GOLD.IT_ASSUMPTION IS
  'Every constant behind the synthetic IT layer. IS_MEASURED false means the number was chosen by us and has no basis in the source data.';

/* --------------------------------------------------------------------------
   Technicians. Synthetic, and separate per plant because the two plants are
   different companies.
   -------------------------------------------------------------------------- */

CREATE OR REPLACE TABLE GOLD.DIM_TECHNICIAN AS
SELECT
  PLANT_CODE,
  PLANT_CODE || '-T' || LPAD(SEQ::VARCHAR, 2, '0') AS TECHNICIAN_ID,
  TECH_NAME,
  SHIFT,
  SPECIALITY,
  'SYNTHETIC_IT'                                   AS DATA_ORIGIN
FROM (
  SELECT 'PLANT_A' AS PLANT_CODE, 1 AS SEQ, 'Alvarez'  AS TECH_NAME, 'EARLY' AS SHIFT, 'Mechanical' AS SPECIALITY UNION ALL
  SELECT 'PLANT_A', 2, 'Baptista', 'EARLY', 'Electrical'      UNION ALL
  SELECT 'PLANT_A', 3, 'Costa',    'LATE',  'Mechanical'      UNION ALL
  SELECT 'PLANT_A', 4, 'Duarte',   'LATE',  'Controls'        UNION ALL
  SELECT 'PLANT_A', 5, 'Esteves',  'NIGHT', 'Mechanical'      UNION ALL
  SELECT 'PLANT_A', 6, 'Ferreira', 'NIGHT', 'Electrical'      UNION ALL
  SELECT 'PLANT_B', 1, 'Bianchi',  'EARLY', 'Mechanical'      UNION ALL
  SELECT 'PLANT_B', 2, 'Colombo',  'EARLY', 'Controls'        UNION ALL
  SELECT 'PLANT_B', 3, 'Esposito', 'LATE',  'Mechanical'      UNION ALL
  SELECT 'PLANT_B', 4, 'Ferrari',  'LATE',  'Electrical'      UNION ALL
  SELECT 'PLANT_B', 5, 'Greco',    'NIGHT', 'Mechanical'      UNION ALL
  SELECT 'PLANT_B', 6, 'Lombardi', 'NIGHT', 'Controls'
);

COMMENT ON TABLE GOLD.DIM_TECHNICIAN IS
  'Invented maintenance staff. No person in either published dataset is identified, and none is implied here.';

/* --------------------------------------------------------------------------
   Work orders.

   Both plants are built in one statement so the cost arithmetic is written
   once, but the two sources never meet: PLANT_CODE is fixed inside each arm
   of the UNION and no join crosses it.

   Every pseudo-random quantity is a HASH of the work order id with a distinct
   salt per quantity, so the draws are independent of each other and identical
   on every re-run.
   -------------------------------------------------------------------------- */

CREATE OR REPLACE TABLE GOLD.WORK_ORDER AS
WITH cfg AS (
  SELECT
    MAX(IFF(NAME = 'LABOUR_RATE_PER_HOUR', VALUE, NULL))            AS LABOUR_RATE,
    MAX(IFF(NAME = 'RESPONSE_MINUTES_MIN', VALUE, NULL))            AS RESP_MIN,
    MAX(IFF(NAME = 'RESPONSE_MINUTES_MAX', VALUE, NULL))            AS RESP_MAX,
    MAX(IFF(NAME = 'WRENCH_TIME_FRACTION', VALUE, NULL))            AS WRENCH,
    MAX(IFF(NAME = 'INCIDENT_LABOUR_MINUTES', VALUE, NULL))         AS INCIDENT_LABOUR,
    MAX(IFF(NAME = 'PARTS_COST_MAX', VALUE, NULL))                  AS PARTS_MAX,
    MAX(IFF(NAME = 'PARTS_PROBABILITY_P4', VALUE, NULL))            AS P_PARTS_P4,
    MAX(IFF(NAME = 'PARTS_PROBABILITY_P3', VALUE, NULL))            AS P_PARTS_P3,
    MAX(IFF(NAME = 'PARTS_PROBABILITY_P2', VALUE, NULL))            AS P_PARTS_P2,
    MAX(IFF(NAME = 'PARTS_PROBABILITY_P1', VALUE, NULL))            AS P_PARTS_P1,
    MAX(IFF(NAME = 'CONTRIBUTION_MARGIN_PER_PACKAGE'
            AND PLANT_SCOPE = 'PLANT_B', VALUE, NULL))              AS MARGIN_B
  FROM GOLD.IT_ASSUMPTION
  WHERE ASSUMPTION_SET_ID = 'AS-2026-09-24'
),

/* ---- Plant B: one order per unplanned stop of 30 minutes or more ---- */
b_events AS (
  SELECT
    'PLANT_B'                                   AS PLANT_CODE,
    e.MACHINE_KEY,
    e.MACHINE_CODE,
    'UNPLANNED_STOP'                            AS SOURCE_EVENT_TYPE,
    e.STOP_START                                AS EVENT_START,
    e.STOP_END                                  AS EVENT_END,
    e.STOP_DURATION_MIN                         AS EVENT_DURATION_MIN,
    /* A_000 is the publisher's placeholder for "no alarm was active". */
    IFF(e.ALARM_CODE = 'A_000', 'UNDIAGNOSED', e.ALARM_CODE) AS CAUSE_CODE,
    e.STOP_STATE                                AS EVENT_DETAIL,
    r.IDEAL_RATE_PPH
  FROM GOLD.PIADE_DOWNTIME_EVENT e
  JOIN GOLD.OEE_IDEAL_RATE r USING (MACHINE_KEY)
  WHERE e.STOP_DURATION_MIN >= 30
),

/* ---- Plant A: one order per merged module-alarm incident ---- */
a_hits AS (
  SELECT MACHINE_KEY, MACHINE_CODE, TIME_UTC, MODULE_ALARM_COUNT
  FROM SILVER.COMOPI_ALARM_10MIN
  WHERE IS_MODULE_ALARM
),
a_marked AS (
  SELECT *,
    IFF(
      DATEDIFF('second',
        LAG(TIME_UTC) OVER (PARTITION BY MACHINE_KEY ORDER BY TIME_UTC),
        TIME_UTC) > 1800
      OR LAG(TIME_UTC) OVER (PARTITION BY MACHINE_KEY ORDER BY TIME_UTC) IS NULL,
      1, 0) AS IS_NEW_INCIDENT
  FROM a_hits
),
a_grouped AS (
  SELECT *,
    SUM(IS_NEW_INCIDENT) OVER (
      PARTITION BY MACHINE_KEY ORDER BY TIME_UTC
      ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS INCIDENT_NO
  FROM a_marked
),
a_events AS (
  SELECT
    'PLANT_A'                                        AS PLANT_CODE,
    MACHINE_KEY,
    ANY_VALUE(MACHINE_CODE)                          AS MACHINE_CODE,
    'MODULE_ALARM_INCIDENT'                          AS SOURCE_EVENT_TYPE,
    MIN(TIME_UTC)                                    AS EVENT_START,
    /* Each window covers ten minutes, so the incident ends ten minutes after
       the last window begins. */
    DATEADD('minute', 10, MAX(TIME_UTC))             AS EVENT_END,
    DATEDIFF('minute', MIN(TIME_UTC), MAX(TIME_UTC)) + 10 AS EVENT_DURATION_MIN,
    'MODULE_ALARM'                                   AS CAUSE_CODE,
    SUM(MODULE_ALARM_COUNT)::VARCHAR || ' alarm activations across '
      || COUNT(*)::VARCHAR || ' ten-minute windows'  AS EVENT_DETAIL,
    CAST(NULL AS FLOAT)                              AS IDEAL_RATE_PPH
  FROM a_grouped
  GROUP BY MACHINE_KEY, INCIDENT_NO
),

events AS (
  SELECT * FROM b_events
  UNION ALL
  SELECT * FROM a_events
),

keyed AS (
  SELECT
    e.*,
    /* Deterministic id. Ordering is by plant, machine and time, all of which
       are stable, so the same event always gets the same number. */
    'WO-' || SUBSTR(e.PLANT_CODE, 7, 1) || '-'
      || LPAD(ROW_NUMBER() OVER (
           PARTITION BY e.PLANT_CODE ORDER BY e.MACHINE_CODE, e.EVENT_START
         )::VARCHAR, 6, '0')                          AS WORK_ORDER_ID
  FROM events e
),

drawn AS (
  SELECT
    k.*,
    c.LABOUR_RATE, c.RESP_MIN, c.RESP_MAX, c.WRENCH,
    c.INCIDENT_LABOUR, c.PARTS_MAX, c.MARGIN_B,
    c.P_PARTS_P4, c.P_PARTS_P3, c.P_PARTS_P2, c.P_PARTS_P1,
    /* Independent uniform draws in [0,1). Snowflake's HASH takes one
       argument, so each draw gets its own salt by concatenation rather than
       a second parameter. */
    (ABS(HASH(k.WORK_ORDER_ID || 'response')) % 10000) / 10000.0  AS U_RESPONSE,
    (ABS(HASH(k.WORK_ORDER_ID || 'parts'))    % 10000) / 10000.0  AS U_PARTS,
    (ABS(HASH(k.WORK_ORDER_ID || 'needsparts')) % 10000) / 10000.0 AS U_NEEDS_PARTS,
    (ABS(HASH(k.WORK_ORDER_ID || 'tech'))     % 6)                AS TECH_SLOT
  FROM keyed k
  CROSS JOIN cfg c
),

costed AS (
  SELECT
    d.*,
    ROUND(d.RESP_MIN + d.U_RESPONSE * (d.RESP_MAX - d.RESP_MIN), 1) AS RESPONSE_MIN,
    CASE d.PLANT_CODE
      /* Plant B records how long the machine was down, so repair time is a
         fraction of that. Plant A records only that an alarm fired, so a flat
         allowance is the only defensible choice. */
      WHEN 'PLANT_B' THEN ROUND(d.EVENT_DURATION_MIN * d.WRENCH, 1)
      ELSE d.INCIDENT_LABOUR
    END                                                           AS LABOUR_MIN,
    /* Two stages. First, did this job need a part at all — a chance that
       rises with the length of the stop. Only then is a cost drawn, squared
       so that most of those jobs sit near the cheap end and a few reach the
       cap, which is how corrective spend actually distributes. */
    IFF(
      d.U_NEEDS_PARTS < CASE
        WHEN d.EVENT_DURATION_MIN >= 240 THEN d.P_PARTS_P1
        WHEN d.EVENT_DURATION_MIN >= 120 THEN d.P_PARTS_P2
        WHEN d.EVENT_DURATION_MIN >=  60 THEN d.P_PARTS_P3
        ELSE d.P_PARTS_P4
      END,
      ROUND(POWER(d.U_PARTS, 2) * d.PARTS_MAX, 2),
      0
    )                                                             AS PARTS_COST
  FROM drawn d
)

SELECT
  c.WORK_ORDER_ID,
  c.PLANT_CODE,
  c.MACHINE_KEY,
  c.MACHINE_CODE,
  c.SOURCE_EVENT_TYPE,
  c.EVENT_START                                                   AS SOURCE_EVENT_START,
  c.EVENT_END                                                     AS SOURCE_EVENT_END,
  c.EVENT_DURATION_MIN                                            AS SOURCE_EVENT_MINUTES,
  c.CAUSE_CODE,
  c.EVENT_DETAIL,

  /* Lifecycle. Reported when the event began; everything after is derived. */
  c.EVENT_START                                                   AS REPORTED_AT,
  DATEADD('minute', c.RESPONSE_MIN::INT, c.EVENT_START)           AS STARTED_AT,
  DATEADD('minute', (c.RESPONSE_MIN + c.LABOUR_MIN)::INT, c.EVENT_START)
                                                                  AS COMPLETED_AT,
  c.RESPONSE_MIN,
  c.LABOUR_MIN,
  'COMPLETED'                                                     AS STATUS,
  CASE
    WHEN c.EVENT_DURATION_MIN >= 240 THEN 'P1'
    WHEN c.EVENT_DURATION_MIN >= 120 THEN 'P2'
    WHEN c.EVENT_DURATION_MIN >=  60 THEN 'P3'
    ELSE 'P4'
  END                                                             AS PRIORITY,
  t.TECHNICIAN_ID,
  t.TECH_NAME,
  t.SPECIALITY,

  /* Cost. */
  ROUND(c.LABOUR_MIN / 60.0 * c.LABOUR_RATE, 2)                   AS LABOUR_COST,
  c.PARTS_COST,
  /* Lost output, Plant B only. The package count is derived from an observed
     ideal rate and an observed stop duration; only the margin is invented. */
  IFF(c.PLANT_CODE = 'PLANT_B',
      ROUND(c.EVENT_DURATION_MIN / 60.0 * c.IDEAL_RATE_PPH, 0),
      NULL)                                                       AS LOST_PACKAGES,
  IFF(c.PLANT_CODE = 'PLANT_B',
      ROUND(c.EVENT_DURATION_MIN / 60.0 * c.IDEAL_RATE_PPH * c.MARGIN_B, 2),
      NULL)                                                       AS LOST_PRODUCTION_COST,
  ROUND(
    c.LABOUR_MIN / 60.0 * c.LABOUR_RATE
    + c.PARTS_COST
    + COALESCE(IFF(c.PLANT_CODE = 'PLANT_B',
        c.EVENT_DURATION_MIN / 60.0 * c.IDEAL_RATE_PPH * c.MARGIN_B, NULL), 0)
  , 2)                                                            AS TOTAL_COST,
  IFF(c.PLANT_CODE = 'PLANT_A',
      'Plant A publishes no production counts, so lost output is not costed.',
      NULL)                                                       AS COST_LIMITATION,

  'SYNTHETIC_IT'                                                  AS DATA_ORIGIN,
  'AS-2026-09-24'                                                 AS ASSUMPTION_SET_ID,
  'gen-v1'                                                        AS GENERATOR_VERSION
FROM costed c
JOIN GOLD.DIM_TECHNICIAN t
  ON  t.PLANT_CODE    = c.PLANT_CODE
  AND t.TECHNICIAN_ID = c.PLANT_CODE || '-T' || LPAD((c.TECH_SLOT + 1)::VARCHAR, 2, '0');

COMMENT ON TABLE GOLD.WORK_ORDER IS
  'INVENTED maintenance records. Each row is anchored to one real observed event on its own plant; no event is invented and nothing crosses between plants. Costs rest on GOLD.IT_ASSUMPTION.';

/* ==========================================================================
   Verification. The first two are the ones that matter: if either fails, the
   generator has invented something.
   ========================================================================== */

/* 1. Counts against the events they came from. Plant B must equal the number
      of unplanned stops of 30 minutes or more, measured offline as 4,061.
      Plant A must equal the merged incident count, measured as 1,042. */
SELECT
  'PLANT_B expected (stops >= 30 min)' AS CHECK_NAME,
  (SELECT COUNT(*) FROM GOLD.PIADE_DOWNTIME_EVENT WHERE STOP_DURATION_MIN >= 30) AS EXPECTED,
  (SELECT COUNT(*) FROM GOLD.WORK_ORDER WHERE PLANT_CODE = 'PLANT_B')            AS ACTUAL
UNION ALL
SELECT
  'PLANT_A expected (merged incidents)',
  1042,
  (SELECT COUNT(*) FROM GOLD.WORK_ORDER WHERE PLANT_CODE = 'PLANT_A');

/* 2. No orphans and no crossing. Every order must sit inside its own plant's
      observed time range and reference a machine that plant actually has. */
SELECT
  w.PLANT_CODE,
  COUNT(*)                                                    AS ORDERS,
  COUNT(DISTINCT w.MACHINE_KEY)                               AS MACHINES,
  SUM(IFF(m.MACHINE_KEY IS NULL, 1, 0))                       AS UNKNOWN_MACHINES,
  SUM(IFF(w.MACHINE_KEY NOT LIKE w.PLANT_CODE || ':%', 1, 0)) AS CROSS_PLANT_ROWS,
  MIN(w.REPORTED_AT)                                          AS FIRST_ORDER,
  MAX(w.REPORTED_AT)                                          AS LAST_ORDER
FROM GOLD.WORK_ORDER w
LEFT JOIN SILVER.DIM_MACHINE m ON m.MACHINE_KEY = w.MACHINE_KEY
GROUP BY w.PLANT_CODE;

/* 3. Cost shape. Plant A's LOST_PRODUCTION_COST must be entirely NULL — if it
      is not, output has been costed for a plant that publishes no output. */
SELECT
  PLANT_CODE,
  COUNT(*)                                        AS ORDERS,
  ROUND(SUM(LABOUR_COST), 2)                      AS LABOUR_TOTAL,
  ROUND(SUM(PARTS_COST), 2)                       AS PARTS_TOTAL,
  ROUND(SUM(LOST_PRODUCTION_COST), 2)             AS LOST_PRODUCTION_TOTAL,
  COUNT(LOST_PRODUCTION_COST)                     AS ROWS_WITH_LOST_PRODUCTION,
  ROUND(SUM(TOTAL_COST), 2)                       AS GRAND_TOTAL,
  ROUND(AVG(TOTAL_COST), 2)                       AS AVG_PER_ORDER,
  ROUND(MAX(TOTAL_COST), 2)                       AS MAX_ORDER
FROM GOLD.WORK_ORDER
GROUP BY PLANT_CODE;

/* 4. The uncomfortable one, kept in the open. How much of Plant B's
      corrective cost sits behind stops with no recorded cause? */
SELECT
  CAUSE_CODE,
  COUNT(*)                                        AS ORDERS,
  ROUND(SUM(SOURCE_EVENT_MINUTES) / 60.0, 1)      AS STOP_HOURS,
  ROUND(SUM(TOTAL_COST), 2)                       AS TOTAL_COST,
  ROUND(100.0 * SUM(TOTAL_COST)
        / SUM(SUM(TOTAL_COST)) OVER (), 2)        AS PCT_OF_PLANT_COST
FROM GOLD.WORK_ORDER
WHERE PLANT_CODE = 'PLANT_B'
GROUP BY CAUSE_CODE
ORDER BY TOTAL_COST DESC
LIMIT 12;

/* 5. Determinism. Re-deriving the draws from the stored ids must reproduce
      the stored values exactly. A non-zero MISMATCHES means something
      non-deterministic crept in and the whole table is unreproducible. */
SELECT
  COUNT(*)                                              AS ORDERS_CHECKED,
  SUM(IFF(ABS(RESPONSE_MIN
        - ROUND(8 + ((ABS(HASH(WORK_ORDER_ID || 'response')) % 10000) / 10000.0)
                * (35 - 8), 1)) > 0.05, 1, 0))          AS MISMATCHES
FROM GOLD.WORK_ORDER;

/* 5b. Parts should now be absent from most short jobs. If PCT_WITH_PARTS is
       near 100 in the P4 band, the two-stage draw did not take effect and the
       original implausible result is back. */
SELECT
  PLANT_CODE,
  PRIORITY,
  COUNT(*)                                              AS ORDERS,
  SUM(IFF(PARTS_COST > 0, 1, 0))                        AS ORDERS_WITH_PARTS,
  ROUND(100.0 * AVG(IFF(PARTS_COST > 0, 1, 0)), 1)      AS PCT_WITH_PARTS,
  ROUND(AVG(PARTS_COST), 2)                             AS AVG_PARTS_COST
FROM GOLD.WORK_ORDER
GROUP BY PLANT_CODE, PRIORITY
ORDER BY PLANT_CODE, PRIORITY;

/* 6. Priority mix, as a plausibility check rather than a correctness one.
      A distribution that is nearly all P1 would mean the thresholds are
      wrong for this data even though the arithmetic is right. */
SELECT PLANT_CODE, PRIORITY, COUNT(*) AS ORDERS,
       ROUND(AVG(SOURCE_EVENT_MINUTES), 1) AS AVG_EVENT_MINUTES
FROM GOLD.WORK_ORDER
GROUP BY PLANT_CODE, PRIORITY
ORDER BY PLANT_CODE, PRIORITY;

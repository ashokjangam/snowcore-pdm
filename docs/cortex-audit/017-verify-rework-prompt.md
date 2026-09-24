Verification only. Run queries, create nothing, change nothing.

Session setup first, re-asserted whenever context is lost. Use fully qualified
object names throughout, because context has been dropping between calls:

    USE ROLE ACCOUNTADMIN;
    USE DATABASE SNOWCORE_REAL;
    USE WAREHOUSE COMPUTE_WH;
    ALTER SESSION SET TIMEZONE = 'UTC';

The IT layer was reworked to separate breakdowns from idle time. The objects
are built; these checks confirm they are right. Run each query and report the
full result.

## 1. Counts against source events

    SELECT 'PLANT_B work orders' AS CHECK_NAME,
      (SELECT COUNT(*) FROM SNOWCORE_REAL.GOLD.PIADE_DOWNTIME_EVENT
       WHERE STOP_STATE = 'downtime' AND STOP_DURATION_MIN >= 10) AS EXPECTED,
      (SELECT COUNT(*) FROM SNOWCORE_REAL.GOLD.WORK_ORDER
       WHERE PLANT_CODE = 'PLANT_B') AS ACTUAL
    UNION ALL SELECT 'PLANT_A work orders', 1042,
      (SELECT COUNT(*) FROM SNOWCORE_REAL.GOLD.WORK_ORDER WHERE PLANT_CODE = 'PLANT_A')
    UNION ALL SELECT 'PLANT_B idle incidents',
      (SELECT COUNT(*) FROM SNOWCORE_REAL.GOLD.PIADE_DOWNTIME_EVENT
       WHERE STOP_STATE = 'idle' AND STOP_DURATION_MIN >= 30),
      (SELECT COUNT(*) FROM SNOWCORE_REAL.GOLD.PRODUCTION_LOSS_INCIDENT);

I measured 2,555 Plant B orders offline against the raw CSV using an unrounded
duration, and the account reports 2,556. If EXPECTED and ACTUAL agree with each
other at 2,556, the one-row gap is rounding in `STOP_DURATION_MIN` and is fine.
Confirm that is what is happening rather than assuming it: report both numbers
and say whether they agree with each other.

## 2. No placeholder causes, no cross-plant rows

    SELECT PLANT_CODE, COUNT(*) AS ORDERS,
      SUM(IFF(CAUSE_CODE IN ('A_000','UNDIAGNOSED'), 1, 0)) AS PLACEHOLDER_CAUSES,
      SUM(IFF(MACHINE_KEY NOT LIKE PLANT_CODE || ':%', 1, 0)) AS CROSS_PLANT_ROWS,
      COUNT(DISTINCT CAUSE_CODE) AS DISTINCT_CAUSES
    FROM SNOWCORE_REAL.GOLD.WORK_ORDER GROUP BY PLANT_CODE;

## 3. Determinism

    SELECT COUNT(*) AS ORDERS_CHECKED,
      SUM(IFF(ABS(RESPONSE_MIN - ROUND(8 + ((ABS(HASH(WORK_ORDER_ID || 'response')) % 10000) / 10000.0) * (35 - 8), 1)) > 0.05, 1, 0)) AS MISMATCHES
    FROM SNOWCORE_REAL.GOLD.WORK_ORDER;

MISMATCHES must be exactly 0.

## 4. Maintenance against idling — the finding this rework exists for

    SELECT 'BREAKDOWN (maintenance)' AS LOSS_TYPE, COUNT(*) AS EVENTS,
      ROUND(SUM(SOURCE_EVENT_MINUTES)/60.0,1) AS HOURS,
      ROUND(SUM(LABOUR_COST + PARTS_COST),2) AS REPAIR_COST,
      ROUND(SUM(LOST_PRODUCTION_COST),2) AS FORGONE_MARGIN,
      ROUND(SUM(TOTAL_COST),2) AS TOTAL_COST
    FROM SNOWCORE_REAL.GOLD.WORK_ORDER WHERE PLANT_CODE = 'PLANT_B'
    UNION ALL
    SELECT 'IDLE (planning)', COUNT(*), ROUND(SUM(LOSS_MINUTES)/60.0,1), 0,
      ROUND(SUM(FORGONE_MARGIN),2), ROUND(SUM(FORGONE_MARGIN),2)
    FROM SNOWCORE_REAL.GOLD.PRODUCTION_LOSS_INCIDENT;

## 5. Cost shape per plant

    SELECT PLANT_CODE, COUNT(*) AS ORDERS,
      ROUND(SUM(LABOUR_COST),2) AS LABOUR, ROUND(SUM(PARTS_COST),2) AS PARTS,
      COUNT(LOST_PRODUCTION_COST) AS ROWS_WITH_LOST_PRODUCTION,
      ROUND(SUM(TOTAL_COST),2) AS TOTAL, ROUND(AVG(TOTAL_COST),2) AS AVG_PER_ORDER
    FROM SNOWCORE_REAL.GOLD.WORK_ORDER GROUP BY PLANT_CODE;

`ROWS_WITH_LOST_PRODUCTION` must be 0 for PLANT_A.

## 6. The canonical OEE

    SELECT PLANT_CODE, COALESCE(MACHINE_CODE,'ALL MACHINES') AS SCOPE,
      PLANNED_HOURS, RUN_HOURS, BREAKDOWN_HOURS, IDLE_HOURS, SLOW_RUNNING_HOURS,
      AVAILABILITY, PERFORMANCE, QUALITY, OEE
    FROM SNOWCORE_REAL.GOLD.V_OEE_ROLLUP
    ORDER BY PLANT_CODE, MACHINE_CODE NULLS FIRST;

## 7. Pareto, corrected labelling

    SELECT CAUSE_CODE, LOSS_NATURE, OWNING_FUNCTION, STOP_PATTERN,
      STOP_COUNT, STOP_HOURS, MEDIAN_STOP_MIN, PCT_OF_STOP_TIME, CUMULATIVE_PCT
    FROM SNOWCORE_REAL.GOLD.V_DOWNTIME_PARETO
    WHERE PLANT_CODE = 'PLANT_B' ORDER BY STOP_HOURS DESC LIMIT 12;

## 8. Cost split per machine

    SELECT PLANT_CODE, MACHINE_CODE, WORK_ORDERS, BREAKDOWN_HOURS,
      MAINTENANCE_COST, IDLE_INCIDENTS, IDLE_HOURS, IDLE_FORGONE_MARGIN,
      PCT_COST_FROM_IDLING
    FROM SNOWCORE_REAL.GOLD.V_COST_BY_MACHINE ORDER BY PLANT_CODE, MACHINE_CODE;

## 9. Semantic view against a direct query

    SELECT * FROM SEMANTIC_VIEW(
      SNOWCORE_REAL.GOLD.SEM_SNOWCORE_OEE
      DIMENSIONS machine.machine_code
      METRICS oee.availability, oee.performance, oee.quality, oee.oee_pct
    ) ORDER BY MACHINE_CODE;

    SELECT MACHINE_CODE,
      ROUND(SUM(RUN_SEC)/NULLIF(SUM(PLANNED_SEC),0),4) AS AVAILABILITY_DIRECT,
      ROUND(SUM(PACKAGES_OUT)/NULLIF(SUM(THEORETICAL_PACKAGES),0),4) AS PERFORMANCE_DIRECT,
      ROUND(SUM(PACKAGES_OUT)/NULLIF(SUM(PACKAGES_IN),0),4) AS QUALITY_DIRECT
    FROM SNOWCORE_REAL.GOLD.PIADE_OEE_DAILY GROUP BY MACHINE_CODE ORDER BY MACHINE_CODE;

## 10. Narratives and advice, full text

    SELECT BRIEFING_KEY, INPUT_ORIGIN, MODEL_USED, NARRATIVE
    FROM SNOWCORE_REAL.GOLD.CORTEX_BRIEFING ORDER BY BRIEFING_KEY;

    SELECT CAUSE_CODE, LOSS_NATURE, STOP_PATTERN, STOP_HOURS, ADVICE
    FROM SNOWCORE_REAL.GOLD.CORTEX_CAUSE_ADVICE ORDER BY STOP_HOURS DESC;

    SELECT STOP_PATTERN, COUNT(*) AS CAUSES, ROUND(SUM(STOP_HOURS),1) AS STOP_HOURS
    FROM SNOWCORE_REAL.GOLD.V_DOWNTIME_PARETO WHERE PLANT_CODE='PLANT_B'
    GROUP BY STOP_PATTERN ORDER BY STOP_HOURS DESC;

## Judgement

1. Do the three counts in query 1 match, and is the 2,555 versus 2,556 gap
   explained by rounding?
2. Are placeholder causes and cross-plant rows both zero, and are mismatches
   in query 3 zero?
3. From query 4: state the idle cost and the maintenance cost on Plant B, and
   the ratio between them.
4. From query 6: what is Plant B's canonical OEE? Two earlier averaging
   methods gave 57.1% and 43.2%; say how far the correct figure is from each.
5. Is `IDLE_NO_ALARM` top of the Pareto, marked WAITING and owned by PLANNING?
6. Does the semantic view still agree with the direct query on every machine?
7. Read the `PLANT_B_COST` narrative. Does its first sentence say the figures
   are synthetic, and does it assign idle cost to planning rather than
   maintenance? Quote it if not.
8. Read every advice sentence. Does any invent a physical mechanism — a
   bearing, seal, gripper, jam, sensor, motor — for an anonymised alarm code?
   Quote any that do. This is the failure I most want caught.
9. Does the deterministic `STOP_PATTERN` rule spread causes across more than
   one bucket, unlike the LLM version which put all nineteen in one?

Report problems plainly.

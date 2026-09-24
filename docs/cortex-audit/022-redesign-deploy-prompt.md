Re-upload the redesigned Streamlit app and verify its queries. Fully qualified
names throughout — database context has been dropping between calls.

    USE ROLE ACCOUNTADMIN;
    USE DATABASE SNOWCORE_REAL;
    USE WAREHOUSE COMPUTE_WH;
    ALTER SESSION SET TIMEZONE = 'UTC';

`streamlit/app.py` has been rewritten with a new layout. The data it reads is
the same, but several queries are new or changed, so they need checking before
I open the app. Do not modify `app.py`.

## 1. Upload

Read `streamlit/app.py` from disk exactly as it is.

    PUT 'file://<absolute path>/streamlit/app.py'
        @SNOWCORE_REAL.APPS.STREAMLIT_STAGE/snowcore_pdm/
        OVERWRITE = TRUE AUTO_COMPRESS = FALSE;

    ALTER STAGE SNOWCORE_REAL.APPS.STREAMLIT_STAGE REFRESH;
    LIST @SNOWCORE_REAL.APPS.STREAMLIT_STAGE/snowcore_pdm/;

The local file is 49,235 bytes. Report the staged size; anything much smaller
means truncation and must be reported rather than glossed over.

## 2. Verify the new and changed queries

Run each and report the row count, plus the actual values where asked. Report
any failure with its exact error message.

**a. Rollup columns used by the new KPI strip**

    SELECT PLANT_CODE, MACHINE_CODE, DAYS_OBSERVED, PLANNED_HOURS, RUN_HOURS,
           BREAKDOWN_HOURS, IDLE_HOURS, SLOW_RUNNING_HOURS,
           AVAILABILITY, PERFORMANCE, QUALITY, OEE
    FROM SNOWCORE_REAL.GOLD.V_OEE_ROLLUP
    ORDER BY PLANT_CODE, MACHINE_CODE NULLS FIRST;

**b. The time-split bar on the overview page.** Confirm the four parts sum to
roughly PLANNED_HOURS and that none is negative — in particular
`RUN_HOURS - SLOW_RUNNING_HOURS`, which must not go below zero.

    SELECT RUN_HOURS, SLOW_RUNNING_HOURS, RUN_HOURS - SLOW_RUNNING_HOURS AS AT_RATE,
           IDLE_HOURS, BREAKDOWN_HOURS, PLANNED_HOURS,
           (RUN_HOURS - SLOW_RUNNING_HOURS) + SLOW_RUNNING_HOURS
             + IDLE_HOURS + BREAKDOWN_HOURS AS PARTS_TOTAL
    FROM SNOWCORE_REAL.GOLD.V_OEE_ROLLUP
    WHERE PLANT_CODE='PLANT_B' AND MACHINE_CODE IS NULL;

State whether AT_RATE is positive and how PARTS_TOTAL compares to
PLANNED_HOURS. If AT_RATE is negative the overview chart is wrong and I need
to know immediately.

**c. Biggest-loss tally**

    SELECT BIGGEST_LOSS, COUNT(*) AS DAYS
    FROM SNOWCORE_REAL.GOLD.V_OEE_DAILY
    WHERE BIGGEST_LOSS IS NOT NULL GROUP BY BIGGEST_LOSS ORDER BY DAYS DESC;

**d. Plant A drift, deduplicated per channel (new QUALIFY)**

    SELECT CHANNEL, MEAN_SIGNED_Z
    FROM SNOWCORE_REAL.ML.PLANT_A_CHANNEL_DRIFT
    WHERE MACHINE_CODE='A005' AND IS_DRIFTED
    QUALIFY ROW_NUMBER() OVER (
      PARTITION BY CHANNEL ORDER BY ABS(MEAN_SIGNED_Z) DESC) = 1
    ORDER BY MEAN_SIGNED_Z;

Also report, for every Plant A machine, how many drifted channels it has, so I
know which machines will show an empty drift panel:

    SELECT MACHINE_CODE, COUNT(DISTINCT CHANNEL) AS DRIFTED_CHANNELS
    FROM SNOWCORE_REAL.ML.PLANT_A_CHANNEL_DRIFT
    WHERE IS_DRIFTED GROUP BY MACHINE_CODE ORDER BY MACHINE_CODE;

**e. Plant A assessed-machine status (new COUNT_IF and 30-window rule)**

    WITH scored AS (
      SELECT MACHINE_CODE, COUNT_IF(IS_SCORED_PERIOD) AS SCORED_WINDOWS
      FROM SNOWCORE_REAL.ML.PLANT_A_HEALTH GROUP BY MACHINE_CODE
    )
    SELECT f.MACHINE_CODE,
           IFF(COALESCE(s.SCORED_WINDOWS,0) < 30, 'Not assessed', 'Scored') AS STATUS,
           COALESCE(s.SCORED_WINDOWS,0) AS SCORED_WINDOWS
    FROM SNOWCORE_REAL.GOLD.V_FLEET f
    LEFT JOIN scored s USING (MACHINE_CODE)
    WHERE f.PLANT_CODE='PLANT_A' ORDER BY f.MACHINE_CODE;

Report which machines are 'Scored' and which are 'Not assessed'. The app puts
a selector over the scored ones, so if that list is empty the page breaks.

**f. Risk hit-and-miss markers**

    SELECT MACHINE_CODE,
           COUNT(*) AS ROWS_SCORED,
           SUM(IFF(IS_FLAGGED=1 AND ACTUAL_HEAVY_STOP=1,1,0)) AS FLAGGED_HITS,
           SUM(IFF(IS_FLAGGED=1 AND ACTUAL_HEAVY_STOP=0,1,0)) AS FLAGGED_FALSE
    FROM SNOWCORE_REAL.GOLD.V_PLANT_B_RISK GROUP BY MACHINE_CODE ORDER BY MACHINE_CODE;

**g. Assumption table, as the app now reads it**

    SELECT PLANT_SCOPE, NAME, VALUE, UNIT, IS_MEASURED, BASIS
    FROM SNOWCORE_REAL.GOLD.IT_ASSUMPTION ORDER BY PLANT_SCOPE, NAME;

**h. Pareto, deeper than before (app now shows 25 rows)**

    SELECT COUNT(*) AS CAUSE_ROWS
    FROM SNOWCORE_REAL.GOLD.V_DOWNTIME_PARETO WHERE PLANT_CODE='PLANT_B';

## 3. Confirm the app object

    SHOW STREAMLITS IN SCHEMA SNOWCORE_REAL.APPS;

## Report

1. Staged file size.
2. Any query that failed, with the exact error.
3. The specific answer to 2b — is AT_RATE positive?
4. Which Plant A machines are scored, and which have zero drifted channels.

Be blunt about anything that looks wrong.

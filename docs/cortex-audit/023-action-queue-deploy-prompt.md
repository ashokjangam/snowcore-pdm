Upload the revised Streamlit app and verify the queries behind its new page.
Fully qualified names throughout. Use forward slashes in the PUT path — the
backslash form was consumed last time.

    USE ROLE ACCOUNTADMIN;
    USE DATABASE SNOWCORE_REAL;
    USE WAREHOUSE COMPUTE_WH;
    ALTER SESSION SET TIMEZONE = 'UTC';

`streamlit/app.py` has been revised. The visual style returns to the earlier
version, and a new **Action queue** page unifies both plants at the decision
layer. Do not modify the file.

## 1. Upload

    PUT 'file://C:/Users/C306242/Phoenix/sainathch45/snowcore-pdm/streamlit/app.py'
        @SNOWCORE_REAL.APPS.STREAMLIT_STAGE/snowcore_pdm/
        OVERWRITE = TRUE AUTO_COMPRESS = FALSE;

    ALTER STAGE SNOWCORE_REAL.APPS.STREAMLIT_STAGE REFRESH;
    LIST @SNOWCORE_REAL.APPS.STREAMLIT_STAGE/snowcore_pdm/;

Local size is 61,501 bytes. Report the staged size and flag any shortfall.

## 2. Verify the Action queue queries

These are new. Run each, report the row count and the actual rows where the
result is small. Report any failure with its exact error.

**a. Planning rows — idle by line**

    SELECT MACHINE_CODE, IDLE_HOURS, IDLE_INCIDENTS, PCT_COST_FROM_IDLING
    FROM SNOWCORE_REAL.GOLD.V_COST_BY_MACHINE
    WHERE PLANT_CODE='PLANT_B' AND IDLE_HOURS > 0
    ORDER BY IDLE_HOURS DESC;

**b. Maintenance rows — real faults only.** This must exclude IDLE_NO_ALARM.
Confirm that `IDLE_NO_ALARM` does not appear in the result.

    SELECT CAUSE_CODE, STOP_COUNT, STOP_HOURS, MEDIAN_STOP_MIN, STOP_PATTERN
    FROM SNOWCORE_REAL.GOLD.V_DOWNTIME_PARETO
    WHERE PLANT_CODE='PLANT_B' AND LOSS_NATURE='FAULTED'
    ORDER BY STOP_HOURS DESC LIMIT 6;

**c. Which lines the model is trusted on**

    SELECT SCOPE, TOP_DECILE_PRECISION, BASELINE_TOP_DECILE_PRECISION,
           TOP_DECILE_PRECISION > BASELINE_TOP_DECILE_PRECISION AS TRUSTED
    FROM SNOWCORE_REAL.ML.PLANT_B_MODEL_METRICS WHERE SCOPE <> 'FLEET'
    ORDER BY SCOPE;

**d. Flagged hours for the trusted lines.** Substitute the trusted list from
query c into the IN clause yourself.

    SELECT MACHINE_CODE, COUNT(*) AS FLAGGED_HOURS,
           SUM(IFF(ACTUAL_HEAVY_STOP=1,1,0)) AS CONFIRMED
    FROM SNOWCORE_REAL.GOLD.V_PLANT_B_RISK
    WHERE IS_FLAGGED = 1 AND MACHINE_CODE IN (<trusted lines>)
    GROUP BY MACHINE_CODE ORDER BY FLAGGED_HOURS DESC;

**e. Plant A drift with LISTAGG.** This is the one most likely to fail on
syntax, so report the exact error if it does.

    SELECT MACHINE_CODE, COUNT(DISTINCT CHANNEL) AS CHANNELS,
           LISTAGG(DISTINCT CHANNEL, ', ') WITHIN GROUP (ORDER BY CHANNEL) AS NAMES
    FROM SNOWCORE_REAL.ML.PLANT_A_CHANNEL_DRIFT
    WHERE IS_DRIFTED GROUP BY MACHINE_CODE ORDER BY CHANNELS DESC;

**f. Plant A data gaps**

    WITH scored AS (
      SELECT MACHINE_CODE, COUNT_IF(IS_SCORED_PERIOD) AS W
      FROM SNOWCORE_REAL.ML.PLANT_A_HEALTH GROUP BY MACHINE_CODE
    )
    SELECT f.MACHINE_CODE, COALESCE(s.W,0) AS W
    FROM SNOWCORE_REAL.GOLD.V_FLEET f LEFT JOIN scored s USING (MACHINE_CODE)
    WHERE f.PLANT_CODE='PLANT_A' AND COALESCE(s.W,0) < 30
    ORDER BY f.MACHINE_CODE;

## 3. Sanity on the unified queue

From the results above, tell me how many rows the Action queue will contain in
each group, so I can confirm no group is empty:

- Planning  = count from (a)
- Maintenance = count from (b) plus count from (d)
- Reliability = count from (e)
- Data gap = untrusted lines from (c) plus count from (f)

If any group would be empty, say which, because an empty section is a layout
bug I need to handle.

## 4. Report

1. Staged file size.
2. Any query that failed, with its exact error.
3. The four group counts from step 3.
4. Confirm `IDLE_NO_ALARM` is absent from query b — if it is present, the
   maintenance section of the queue is wrongly claiming waiting time as repair
   work, which is the exact error this whole layer exists to avoid.

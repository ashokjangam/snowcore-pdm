Deploy the Streamlit app into Snowflake. Use fully qualified names everywhere,
because database context has been dropping between calls in this connection.

    USE ROLE ACCOUNTADMIN;
    USE DATABASE SNOWCORE_REAL;
    USE WAREHOUSE COMPUTE_WH;
    ALTER SESSION SET TIMEZONE = 'UTC';
    ALTER SESSION SET QUERY_TAG = 'snowcore-real|coco|streamlit-deploy';

## Files

Two files in this repository are the entire application:

    streamlit/app.py
    streamlit/environment.yml

Read them from disk. Do not reconstruct, rewrite, reformat or "improve" them.
`app.py` is roughly 600 lines and must arrive byte-for-byte.

## Steps

### 1. Stage

    CREATE SCHEMA IF NOT EXISTS SNOWCORE_REAL.APPS;
    CREATE STAGE IF NOT EXISTS SNOWCORE_REAL.APPS.STREAMLIT_STAGE
      DIRECTORY = (ENABLE = TRUE)
      COMMENT = 'Source for the SnowCore two-plant Streamlit app.';

### 2. Upload

    PUT 'file://<absolute path>/streamlit/app.py'
        @SNOWCORE_REAL.APPS.STREAMLIT_STAGE/snowcore_pdm/
        OVERWRITE = TRUE AUTO_COMPRESS = FALSE;

    PUT 'file://<absolute path>/streamlit/environment.yml'
        @SNOWCORE_REAL.APPS.STREAMLIT_STAGE/snowcore_pdm/
        OVERWRITE = TRUE AUTO_COMPRESS = FALSE;

`AUTO_COMPRESS = FALSE` matters — a gzipped `app.py` will not run.

If `PUT` is not supported by this client, stop and say so explicitly rather
than inventing a workaround such as writing the file contents through
`COPY INTO` or a `SELECT`. That would corrupt the Python source. Report the
exact error and stop.

Then confirm both files are present and note their sizes:

    ALTER STAGE SNOWCORE_REAL.APPS.STREAMLIT_STAGE REFRESH;
    LIST @SNOWCORE_REAL.APPS.STREAMLIT_STAGE/snowcore_pdm/;

### 3. Create the app

    CREATE OR REPLACE STREAMLIT SNOWCORE_REAL.APPS.SNOWCORE_PDM
      ROOT_LOCATION = '@SNOWCORE_REAL.APPS.STREAMLIT_STAGE/snowcore_pdm'
      MAIN_FILE     = 'app.py'
      QUERY_WAREHOUSE = COMPUTE_WH
      COMMENT = 'SnowCore PdM two-plant command centre. Plant A and Plant B are never aggregated.';

### 4. Report the URL

    SHOW STREAMLITS IN SCHEMA SNOWCORE_REAL.APPS;

Report the app name and its `url_id`, and construct the full URL in the form
`https://app.snowflake.com/<org>/<account>/#/streamlit-apps/SNOWCORE_REAL.APPS.SNOWCORE_PDM`.
Get the org and account from `SELECT CURRENT_ORGANIZATION_NAME(), CURRENT_ACCOUNT_NAME();`.

## 5. Prove the queries work before I open the app

The app will fail at runtime rather than at creation time if a column is
missing. Run each of these and report the row count. Report any that error,
with the exact message.

    SELECT * FROM SNOWCORE_REAL.GOLD.V_OEE_ROLLUP WHERE PLANT_CODE='PLANT_B' AND MACHINE_CODE IS NULL;
    SELECT SUM(MAINTENANCE_COST), SUM(IDLE_FORGONE_MARGIN), SUM(BREAKDOWN_HOURS), SUM(IDLE_HOURS)
      FROM SNOWCORE_REAL.GOLD.V_COST_BY_MACHINE WHERE PLANT_CODE='PLANT_B';
    SELECT COUNT(DISTINCT MACHINE_CODE), AVG(HEALTH_INDEX_AVG), MIN(HEALTH_INDEX_WORST)
      FROM SNOWCORE_REAL.GOLD.V_PLANT_A_HEALTH WHERE ANY_SCORED_PERIOD;
    SELECT SCOPE, AUC, BASE_RATE, TOP_DECILE_PRECISION, TOP_DECILE_RECALL, BASELINE_TOP_DECILE_PRECISION, TEST_ROWS
      FROM SNOWCORE_REAL.ML.PLANT_B_MODEL_METRICS;
    SELECT MACHINE_CODE, COUNT_IF(IS_SCORED_PERIOD) FROM SNOWCORE_REAL.ML.PLANT_A_HEALTH GROUP BY MACHINE_CODE;
    SELECT MACHINE_CODE, DRIFT_MONTH, CHANNEL, MEAN_SIGNED_Z, MEDIAN_SHIFT, IS_DRIFTED
      FROM SNOWCORE_REAL.ML.PLANT_A_CHANNEL_DRIFT LIMIT 5;
    SELECT MACHINE_CODE, HOUR_TS, RISK_SCORE, RISK_BAND, IS_FLAGGED, ACTUAL_HEAVY_STOP, ACTUAL_NEXT_HOUR_DOWNTIME_PCT
      FROM SNOWCORE_REAL.GOLD.V_PLANT_B_RISK LIMIT 5;
    SELECT RANK, FEATURE, IMPORTANCE FROM SNOWCORE_REAL.ML.PLANT_B_FEATURE_IMPORTANCE ORDER BY RANK LIMIT 5;
    SELECT PLANT_CODE, NAME, VALUE, UNIT, IS_MEASURED, RATIONALE FROM SNOWCORE_REAL.GOLD.IT_ASSUMPTION LIMIT 5;
    SELECT PLANT_CODE, SUBJECT, DATA_ORIGIN, SOURCE, NOTE FROM SNOWCORE_REAL.GOLD.V_PROVENANCE;
    SELECT BRIEFING_KEY, NARRATIVE, INPUT_ORIGIN, MODEL_USED, GENERATED_AT FROM SNOWCORE_REAL.GOLD.CORTEX_BRIEFING;
    SELECT MACHINE_CODE, FIRST_SEEN, LAST_SEEN FROM SNOWCORE_REAL.GOLD.V_FLEET WHERE PLANT_CODE='PLANT_A';
    SELECT OEE_DATE, MACHINE_CODE, OEE, AVAILABILITY, PERFORMANCE, QUALITY, BIGGEST_LOSS
      FROM SNOWCORE_REAL.GOLD.V_OEE_DAILY LIMIT 5;
    SELECT CAUSE_CODE, LOSS_NATURE, OWNING_FUNCTION, STOP_PATTERN, STOP_COUNT, STOP_HOURS,
           MEDIAN_STOP_MIN, PCT_OF_STOP_TIME, CUMULATIVE_PCT
      FROM SNOWCORE_REAL.GOLD.V_DOWNTIME_PARETO WHERE PLANT_CODE='PLANT_B' ORDER BY STOP_HOURS DESC LIMIT 5;

## Report

State plainly:

1. Did both files upload, and at what byte sizes? A size far below ~20 KB for
   `app.py` means it was truncated.
2. Was the STREAMLIT object created, and what is its URL?
3. Did every verification query in step 5 succeed? List any that failed with
   the exact error, because each failure is a page in the app that will break.

Do not modify `app.py`. If a query fails because of a column name, report it
and let me fix the source.

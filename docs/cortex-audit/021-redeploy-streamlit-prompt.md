Re-upload one file and confirm the fix. Fully qualified names throughout.

    USE ROLE ACCOUNTADMIN;
    USE DATABASE SNOWCORE_REAL;
    USE WAREHOUSE COMPUTE_WH;
    ALTER SESSION SET TIMEZONE = 'UTC';

`streamlit/app.py` referenced `GOLD.IT_ASSUMPTION.PLANT_CODE` and `RATIONALE`,
which do not exist. The real columns are `PLANT_SCOPE` and `BASIS`. The file on
disk is already corrected. Only `app.py` changed; `environment.yml` is
unchanged and does not need re-uploading.

## 1. Confirm the corrected query actually runs

    SELECT PLANT_SCOPE, NAME, VALUE, UNIT, IS_MEASURED, BASIS
    FROM SNOWCORE_REAL.GOLD.IT_ASSUMPTION
    ORDER BY PLANT_SCOPE, NAME;

Report the full result. This is the last unverified page in the app.

## 2. Re-upload

Read `streamlit/app.py` from disk. Do not alter it.

    PUT 'file://<absolute path>/streamlit/app.py'
        @SNOWCORE_REAL.APPS.STREAMLIT_STAGE/snowcore_pdm/
        OVERWRITE = TRUE AUTO_COMPRESS = FALSE;

    ALTER STAGE SNOWCORE_REAL.APPS.STREAMLIT_STAGE REFRESH;
    LIST @SNOWCORE_REAL.APPS.STREAMLIT_STAGE/snowcore_pdm/;

Report the new size. It should be slightly larger than the previous 24,960
bytes, not smaller.

## 3. Confirm the app still resolves

    SHOW STREAMLITS IN SCHEMA SNOWCORE_REAL.APPS;

A `CREATE OR REPLACE STREAMLIT` is not needed, because the object reads from
the stage at run time. Confirm the object still exists and still points at
`@SNOWCORE_REAL.APPS.STREAMLIT_STAGE/snowcore_pdm` with `MAIN_FILE = 'app.py'`.

## 4. One last sweep for the same class of bug

Every remaining table and view the app reads was verified in the previous run
except the assumption table. To be certain nothing else is mismatched, list the
column names of these two, which are the ones the app selects the most columns
from, and confirm the listed names exist:

    DESCRIBE VIEW SNOWCORE_REAL.GOLD.V_COST_BY_MACHINE;
    DESCRIBE VIEW SNOWCORE_REAL.GOLD.V_PLANT_A_HEALTH;

The app selects from `V_COST_BY_MACHINE`: `MACHINE_CODE`, `WORK_ORDERS`,
`BREAKDOWN_HOURS`, `MAINTENANCE_COST`, `IDLE_INCIDENTS`, `IDLE_HOURS`,
`IDLE_FORGONE_MARGIN`, `PCT_COST_FROM_IDLING`.

From `V_PLANT_A_HEALTH`: `MACHINE_CODE`, `HEALTH_DATE`, `HEALTH_INDEX_AVG`,
`HEALTH_INDEX_WORST`, `CHANNEL_EXCURSIONS`, `DOMINANT_CHANNEL`,
`ANY_SCORED_PERIOD`.

Report any name in those two lists that does not exist in the view.

## Report

State whether the assumption query now works, the new file size, and whether
any further column mismatch was found.

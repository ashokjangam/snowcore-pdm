# Cortex prompt 037e — replace procedure and run one campaign

Use connection `hackathon`. Do not start a second CALL if one is already
RUNNING.

1. PUT and execute the current runtime SQL:

```sql
USE ROLE ACCOUNTADMIN;
USE DATABASE SNOWCORE_REAL;
USE WAREHOUSE COMPUTE_WH;

PUT 'file://C:/Users/C306242/Phoenix/sainathch45/snowcore-pdm/sql/20_piade_autoresearch_runtime.sql'
  @SNOWCORE_REAL.APPS.STREAMLIT_STAGE/sql/
  OVERWRITE=TRUE AUTO_COMPRESS=FALSE;

ALTER STAGE SNOWCORE_REAL.APPS.STREAMLIT_STAGE REFRESH;
EXECUTE IMMEDIATE FROM @SNOWCORE_REAL.APPS.STREAMLIT_STAGE/sql/20_piade_autoresearch_runtime.sql;
```

2. If any `CALL SNOWCORE_REAL.ML.RUN_PIADE_AUTORESEARCH` query is RUNNING,
   wait. Do not cancel it unless it has been running more than 45 minutes
   after this replacement; in that case SYSTEM$CANCEL_QUERY that id only.

3. Then exactly one:

```sql
ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = 2400;
CALL SNOWCORE_REAL.ML.RUN_PIADE_AUTORESEARCH(25);
```

4. Report campaign STATUS, EVALUATED_TRIALS, STOP_REASON, PROMOTION_STATUS,
   PROMOTION_ELIGIBLE, BASELINE_MEAN_AUC, CHAMPION_MEAN_AUC, HOLDOUT_EVALUATED,
   PRODUCTION_TABLES_MODIFIED, gate rows, and ERROR_MESSAGE if failed.

Do not write PLANT_B_* production tables. Do not edit files.

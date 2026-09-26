# Cortex prompt 037e2 — single 25-trial CALL

Use connection `hackathon`. Do not edit files. Do not start a second CALL.

If `QUERY_HISTORY` shows a RUNNING `CALL ...RUN_PIADE_AUTORESEARCH`, wait for
it instead of starting another. Otherwise:

```sql
USE ROLE ACCOUNTADMIN;
USE DATABASE SNOWCORE_REAL;
USE WAREHOUSE COMPUTE_WH;
ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = 2400;
CALL SNOWCORE_REAL.ML.RUN_PIADE_AUTORESEARCH(25);
```

After it returns, SELECT the latest campaign row (status, evaluated trials,
stop reason, promotion fields, baseline/champion AUC, holdout flag,
production_tables_modified, error_message) and all promotion-gate rows for
that campaign_id. Do not write PLANT_B_* tables.

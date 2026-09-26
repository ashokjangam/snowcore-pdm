# Cortex prompt 037f — cancel zombie fits, replace proc, one campaign

Use connection `hackathon`. Do not edit files.

1. Find running statements whose trimmed text starts with `CALL` and contains
   `RUN_PIADE_AUTORESEARCH`. `SYSTEM$CANCEL_QUERY` each of those query ids.

2. Mark abandoned campaigns honestly (do not delete rows):

```sql
USE DATABASE SNOWCORE_REAL;
UPDATE ML.PIADE_RESEARCH_CAMPAIGN
SET STATUS='FAILED',
    FINISHED_AT=COALESCE(FINISHED_AT, CURRENT_TIMESTAMP()),
    STOP_REASON='CANCELED_NATIVE_FIT_OVERRUN',
    PROMOTION_STATUS='BLOCKED_BY_ERROR',
    PROMOTION_ELIGIBLE=FALSE,
    PRODUCTION_TABLES_MODIFIED=FALSE,
    ERROR_MESSAGE='Canceled: RandomForest native fit on XS warehouse exceeded the 180s/1800s budget and could not be preempted from Python.'
WHERE STATUS='RUNNING';

UPDATE ML.PIADE_RESEARCH_RUN
SET TRIAL_DECISION='CRASH',
    EVALUATION_STATUS='FAILED',
    FINISHED_AT=COALESCE(FINISHED_AT, CURRENT_TIMESTAMP()),
    DECISION_REASON='Canceled: native fit overrun on COMPUTE_WH X-Small'
WHERE EVALUATION_STATUS='RUNNING';
```

3. PUT and execute the current runtime SQL:

```sql
PUT 'file://C:/Users/C306242/Phoenix/sainathch45/snowcore-pdm/sql/20_piade_autoresearch_runtime.sql'
  @SNOWCORE_REAL.APPS.STREAMLIT_STAGE/sql/
  OVERWRITE=TRUE AUTO_COMPRESS=FALSE;
ALTER STAGE SNOWCORE_REAL.APPS.STREAMLIT_STAGE REFRESH;
EXECUTE IMMEDIATE FROM @SNOWCORE_REAL.APPS.STREAMLIT_STAGE/sql/20_piade_autoresearch_runtime.sql;
```

4. Then exactly one:

```sql
ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS=2400;
CALL SNOWCORE_REAL.ML.RUN_PIADE_AUTORESEARCH(25);
```

Wait for the CALL. Report the new campaign STATUS, EVALUATED_TRIALS,
STOP_REASON, PROMOTION_*, BASELINE_MEAN_AUC, CHAMPION_MEAN_AUC,
HOLDOUT_EVALUATED, PRODUCTION_TABLES_MODIFIED, gate rows, and ERROR_MESSAGE.
Do not write PLANT_B_* tables.

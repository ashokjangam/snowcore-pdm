# Cortex prompt 037e1 — replace procedure only

Use connection `hackathon`. Do not CALL anything.

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

Then `SHOW PROCEDURES LIKE 'RUN_PIADE_AUTORESEARCH' IN SCHEMA SNOWCORE_REAL.ML`.
Report created timestamp. Do not edit files.

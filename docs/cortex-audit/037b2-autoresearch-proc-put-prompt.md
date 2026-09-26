# Cortex prompt 037b2 — PUT runtime SQL and EXECUTE IMMEDIATE FROM

Use connection `hackathon`. Do not edit files. Run these statements in order.
Snowflake tool calls do not keep session context, so prefix each call with
`USE DATABASE SNOWCORE_REAL;` when needed.

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

If `EXECUTE IMMEDIATE FROM` is unsupported, say so and stop. If package pin
`snowflake-ml-python==2.1.0` fails, PUT is already done: report the exact
error. Then SHOW PROCEDURES LIKE 'RUN_PIADE_AUTORESEARCH' IN SCHEMA
SNOWCORE_REAL.ML.

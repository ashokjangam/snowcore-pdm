# Cortex prompt 037g — replace procedure after champion-contract bind fix

Use connection `hackathon`. Do not edit files. Do not CALL RUN_PIADE_AUTORESEARCH
in this prompt.

Campaign `aabd1201-f2bc-432e-93e4-3a4f150736c7` already evaluated its trials and
wrote promotion gates, then failed on `INSERT INTO ML.PIADE_CHAMPION_CONTRACT`
(`Bind variable ? not set`). Production `PLANT_B_*` tables must stay untouched.

Run these statements in order. Prefix with `USE DATABASE SNOWCORE_REAL;` if the
session drops.

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

Then SHOW PROCEDURES LIKE 'RUN_PIADE_AUTORESEARCH' IN SCHEMA SNOWCORE_REAL.ML.

Return PUT bytes, EXECUTE IMMEDIATE success or the exact error, and the
procedure created timestamp. Confirm no CALL was started.

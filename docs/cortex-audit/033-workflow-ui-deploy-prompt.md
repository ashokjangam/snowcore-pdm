# Cortex prompt 033 — workflow UI deployment

Deploy only the current Streamlit application. Do not change tables, views,
roles, grants, metrics, or Streamlit ownership.

```sql
USE ROLE ACCOUNTADMIN;
USE DATABASE SNOWCORE_REAL;
USE WAREHOUSE COMPUTE_WH;
ALTER SESSION SET TIMEZONE='UTC';

PUT 'file://C:/Users/C306242/Phoenix/sainathch45/snowcore-pdm/streamlit/app.py'
  @SNOWCORE_REAL.APPS.STREAMLIT_STAGE/snowcore_pdm/
  OVERWRITE=TRUE AUTO_COMPRESS=FALSE;

ALTER STAGE SNOWCORE_REAL.APPS.STREAMLIT_STAGE REFRESH;

LIST @SNOWCORE_REAL.APPS.STREAMLIT_STAGE/snowcore_pdm/;
```

Then run read-only checks that support the workflow UI:

```sql
SELECT DISTINCT STATUS
FROM GOLD.WORK_ORDER
WHERE PLANT_CODE='PLANT_B'
ORDER BY 1;

SELECT DISTINCT PRIORITY
FROM GOLD.WORK_ORDER
WHERE PLANT_CODE='PLANT_B'
ORDER BY 1;

SHOW STREAMLITS LIKE 'SNOWCORE_PDM' IN SCHEMA SNOWCORE_REAL.APPS;
```

Report staged bytes/timestamp, historical status values, historical priority
values, app owner, query warehouse, and URL ID. The new `PLANNED` status is
session-only and should not be inserted into Snowflake.

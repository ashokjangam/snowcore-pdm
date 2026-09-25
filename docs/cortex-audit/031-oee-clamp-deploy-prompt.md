# Cortex prompt 031 — clamped weekly OEE redeploy

Upload the current `streamlit/app.py` and confirm the clamped weekly trend
definition stays inside 0 and 1. Change no tables, views, or metrics.

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

The app now caps each weekly OEE term at 1.0, matching the `LEAST(...,1.0)`
rule already used by `GOLD.PIADE_OEE_DAILY`. Confirm the clamped definition
behaves:

```sql
USE DATABASE SNOWCORE_REAL;
SELECT COUNT(*) AS WEEKS,
       COUNT_IF(W < 0 OR W > 1) AS OUT_OF_RANGE_WEEKS,
       ROUND(MIN(W),4) AS MIN_W,
       ROUND(MAX(W),4) AS MAX_W
FROM (
  SELECT LEAST(SUM(RUN_HOURS)/NULLIF(SUM(PLANNED_HOURS),0),1.0)
         * LEAST(SUM(PACKAGES_OUT)/NULLIF(SUM(THEORETICAL_PACKAGES),0),1.0)
         * LEAST(SUM(PACKAGES_OUT)/NULLIF(SUM(PACKAGES_IN),0),1.0) AS W
  FROM GOLD.V_OEE_DAILY GROUP BY DATE_TRUNC('week', OEE_DATE));
```

Also report how many weeks were affected by the cap, so the limitation can be
documented honestly rather than hidden:

```sql
USE DATABASE SNOWCORE_REAL;
SELECT COUNT(*) AS WEEKS_CAPPED FROM (
  SELECT DATE_TRUNC('week', OEE_DATE) WK
  FROM GOLD.V_OEE_DAILY
  GROUP BY 1
  HAVING SUM(PACKAGES_OUT) > SUM(PACKAGES_IN)
      OR SUM(RUN_HOURS) > SUM(PLANNED_HOURS)
      OR SUM(PACKAGES_OUT) > SUM(THEORETICAL_PACKAGES));

SELECT COUNT_IF(QUALITY_CLAMPED) AS DAYS_CLAMPED, COUNT(*) AS TOTAL_DAYS
FROM GOLD.V_OEE_DAILY;
```

Report staged bytes and timestamp, weeks, out-of-range weeks, min/max, weeks
capped, and clamped days out of total days.

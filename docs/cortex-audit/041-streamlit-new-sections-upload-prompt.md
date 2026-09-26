# Cortex prompt 041 — upload Streamlit app with warning, root-cause and auto work-order sections

Use connection `hackathon`. Do not edit files. Run in order and report results
verbatim. On error, report the exact error and stop.

```sql
USE ROLE ACCOUNTADMIN;
USE DATABASE SNOWCORE_REAL;
USE WAREHOUSE COMPUTE_WH;

PUT 'file://C:/Users/C306242/Phoenix/sainathch45/snowcore-pdm/streamlit/app.py'
  @SNOWCORE_REAL.APPS.STREAMLIT_STAGE/snowcore_pdm/ OVERWRITE=TRUE AUTO_COMPRESS=FALSE;
ALTER STAGE SNOWCORE_REAL.APPS.STREAMLIT_STAGE REFRESH;

LIST @SNOWCORE_REAL.APPS.STREAMLIT_STAGE/snowcore_pdm/;

SELECT COUNT(*) N FROM SNOWCORE_REAL.ML.PLANT_B_FAILURE_METRICS;
SELECT COUNT(*) N FROM SNOWCORE_REAL.GOLD.V_ROOT_CAUSE_ALARM;
SELECT COUNT(*) N FROM SNOWCORE_REAL.GOLD.RISK_WORK_ORDER;
```

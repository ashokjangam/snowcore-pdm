# Cortex prompt 038 — upload Streamlit app

Use connection `hackathon`. Change no tables or procedures.

```sql
USE ROLE ACCOUNTADMIN;
USE DATABASE SNOWCORE_REAL;
USE WAREHOUSE COMPUTE_WH;

PUT 'file://C:/Users/C306242/Phoenix/sainathch45/snowcore-pdm/streamlit/app.py'
  @SNOWCORE_REAL.APPS.STREAMLIT_STAGE/snowcore_pdm/
  OVERWRITE=TRUE AUTO_COMPRESS=FALSE;

ALTER STAGE SNOWCORE_REAL.APPS.STREAMLIT_STAGE REFRESH;
LIST @SNOWCORE_REAL.APPS.STREAMLIT_STAGE/snowcore_pdm/;
```

Report staged bytes and last modified only.

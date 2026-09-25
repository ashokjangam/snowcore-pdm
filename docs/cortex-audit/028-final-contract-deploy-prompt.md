# Cortex prompt 028 — final contract and UI deployment

Use the personal hackathon connection, execute the current
`sql/18_piade_erp.sql`, then upload the current `streamlit/app.py` over the
existing `SNOWCORE_REAL.APPS.SNOWCORE_PDM` stage file.

```sql
USE ROLE ACCOUNTADMIN;
USE DATABASE SNOWCORE_REAL;
USE WAREHOUSE COMPUTE_WH;
ALTER SESSION SET TIMEZONE='UTC';
```

Do not alter rules or metrics. Required checks after file 18:

```sql
SELECT COUNT(*) FLEET_ROWS,
       COUNT_IF(STOCK_RISK_COUNT IS NOT NULL) LINE_STOCK_ATTRIBUTIONS
FROM GOLD.V_EXECUTIVE_FLEET;

SELECT STOCK_RISK_COUNT FROM GOLD.V_EXECUTIVE_KPI;

SELECT COUNT(*) THREAD_ROWS,
       COUNT(*)-COUNT(DISTINCT SOURCE_EVENT_ID) DUPLICATE_EVENT_IDS
FROM GOLD.V_DIGITAL_THREAD;
```

Required: five fleet rows, zero line stock attributions, one site-level stock
risk value in KPI, 142,233 thread rows, zero duplicate event IDs, and all file
18 verification gates pass.

Upload:

```sql
PUT 'file://C:/Users/C306242/Phoenix/sainathch45/snowcore-pdm/streamlit/app.py'
  @SNOWCORE_REAL.APPS.STREAMLIT_STAGE/snowcore_pdm/
  OVERWRITE=TRUE AUTO_COMPRESS=FALSE;
ALTER STAGE SNOWCORE_REAL.APPS.STREAMLIT_STAGE REFRESH;
LIST @SNOWCORE_REAL.APPS.STREAMLIT_STAGE/snowcore_pdm/;
```

Smoke-test the exact bounded thread query used by the app:

```sql
SELECT * FROM GOLD.V_DIGITAL_THREAD
WHERE MACHINE_CODE='s_1' ORDER BY STOP_START DESC LIMIT 500;
```

Confirm the returned columns include SOURCE_EVENT_ID, STOP_START, STOP_STATE,
ALARM_CODE, PRODUCTION_ORDER_ID, WORK_ORDER_ID, MATERIAL_ID and origin fields.
Report gate values and staged bytes.

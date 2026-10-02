# PNEUMORA: ship the promoted predictor

Scope only the `PNEUMORA` database with role `PNEUMORA_ROLE` and warehouse
`PNEUMORA_WH`. Do not touch `SNOWCORE_REAL`, `TRIDENT_OPS` or any other database.
Do not edit local files. Never print credentials. Repository root:
`C:/Users/C306242/Phoenix/sainathch45/snowcore-pdm`.

If any statement fails, report it and the error verbatim and stop.

```sql
USE ROLE PNEUMORA_ROLE;
USE WAREHOUSE PNEUMORA_WH;

PUT 'file://C:/Users/C306242/Phoenix/sainathch45/snowcore-pdm/pneumora/data/snowflake/evidence.csv.gz' @PNEUMORA.CORE.LOAD_STAGE AUTO_COMPRESS = FALSE OVERWRITE = TRUE;
PUT 'file://C:/Users/C306242/Phoenix/sainathch45/snowcore-pdm/pneumora/data/snowflake/work_orders.csv.gz' @PNEUMORA.CORE.LOAD_STAGE AUTO_COMPRESS = FALSE OVERWRITE = TRUE;
TRUNCATE TABLE PNEUMORA.ML.EVIDENCE;
TRUNCATE TABLE PNEUMORA.OPS.WORK_ORDERS;
COPY INTO PNEUMORA.ML.EVIDENCE FROM @PNEUMORA.CORE.LOAD_STAGE/evidence.csv.gz FILE_FORMAT = PNEUMORA.CORE.CSV_GZ ON_ERROR = ABORT_STATEMENT;
COPY INTO PNEUMORA.OPS.WORK_ORDERS FROM @PNEUMORA.CORE.LOAD_STAGE/work_orders.csv.gz FILE_FORMAT = PNEUMORA.CORE.CSV_GZ ON_ERROR = ABORT_STATEMENT;

PUT 'file://C:/Users/C306242/Phoenix/sainathch45/snowcore-pdm/pneumora/sis/app.py' @PNEUMORA.APP.STREAMLIT_STAGE AUTO_COMPRESS = FALSE OVERWRITE = TRUE;
PUT 'file://C:/Users/C306242/Phoenix/sainathch45/snowcore-pdm/pneumora/sis/status_rules.py' @PNEUMORA.APP.STREAMLIT_STAGE AUTO_COMPRESS = FALSE OVERWRITE = TRUE;
ALTER STAGE PNEUMORA.APP.STREAMLIT_STAGE REFRESH;
ALTER STREAMLIT PNEUMORA.APP.PNEUMORA_COPILOT SET TITLE = 'PNEUMORA early air-leak predictor'
  COMMENT = 'PNEUMORA leak predictor: track record, prediction studies, cited RCA and action log';
```

Then report:

- `SELECT COUNT(*) FROM PNEUMORA.ML.EVIDENCE;` (expect 6) and `SELECT COUNT(*) FROM PNEUMORA.OPS.WORK_ORDERS;` (expect 41)
- `SELECT DOC_KEY, PARSE_JSON(DOC_JSON):status::STRING AS STATUS FROM PNEUMORA.ML.EVIDENCE ORDER BY 1;`
- `SELECT PARSE_JSON(DOC_JSON):held_out_pooled AS HELD_OUT FROM PNEUMORA.ML.EVIDENCE WHERE DOC_KEY = 'prediction';`
- `LIST @PNEUMORA.APP.STREAMLIT_STAGE;` (name, size)
- `SHOW STREAMLITS IN SCHEMA PNEUMORA.APP;` (name, title, url_id)

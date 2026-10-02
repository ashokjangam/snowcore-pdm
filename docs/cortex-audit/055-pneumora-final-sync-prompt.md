# PNEUMORA: final app sync and demo rehearsal

Scope only the `PNEUMORA` database with role `PNEUMORA_ROLE` and warehouse
`PNEUMORA_WH`. Do not touch `SNOWCORE_REAL`, `TRIDENT_OPS` or any other database.
Do not edit local files. Never print credentials. The repository root is
`C:/Users/C306242/Phoenix/sainathch45/snowcore-pdm`.

If any statement fails, report it and the error verbatim and stop.

## 1. Sync the app source

```sql
USE ROLE PNEUMORA_ROLE;
USE WAREHOUSE PNEUMORA_WH;
PUT 'file://C:/Users/C306242/Phoenix/sainathch45/snowcore-pdm/pneumora/sis/app.py' @PNEUMORA.APP.STREAMLIT_STAGE AUTO_COMPRESS = FALSE OVERWRITE = TRUE;
ALTER STAGE PNEUMORA.APP.STREAMLIT_STAGE REFRESH;
ALTER TABLE PNEUMORA.CORE.TELEMETRY_5M SET COMMENT = 'Observed MetroPT-3 telemetry, 5-minute means, with the frozen leak-detector flag';
ALTER TABLE PNEUMORA.ML.ALERTS SET COMMENT = 'Leak-detector alerts and existing low-pressure alarm episodes, scored against reported failures';
```

Report `LIST @PNEUMORA.APP.STREAMLIT_STAGE;` (name, size) and
`SHOW STREAMLITS IN SCHEMA PNEUMORA.APP;` (name, title, url_id).

## 2. Rehearse the demo prompts

Follow `docs/demo/01_detect.txt` exactly, then `docs/demo/02_rca.txt` exactly. Both are
read only. Report the tables you showed and the final answers verbatim.
Do not run `docs/demo/03_action.txt`.

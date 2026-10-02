# PNEUMORA: reload export, rerun native anomaly detection, redeploy the app

Scope only the `PNEUMORA` database with role `PNEUMORA_ROLE` and warehouse
`PNEUMORA_WH`. Do not touch `SNOWCORE_REAL`, `TRIDENT_OPS` or any other database.
Do not edit local files. Never print credentials. The repository root is
`C:/Users/C306242/Phoenix/sainathch45/snowcore-pdm`; substitute it for `<REPO_ROOT>`.

Run the steps in order. If any statement fails, report the failing statement and the
error verbatim and stop. Do not change the SQL to make it pass.

## 1. Reload the export

TRUNCATE each table, then run every statement in `pneumora/sql/02_load.sql`:
`PNEUMORA.CORE.TELEMETRY_5M`, `PNEUMORA.CORE.FAILURES`, `PNEUMORA.ML.FAILURE_ZOOM`,
`PNEUMORA.ML.ALERTS`, `PNEUMORA.ML.EVIDENCE`, `PNEUMORA.OPS.WORK_ORDERS`,
`PNEUMORA.OPS.PARTS`, `PNEUMORA.OPS.TECHNICIANS`, `PNEUMORA.CORE.DAILY_KPIS`,
`PNEUMORA.OPS.FACTORY_SCENARIO`. Report the row count of each table afterwards.
Expected: 50782, 4, 1095, 132, 5, 41, 6, 6, 214, 214.

## 2. Native anomaly detection

Execute every statement in `pneumora/sql/05_native_ml.sql`, in order. The previous run
failed because `DETECT_ANOMALIES` could not expand a view over another schema. The
inputs are now materialised tables. Then report verbatim:

- `SELECT * FROM PNEUMORA.ML.NATIVE_ANOMALY_SUMMARY;`
- `SELECT FAILURE_ID, START_TS, ONSET_PRECISION, FIRST_BEFORE_ONSET, FIRST_IN_TIME, DATEDIFF('minute', FIRST_IN_TIME, START_TS) AS MINUTES_BEFORE_START FROM PNEUMORA.ML.NATIVE_ANOMALY_EVAL ORDER BY START_TS;`
- `SELECT COUNT(*), SUM(IFF(IS_ANOMALY,1,0)) FROM PNEUMORA.ML.NATIVE_ANOMALIES;`
- `SELECT COUNT(*) FROM PNEUMORA.ML.LEAK_SIGNAL_TRAIN;` and the same for `PNEUMORA.ML.LEAK_SIGNAL_SCORE`.

## 3. Redeploy the app

Execute every statement in `pneumora/sql/03_deploy_app.sql`. Then report:

- `LIST @PNEUMORA.APP.STREAMLIT_STAGE;` (names and sizes)
- `SHOW STREAMLITS IN SCHEMA PNEUMORA.APP;` (name, title, url_id, query_warehouse)
- `DESCRIBE STREAMLIT PNEUMORA.APP.PNEUMORA_COPILOT;` (runtime_name, main_file)

## 4. Smoke tests

- Structured Cortex call, report the returned value:
  `SELECT AI_COMPLETE(model => 'llama3.3-70b', prompt => 'Reply with one short sentence: what does a falling compressor idle pressure decay suggest?', response_format => TYPE OBJECT(answer STRING)) AS R;`
- `CALL PNEUMORA.OPS.RECORD_ACTION('SMOKE|DEPLOY', 'INSPECT', 'post-deploy smoke', CURRENT_USER());`
  twice. Report both results. Then `DELETE FROM PNEUMORA.OPS.ACTION_LOG WHERE SOURCE_KEY = 'SMOKE|DEPLOY';`
  and confirm zero rows remain.
- `SELECT DOC_ID FROM PNEUMORA.ML.EVIDENCE ORDER BY 1;` (column may be named differently; list the key column).

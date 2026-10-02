# PNEUMORA: action log and Snowflake-native anomaly detection

Scope only the `PNEUMORA` database with role `PNEUMORA_ROLE` and warehouse
`PNEUMORA_WH`. Do not touch `SNOWCORE_REAL`, `TRIDENT_OPS` or any other database.
Do not edit local files.

1. Execute every statement in `pneumora/sql/04_actions.sql` exactly as written.
2. Smoke-test idempotency, then clean up:
   - `CALL PNEUMORA.OPS.RECORD_ACTION('SMOKE|TEST', 'ACKNOWLEDGE', 'smoke test', CURRENT_USER());` twice.
   - Report both results. The second must return the same `action_id` with `deduplicated = true`.
   - `DELETE FROM PNEUMORA.OPS.ACTION_LOG WHERE SOURCE_KEY = 'SMOKE|TEST';` and confirm zero rows remain.
3. Execute every statement in `pneumora/sql/05_native_ml.sql` exactly as written, in order.
4. Report verbatim:
   - `SELECT * FROM PNEUMORA.ML.NATIVE_ANOMALY_SUMMARY;`
   - `SELECT FAILURE_ID, START_TS, ONSET_PRECISION, FIRST_BEFORE_ONSET, FIRST_IN_TIME, DATEDIFF('minute', FIRST_IN_TIME, START_TS) AS MINUTES_BEFORE_START FROM PNEUMORA.ML.NATIVE_ANOMALY_EVAL ORDER BY START_TS;`
   - `SELECT COUNT(*), SUM(IFF(IS_ANOMALY,1,0)) FROM PNEUMORA.ML.NATIVE_ANOMALIES;`

Report any error verbatim with the failing statement. Do not change the SQL to make it
pass; if a statement fails, stop and report.

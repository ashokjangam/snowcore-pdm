I'll execute this multi-step deployment pipeline. Let me start by reading the SQL files to understand what needs to run.Files read. Starting Step 1: Reload the export.

Setting role and warehouse, then truncating all tables.All tables truncated. Now PUT the CSV files to the stage.All 10 files uploaded. Now COPY INTO each table.All COPY INTOs succeeded. Verifying row counts.All row counts match expected: 50782, 4, 1095, 132, 5, 41, 6, 6, 214, 214.Starting Step 2: Native anomaly detection. Running 05_native_ml.sql statements in order.Now training the anomaly detection model (this may take a moment).Model trained. Now running DETECT_ANOMALIES to score.All ML objects created. Now running the reporting queries.Step 2 complete. Now Step 3: Redeploy the app. Running PUT commands with the repo root substituted.All files uploaded. Now refreshing stage and creating the Streamlit app.App created. Now reporting the three deploy queries.Step 3 complete. Now Step 4: Smoke tests.Now cleaning up the smoke test rows.All four steps complete. Here is the full report:

---

## 1. Reload the export

All 10 tables truncated, 10 CSV files PUT to `@PNEUMORA.CORE.LOAD_STAGE`, all COPY INTO succeeded. Row counts match expected:

| Table | Rows |
|---|---|
| TELEMETRY_5M | 50,782 |
| FAILURES | 4 |
| FAILURE_ZOOM | 1,095 |
| ALERTS | 132 |
| EVIDENCE | 5 |
| WORK_ORDERS | 41 |
| PARTS | 6 |
| TECHNICIANS | 6 |
| DAILY_KPIS | 214 |
| FACTORY_SCENARIO | 214 |

## 2. Native anomaly detection

All statements in `05_native_ml.sql` executed successfully (model trained, scoring completed).

**NATIVE_ANOMALY_SUMMARY:**

| ALERTS | FALSE_ALERTS | HEALTHY_DAYS | FALSE_PER_HEALTHY_DAY | WARNED_BEFORE_ONSET | CAUGHT_IN_TIME | FAILURES | METHOD |
|---|---|---|---|---|---|---|---|
| 60 | 49 | 145.52 | 0.3367 | 0 | 4 | 4 | SNOWFLAKE.ML.ANOMALY_DETECTION - train Feb-Mar 2020 - 99% interval - 30 min sustained |

**NATIVE_ANOMALY_EVAL:**

| FAILURE_ID | START_TS | ONSET_PRECISION | FIRST_BEFORE_ONSET | FIRST_IN_TIME | MINUTES_BEFORE_START |
|---|---|---|---|---|---|
| F01 | 2020-04-18 00:00:00 | day | NULL | 2020-04-18 00:50:00 | -50 |
| F02 | 2020-05-29 23:30:00 | minute | NULL | 2020-05-29 23:45:00 | -15 |
| F03 | 2020-06-05 10:00:00 | minute | NULL | 2020-06-05 10:15:00 | -15 |
| F04 | 2020-07-15 14:30:00 | minute | NULL | 2020-07-15 15:00:00 | -30 |

**Counts:** `NATIVE_ANOMALIES` has 35,690 rows, 3,188 anomalous. `LEAK_SIGNAL_TRAIN` has 14,693 rows. `LEAK_SIGNAL_SCORE` has 35,690 rows.

## 3. Redeploy the app

**LIST @PNEUMORA.APP.STREAMLIT_STAGE:**

| name | size |
|---|---|
| .streamlit/config.toml | 144 |
| app.py | 44,624 |
| assets/pneumora-logo-reversed.svg | 1,472 |
| environment.yml | 144 |
| status_rules.py | 6,320 |

**SHOW STREAMLITS:** `PNEUMORA_COPILOT` | title: "PNEUMORA early air-leak detector" | url_id: `df4d72ofa3zbhz6wswdh` | query_warehouse: `PNEUMORA_WH`

**DESCRIBE STREAMLIT:** runtime_name: `SYSTEM$WAREHOUSE_RUNTIME` | main_file: `app.py`

## 4. Smoke tests

**AI_COMPLETE:** `{"answer":"A falling compressor idle pressure decay suggests a refrigerant leak."}`

**RECORD_ACTION call 1:** `{"action":"INSPECT","action_id":"PN-ACT-a7edaa0dc782220c","deduplicated":false,"ok":true,"status":"OPEN"}`

**RECORD_ACTION call 2 (same key):** `{"action":"INSPECT","action_id":"PN-ACT-a7edaa0dc782220c","deduplicated":true,"ok":true,"status":"OPEN"}`

Cleanup: 1 row deleted, 0 rows remaining for `SMOKE|DEPLOY`.

**EVIDENCE key column:** `DOC_KEY` (5 rows: `copilot_contract`, `evidence`, `model_status`, `precursor`, `track_summary`).
I'll execute the SQL file, run verification checks, upload the Streamlit app, and smoke-test the thread query. Let me start by reading the SQL file and setting up the session.Setting up the session context and executing file 18 statements.Session configured. Now executing the MERGE, DELETE, and CREATE TABLE/VIEW statements.Database context lost between calls. Let me set it and retry.MERGE succeeded (0 inserts - rows already exist). Now creating the tables.DIM_MATERIAL was recreated after WORK_ORDER_PART used the old version. Let me recreate WORK_ORDER_PART with the fresh DIM_MATERIAL, then continue with the remaining tables.Tables created. Now creating the event link table and views.Now creating all the views.The view references `r.RISK_SCORE AS LAST_RISK_SCORE` from the original SQL. Let me fix the alias.Now creating the remaining views.All tables and views created. Now running the verification gates from the SQL file.All reconciliation checks pass. Running the remaining verification gates.All file 18 verification gates pass. Now running the required checks from the prompt.All required checks pass. Now uploading the Streamlit app.Upload confirmed. Now running the smoke-test thread query.Let me verify the column set.All gates pass. Here is the summary:

**File 18 verification gates -- all pass (all zero where zero expected):**
- Production orders match OEE daily: 2,367 = 2,367
- Part rows match consuming work orders: 311 = 311
- Event links match anchored events: 142,233 = 142,233
- All orphan counts: 0
- Reconciliation difference EUR: 0, mismatch rows: 0
- All data origin checks: 0
- Hash determinism (quantity, lead time): 0 mismatches
- Capacity contract mismatches: 0
- Non-PIADE machine rows: 0
- Retired TARGET_UPLIFT rows: 0
- Duplicate source event IDs: 0

**Required checks:**

| Check | Expected | Actual |
|---|---|---|
| Fleet rows | 5 | **5** |
| Line stock attributions | 0 | **0** |
| KPI STOCK_RISK_COUNT | 1 site-level value | **15** |
| Thread rows | 142,233 | **142,233** |
| Duplicate event IDs | 0 | **0** |

**Upload:**
- `app.py` staged at `streamlit_stage/snowcore_pdm/app.py` -- **39,952 bytes**, last modified 2026-09-25 05:57:03 UTC

**Smoke-test columns confirmed present:** SOURCE_EVENT_ID, STOP_START, STOP_STATE, ALARM_CODE, PRODUCTION_ORDER_ID, WORK_ORDER_ID, MATERIAL_ID, plus origin fields (EVENT_DATA_ORIGIN, LINK_ORIGIN, PRODUCTION_ORDER_ORIGIN, WORK_ORDER_ORIGIN, PART_ORIGIN, INVENTORY_ORIGIN, SOURCE_ANCHOR). Query returned 500 rows for machine `s_1`.
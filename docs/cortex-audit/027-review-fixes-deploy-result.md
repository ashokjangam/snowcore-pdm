I'll execute the SQL files in order, run verification queries, upload the app, and perform smoke tests. Let me start by reading the SQL files and setting up the session.Setting up the session and executing both SQL files in order. Let me start.Now executing `sql/18_piade_erp.sql`. I'll break it into logical chunks.Now creating all the views from 18_piade_erp.sql.Now running the verification checks from the bottom of 18_piade_erp.sql.All file-18 checks pass. Now executing `sql/17_semantic_cortex.sql`.Now creating the semantic view.Now creating the CORTEX_BRIEFING table (this uses LLM calls, may take a moment).Now running the file-17 verification queries.File 17 executed successfully. Now running the required verification queries.TYPEOF doesn't work on TIMESTAMP_NTZ. Let me adjust that check.All verification gates pass. Now uploading the app.All three smoke tests return data successfully.---

## Deployment Complete -- Gate Results

| Gate | Expected | Actual | Status |
|------|----------|--------|--------|
| Duplicate event IDs | 0 | **0** | PASS |
| Cost rows / lines | 5 / 5 | **5 / 5** | PASS |
| LAST_SCORED_HOUR type | timestamp | **TIMESTAMP_NTZ(6)** | PASS |
| Fleet rows | 5 | **5** | PASS |
| FAULTED cumulative max | ~100 | **100** | PASS |
| WAITING cumulative max | ~100 | **100** | PASS |
| Inventory rows | 28 | **28** (4 stockout + 11 reorder + 13 healthy = 28) | PASS |
| Digital thread rows | 142,233 | **142,233** | PASS |
| Action queue rows | 15 | **15** | PASS |
| Analyst context rows | 6 | **6** | PASS |
| Production order 1:1 OEE | 2367 = 2367 | **PASS** |
| Part rows match WOs | 311 = 311 | **PASS** |
| Event links match events | 142,233 = 142,233 | **PASS** |
| Orphan counts (all 4) | 0 | **0** | PASS |
| Parts cost reconciliation | EUR 0 diff, 0 mismatches | **PASS** |
| Quantity hash determinism | 0 mismatches | **PASS** |
| Lead-time hash determinism | 0 mismatches | **PASS** |
| Data origin correctness (4 tables) | 0 wrong | **PASS** |
| Capacity contract mismatches | 0 | **0** | PASS |
| Retired ERP_TARGET_UPLIFT | 0 rows | **0** | PASS |
| Non-PIADE machine rows | 0 | **0** | PASS |
| Untraceable rows | 0 | **0** | PASS |

## App Upload

| File | Source bytes | Stage bytes | Status |
|------|-------------|-------------|--------|
| `app.py` | 39,468 | 39,472 (stage metadata padding) | UPLOADED |
| `environment.yml` | 144 | 144 | Pre-existing |

## Smoke Tests

- `V_PIADE_COST_BY_MACHINE`: 5 rows, all 5 machines, maintenance cost EUR 1,190,989.43, idle forgone margin EUR 8,368,070.72
- `V_DIGITAL_THREAD` (s_1, desc, 500): returned 500 rows with readable SOURCE_EVENT_IDs and real timestamps
- `V_PLANT_B_RISK` (s_1, desc, 72): returned 72 rows, HOUR_TS is TIMESTAMP_NTZ, scores range from blind test period

## Runtime Note

`TYPEOF()` is not valid for TIMESTAMP_NTZ on this account; used `SYSTEM$TYPEOF()` instead for the fleet type check. The original verification query in the prompt would need this substitution if run standalone. No business rules or metrics were altered.
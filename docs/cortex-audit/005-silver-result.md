I'll start by reading the SQL file to understand what needs to be executed.Now I'll execute each statement in order. I'll batch the setup and DDL statements, then run the reconciliation queries.Session setup complete. Now creating tables.The COMMENT ran before the CREATE (parallel execution). Let me re-run the comment now that the table exists.**DIM_PLANT**: Created successfully, comment applied.**DIM_MACHINE**: Created successfully, comment applied.**PIADE_INTERVAL**: Created successfully, comment applied.**COMOPI_SENSOR_10MIN**: Created successfully, comment applied.**COMOPI_ALARM_10MIN**: Created successfully, comment applied. All 6 tables created. Now running the 3 reconciliation queries.ROWS is a reserved word. Let me re-run that query with quoting.All statements executed successfully. Here are the full results and cross-check.

---

## Reconciliation Query 1 — Row Counts

| Table | Actual Rows | Expected | Match |
|---|---|---|---|
| DIM_PLANT | 2 | — | n/a |
| DIM_MACHINE | **13** | 13 | **Yes** |
| PIADE_INTERVAL | **429,394** | 429,394 | **Yes** |
| COMOPI_SENSOR_10MIN | **15,704** | 15,704 | **Yes** |
| COMOPI_ALARM_10MIN | **150,650** | 150,650 | **Yes** |

DIM_MACHINE has 13 rows total (8 Plant A + 5 Plant B as expected).

## Reconciliation Query 2 — PIADE_INTERVAL Breakdown

| Metric | Value |
|---|---|
| INTERVALS | 429,394 |
| COUNTER_RESETS | **86** |
| NULL_OUTPUT_DELTAS | 87 |
| RUNNING_INTERVALS | 265,379 |
| PLANNED_STOPS | 21,782 |
| UNPLANNED_STOPS | 142,233 |
| TOTAL_HOURS | 44,130.6 |

Counter resets: **86** — matches the expected 86.

## Reconciliation Query 3 — Alarm Windows

| Metric | Value |
|---|---|
| PUBLISHED_FAULT_WINDOWS | **41** |
| MODULE_ALARM_WINDOWS | **1,555** |
| MACHINES | 8 |

Published fault windows: **41** — matches. Module alarm windows: **1,555** — matches.

---

## Cross-Check Summary

Every measured value matches the expected profile exactly:

- PIADE_INTERVAL: 429,394 rows
- COMOPI_SENSOR_10MIN: 15,704 rows
- COMOPI_ALARM_10MIN: 150,650 rows
- DIM_MACHINE: 13 rows (8 Plant A + 5 Plant B)
- Published fault windows: 41
- Module alarm windows: 1,555
- Counter resets: 86

**No mismatches detected.** The silver layer is fully reconciled against the source profile.
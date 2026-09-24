# Cortex prompt 007 — re-run Gold with the overlap flag

```text
Re-execute sql/13_gold_oee.sql against the hackathon connection using the
Snowflake SQL tool. It now adds a HAS_OVERLAP_ANOMALY column that marks the
three hours holding more than 3,600 seconds, caused by six overlapping source
intervals on daylight-saving fallback dates.

Fully qualify object names or include USE DATABASE SNOWCORE_REAL and
USE WAREHOUSE COMPUTE_WH in the same call as each statement.

Report only reporting queries 2, 2b and 3:
- query 2: HOURLY_ROWS, AVG_SEC_PER_HOUR, MAX_SEC_PER_HOUR, HOURS_OVER_3600,
  FLAGGED_ANOMALIES, MAX_SEC_EXCLUDING_FLAGGED
- query 2b: the full list of flagged hours with machine and timestamp
- query 3: the hourly OEE summary row

Then state plainly whether MAX_SEC_EXCLUDING_FLAGGED is at or below 3,600 and
whether the flagged hours fall in late October, which is what the
daylight-saving explanation predicts.

Do not modify anything outside SNOWCORE_REAL. Report only returned values.
```

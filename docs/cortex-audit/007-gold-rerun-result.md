I'll read the SQL file first, then execute it.Now I'll execute the script. I'll run the DDL statements first, then the three reporting queries.Context didn't stick across calls. I'll fully qualify all objects going forward.Now I'll create the remaining tables and then run the three reporting queries.All DDL complete. Now running the three reporting queries.All tables rebuilt and queries returned. Here are the results.

---

**Query 2 — Splitting sanity check**

| Metric | Value |
|---|---|
| HOURLY_ROWS | 45,625 |
| AVG_SEC_PER_HOUR | 3,482.1 |
| MAX_SEC_PER_HOUR | 7,200.0 |
| HOURS_OVER_3600 | 3 |
| FLAGGED_ANOMALIES | 3 |
| MAX_SEC_EXCLUDING_FLAGGED | **3,600.0** |

**Query 2b — Flagged hours (full list)**

| MACHINE_CODE | OEE_HOUR (UTC) | TOTAL_SEC | SEGMENT_COUNT |
|---|---|---|---|
| s_1 | 2020-10-25 22:00 +0000 | 7,200.0 | 9 |
| s_1 | 2021-10-31 22:00 +0000 | 7,200.0 | 11 |
| s_3 | 2021-10-31 21:00 +0000 | 7,200.0 | 13 |

**Query 3 — Hourly OEE summary**

| Metric | Value |
|---|---|
| HOURLY_ROWS | 45,625 |
| ROWS_WITH_OEE | 30,253 |
| QUALITY_CLAMPED_ROWS | 6,089 |
| AVG_AVAILABILITY | 0.5773 |
| AVG_PERFORMANCE | 0.6343 |
| AVG_QUALITY | 0.9668 |
| AVG_OEE | 0.5711 |
| AVAILABILITY_OVER_ONE | 0 |
| PERFORMANCE_OVER_ONE | 0 |

---

**Assessment:**

**MAX_SEC_EXCLUDING_FLAGGED is exactly 3,600.0** — at the theoretical ceiling and not above it. Once the three flagged hours are excluded, no hour in the dataset exceeds a full hour of machine time. The splitting logic is correct.

**The flagged hours fall on 2020-10-25 and 2021-10-31**, both late-October dates. These are the European summer-time-to-winter-time (CEST to CET) fallback dates. Each flagged hour holds exactly 7,200 seconds (two hours' worth), consistent with the logger recording the repeated "fall-back" hour twice. This matches the daylight-saving explanation precisely.
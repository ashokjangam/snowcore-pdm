I'll read the SQL script first, then execute it.Executing the DDL statements first.Now creating the interval segment table (the core hour-splitting logic).All DDL succeeded. Now running the 6 reporting queries.Now getting the segment row count.All statements executed successfully. Here are the full results and analysis.

---

## Report 1 — Ideal Rates

| MACHINE_CODE | IDEAL_RATE_PPH | P99_SPEED_PPH | MEDIAN_SPEED_PPH |
|---|---|---|---|
| s_1 | 5,000 | 4,650 | 4,500 |
| s_2 | 6,500 | 6,500 | 6,500 |
| s_3 | 4,800 | 4,800 | 4,000 |
| s_4 | 6,500 | 6,500 | 5,656 |
| s_5 | 6,500 | 6,500 | 6,175 |

## Report 2 — Splitting Sanity

| HOURLY_ROWS | AVG_SEC_PER_HOUR | MAX_SEC_PER_HOUR | HOURS_OVER_3600 |
|---|---|---|---|
| 45,625 | 3,482.1 | 7,200.0 | 3 |

## Report 3 — Hourly OEE Summary

| HOURLY_ROWS | ROWS_WITH_OEE | QUALITY_CLAMPED_ROWS | AVG_AVAILABILITY | AVG_PERFORMANCE | AVG_QUALITY | AVG_OEE | AVAILABILITY_OVER_ONE | PERFORMANCE_OVER_ONE |
|---|---|---|---|---|---|---|---|---|
| 45,625 | 30,253 | 6,089 | 0.5773 | 0.6343 | 0.9668 | 0.5711 | 0 | 0 |

## Report 4 — Per-Machine Daily OEE

| MACHINE_CODE | DAYS | AVAILABILITY | PERFORMANCE | QUALITY | OEE | DAYS_QUALITY_CLAMPED |
|---|---|---|---|---|---|---|
| s_1 | 666 | 0.7498 | 0.6962 | 0.9962 | 0.5370 | 49 |
| s_2 | 458 | 0.3930 | 0.6849 | 0.9892 | 0.2910 | 0 |
| s_3 | 360 | 0.4934 | 0.7341 | 0.9974 | 0.3667 | 0 |
| s_4 | 384 | 0.6861 | 0.5373 | 0.9905 | 0.3705 | 58 |
| s_5 | 499 | 0.5961 | 0.6842 | 0.9579 | 0.5158 | 0 |

## Report 5 — Validation Against Publisher Aggregate

| MATCHED_HOURS | AVG_RUN_DIFF | MEDIAN_RUN_DIFF | MAX_RUN_DIFF | AVG_DOWNTIME_DIFF | AVG_IDLE_DIFF | HOURS_WITHIN_2PCT | HOURS_WITHIN_5PCT |
|---|---|---|---|---|---|---|---|
| 23,376 | 0.06752 | 0.02388 | 0.99997 | 0.04118 | 0.02791 | 10,770 | 15,711 |

## Report 6 — Downtime Events

| DOWNTIME_EVENTS | EVENTS_WITH_ALARM | TOTAL_STOP_MINUTES |
|---|---|---|
| 142,233 | 92,084 | 804,809 |

## GOLD.PIADE_INTERVAL_SEGMENT Row Count: **472,659**

---

## Answers

### 1. Splitting Sanity

**HOURS_OVER_3600 is NOT zero — it is 3.** AVG_SEC_PER_HOUR is 3,482.1 and MAX_SEC_PER_HOUR is **7,200.0**, which exceeds the 3,600-second cap. Three hours contain more than 3,600 seconds of machine time. The average dropped dramatically from the previous 4,310 to 3,482.1, and the worst case dropped from 79,290 to 7,200, but the splitting did not fully eliminate the problem. The 7,200 maximum suggests a two-hour interval that was not split — possibly an edge case in the ARRAY_GENERATE_RANGE logic or a timezone boundary issue.

### 2. Availability and Performance Over One

Both **AVAILABILITY_OVER_ONE and PERFORMANCE_OVER_ONE are zero.** The LEAST(..., 1.0) clamps are working correctly; no hour has a ratio exceeding 1.0.

### 3. Quality Clamped Share

- **Hourly**: 6,089 of 30,253 rows with OEE have QUALITY_CLAMPED = TRUE — **20.1%** of OEE-bearing hours.
- **Daily**: Quality clamped days by machine: s_1 = 49, s_4 = 58, s_2/s_3/s_5 = 0. Out of total daily rows (666+458+360+384+499 = 2,367), that is 107 days or **4.5%**.

### 4. Average OEE Components (Hourly)

| Metric | Value |
|---|---|
| Availability | 57.73% |
| Performance | 63.43% |
| Quality | 96.68% |
| **OEE** | **57.11%** |

### 5. Validation

- **MATCHED_HOURS**: 23,376
- **AVG_RUN_DIFF**: 0.06752
- **MEDIAN_RUN_DIFF**: 0.02388
- **HOURS_WITHIN_2PCT**: 10,770 (46.1%)
- **HOURS_WITHIN_5PCT**: 15,711 (67.2%)

**Did the splitting fix improve agreement?** Yes, substantially. The previous average run-fraction difference was **0.33931**. The new AVG_RUN_DIFF is **0.06752** — an **80% reduction** in average disagreement. The median is even better at 0.02388, and 67% of hours now agree within 5 percentage points. However, there is still a tail of high-disagreement hours (max diff 0.99997), and the 3 hours exceeding 3,600 seconds indicate residual edge cases in the splitting logic.

### 6. GOLD.PIADE_INTERVAL_SEGMENT Row Count

**472,659** rows (up from the 429,394 source intervals, reflecting the expansion from hour-boundary splitting).**Summary**: All 6 Gold OEE objects were created successfully. The hour-boundary splitting reduced the average run-fraction disagreement with the publisher from 0.33931 to 0.06752 (80% improvement), but 3 hours still exceed 3,600 seconds (max 7,200s), indicating a residual edge case worth investigating — likely an off-by-one in the hour range generation or a timezone conversion boundary.
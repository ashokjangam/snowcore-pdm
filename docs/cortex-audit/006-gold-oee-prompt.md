# Cortex prompt 006 — execute Gold OEE (v2, with hour-boundary splitting)

The first version attributed each interval wholly to its starting hour. That
overfilled hours (mean 4,310 seconds in a 3,600-second hour) and the comparison
against the publisher's hourly aggregate diverged by 34 percentage points on
average. This version splits intervals at hour boundaries.

```text
Execute the reviewed script sql/13_gold_oee.sql against the hackathon connection
using the Snowflake SQL tool. It replaces the previous Gold OEE objects.

Session context does not persist between SQL tool calls, so fully qualify object
names or include USE DATABASE SNOWCORE_REAL and USE WAREHOUSE COMPUTE_WH in the
same call as the statement.

Run statements in file order, then report the full result rows of all six
reporting queries.

Answer these plainly:
1. Splitting sanity: is HOURS_OVER_3600 zero, and what are AVG_SEC_PER_HOUR and
   MAX_SEC_PER_HOUR? MAX must not exceed 3,600.
2. Are AVAILABILITY_OVER_ONE and PERFORMANCE_OVER_ONE both zero?
3. What share of OEE rows have QUALITY_CLAMPED = TRUE, hourly and daily?
4. Average Availability, Performance, Quality, OEE.
5. Validation: MATCHED_HOURS, AVG_RUN_DIFF, MEDIAN_RUN_DIFF, HOURS_WITHIN_2PCT
   and HOURS_WITHIN_5PCT. State clearly whether the splitting fix improved the
   agreement with the publisher aggregate compared with the previous average
   run-fraction difference of 0.33931.
6. Also report GOLD.PIADE_INTERVAL_SEGMENT row count.

Constraints:
- Do not modify anything outside SNOWCORE_REAL.
- If a statement fails, report the exact error and stop.
- Do not change any OEE formula, clamp, or threshold to improve a number.
- Report only what the queries return.
```

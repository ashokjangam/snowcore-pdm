# Cortex prompt 005 — execute Silver

```text
Execute the reviewed script sql/12_silver.sql against the hackathon connection
using the Snowflake SQL tool.

Session context does not persist between SQL tool calls, so include
USE DATABASE SNOWCORE_REAL and USE WAREHOUSE COMPUTE_WH in the same call as
each statement, or fully qualify every object name.

Run the statements in file order. Report the result of every CREATE TABLE and
COMMENT statement, then report the full result rows of the three reconciliation
queries at the end of the file.

Cross-check these against the measured profile and tell me about any mismatch:
- PIADE_INTERVAL should have 429,394 rows
- COMOPI_SENSOR_10MIN should have 15,704 rows
- COMOPI_ALARM_10MIN should have 150,650 rows
- DIM_MACHINE should have 13 rows (8 for Plant A, 5 for Plant B)
- published fault windows should be 41
- module alarm windows should be 1,555
- counter resets should be 86 in total

Constraints:
- Do not modify anything outside SNOWCORE_REAL.
- If a statement fails, report the exact Snowflake error and stop. Do not
  rewrite the business logic to make it pass.
- Report only values the queries actually return.
```

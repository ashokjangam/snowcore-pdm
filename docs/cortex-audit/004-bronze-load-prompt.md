# Cortex prompt 004 — execute the Bronze load

```text
Execute the reviewed script sql/11_bronze_load.sql against the hackathon connection
using the Snowflake SQL tool.

Important: session context does not persist between SQL tool calls, so prefix every
statement with the database explicitly or re-issue USE DATABASE SNOWCORE_REAL and
USE WAREHOUSE COMPUTE_WH in the same call as the statement it applies to.

Run the statements in file order. For each CREATE TABLE report success, for each
COPY INTO report rows_loaded and any errors, and for each verification SELECT report
LOADED_ROWS, EXPECTED_ROWS and ROWS_MATCH.

Then finish with a single summary table of the four Bronze tables showing loaded rows
versus expected rows and whether they match.

Constraints:
- Do not modify anything outside SNOWCORE_REAL.
- If a COPY fails, report the exact Snowflake error. Do not silently change the
  file format, the column list, or ON_ERROR to work around it.
- Do not fabricate row counts. Report only what the queries return.
```

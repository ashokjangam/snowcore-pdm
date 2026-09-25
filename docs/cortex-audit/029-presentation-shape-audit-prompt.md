# Cortex prompt 029 — blank trend chart diagnosis

Read-only. Create, alter, or drop nothing. Run exactly the queries below and
report the raw results as compact tables. Do not explore anything else.

```sql
USE ROLE ACCOUNTADMIN;
USE DATABASE SNOWCORE_REAL;
USE WAREHOUSE COMPUTE_WH;
ALTER SESSION SET TIMEZONE='UTC';

DESCRIBE VIEW GOLD.V_OEE_DAILY;

SELECT COUNT(*) TOTAL_ROWS,
       COUNT(DISTINCT MACHINE_CODE) MACHINES,
       COUNT(DISTINCT OEE_DATE) DISTINCT_DATES,
       MIN(OEE_DATE) MIN_DATE,
       MAX(OEE_DATE) MAX_DATE,
       COUNT_IF(OEE IS NULL) NULL_OEE,
       MIN(OEE) MIN_OEE,
       MAX(OEE) MAX_OEE,
       COUNT_IF(OEE > 1) OEE_ABOVE_ONE
FROM GOLD.V_OEE_DAILY;

SELECT MACHINE_CODE, OEE_DATE, OEE FROM GOLD.V_OEE_DAILY
ORDER BY OEE_DATE DESC LIMIT 5;
```

Report:

1. The declared SQL type of `OEE_DATE` and of `OEE` from the DESCRIBE output.
2. Total rows, machine count, distinct date count, and date range.
3. Whether any `OEE` values are NULL or greater than 1.

That is the entire task. Report the numbers and stop.

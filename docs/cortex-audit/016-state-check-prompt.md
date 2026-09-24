Quick state check. Read-only, no DDL, no table creation.

Session setup first:

    USE ROLE ACCOUNTADMIN;
    USE DATABASE SNOWCORE_REAL;
    USE WAREHOUSE COMPUTE_WH;
    ALTER SESSION SET TIMEZONE = 'UTC';

A previous run was interrupted partway through rebuilding the IT layer. I need
to know exactly where it stopped. Run these and report each result:

    SHOW TABLES IN SCHEMA SNOWCORE_REAL.GOLD;
    SHOW VIEWS IN SCHEMA SNOWCORE_REAL.GOLD;
    SHOW SEMANTIC VIEWS IN SCHEMA SNOWCORE_REAL.GOLD;

Then, for whichever of these exist, report the row count and skip the ones
that do not, without treating a missing object as an error:

    SELECT COUNT(*) FROM GOLD.WORK_ORDER;
    SELECT PLANT_CODE, COUNT(*) FROM GOLD.WORK_ORDER GROUP BY PLANT_CODE;
    SELECT COUNT(*) FROM GOLD.PRODUCTION_LOSS_INCIDENT;
    SELECT COUNT(*) FROM GOLD.IT_ASSUMPTION;
    SELECT COUNT(*) FROM GOLD.CORTEX_BRIEFING;
    SELECT COUNT(*) FROM GOLD.CORTEX_CAUSE_ADVICE;
    SELECT COUNT(*) FROM GOLD.CORTEX_CAUSE_GROUP;

Also report whether `GOLD.WORK_ORDER` still contains the old shape, by
checking for the placeholder cause that the rework was meant to eliminate:

    SELECT COUNT(*) AS PLANT_B_ORDERS,
           SUM(IFF(CAUSE_CODE = 'UNDIAGNOSED', 1, 0)) AS UNDIAGNOSED
    FROM GOLD.WORK_ORDER WHERE PLANT_CODE = 'PLANT_B';

Finish with a plain list: which objects exist and are up to date, which exist
but are stale from the previous build, and which do not exist yet. Do not
create or modify anything.

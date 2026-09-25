# Cortex prompt 027 — deploy final review fixes

Use the personal hackathon connection:

```sql
USE ROLE ACCOUNTADMIN;
USE DATABASE SNOWCORE_REAL;
USE WAREHOUSE COMPUTE_WH;
ALTER SESSION SET TIMEZONE='UTC';
```

Execute the current repository files in order:

1. `sql/18_piade_erp.sql`
2. `sql/17_semantic_cortex.sql`

These changes:

- make inventory assumptions executable rather than decorative;
- replace hashed source-event IDs with readable deterministic IDs;
- expose real timestamps in every presentation view;
- add a PIADE-only cost view;
- compute Pareto cumulative percentages within fault/waiting nature;
- add duplicate-key and cost-contract gates.

If Snowflake rejects syntax, make only a compatibility fix, write it back and
report it. Do not alter business rules or metrics.

Required verification:

```sql
SELECT COUNT(*)-COUNT(DISTINCT SOURCE_EVENT_ID) DUPLICATE_EVENT_IDS
FROM GOLD.EVENT_PRODUCTION_ORDER_LINK;

SELECT COUNT(*) COST_ROWS,COUNT(DISTINCT MACHINE_CODE) COST_LINES,
       SUM(MAINTENANCE_COST) MAINTENANCE_COST,
       SUM(IDLE_FORGONE_MARGIN) IDLE_FORGONE_MARGIN
FROM GOLD.V_PIADE_COST_BY_MACHINE;

SELECT TYPEOF(LAST_SCORED_HOUR) LAST_SCORE_TYPE,
       MIN(LAST_SCORED_HOUR) FIRST_LATEST_SCORE,
       MAX(LAST_SCORED_HOUR) LAST_LATEST_SCORE,
       COUNT(*) FLEET_ROWS
FROM GOLD.V_EXECUTIVE_FLEET
GROUP BY TYPEOF(LAST_SCORED_HOUR);

SELECT LOSS_NATURE,MIN(CUMULATIVE_PCT) MIN_CUMULATIVE,
       MAX(CUMULATIVE_PCT) MAX_CUMULATIVE,COUNT(*) CAUSES
FROM GOLD.V_DOWNTIME_PARETO GROUP BY LOSS_NATURE;

SELECT COUNT(*) STOCK_ROWS,
       COUNT_IF(STOCK_STATE='STOCKOUT') STOCKOUTS,
       COUNT_IF(STOCK_STATE='REORDER') REORDERS,
       COUNT_IF(STOCK_STATE='HEALTHY') HEALTHY
FROM GOLD.INVENTORY_SNAPSHOT;

SELECT COUNT(*) THREAD_ROWS FROM GOLD.V_DIGITAL_THREAD;
SELECT COUNT(*) ACTION_ROWS FROM GOLD.V_EXECUTIVE_ACTION_QUEUE;
SELECT COUNT(*) CONTEXT_ROWS FROM GOLD.V_ANALYST_CONTEXT;
```

Required:

- duplicate event IDs = 0;
- cost rows/lines = 5/5;
- latest score is a timestamp, fleet rows = 5;
- each `LOSS_NATURE` cumulative maximum = 100 within rounding;
- inventory has 28 rows and its three stock-state counts sum to 28;
- digital thread remains 142,233 rows;
- action queue remains 15 rows;
- analyst context remains 6 rows;
- all verification queries at the bottom of `sql/18_piade_erp.sql` pass.

Upload the current app:

```sql
PUT 'file://C:/Users/C306242/Phoenix/sainathch45/snowcore-pdm/streamlit/app.py'
  @SNOWCORE_REAL.APPS.STREAMLIT_STAGE/snowcore_pdm/
  OVERWRITE=TRUE AUTO_COMPRESS=FALSE;
ALTER STAGE SNOWCORE_REAL.APPS.STREAMLIT_STAGE REFRESH;
LIST @SNOWCORE_REAL.APPS.STREAMLIT_STAGE/snowcore_pdm/;
```

Smoke-test:

```sql
SELECT * FROM GOLD.V_PIADE_COST_BY_MACHINE LIMIT 5;
SELECT * FROM GOLD.V_DIGITAL_THREAD
WHERE MACHINE_CODE='s_1' ORDER BY STOP_START DESC LIMIT 500;
SELECT * FROM GOLD.V_PLANT_B_RISK
WHERE MACHINE_CODE='s_1' ORDER BY HOUR_TS DESC LIMIT 72;
```

Report exact gate results, app bytes and any remaining runtime warning.

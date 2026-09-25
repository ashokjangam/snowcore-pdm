# Cortex prompt 024 — deploy the PIADE command center end to end

Work in the currently authenticated personal hackathon Snowflake account only.
This replaces the live Streamlit application's data/model/view contracts with
the PIADE-only command center. Do not touch `SNOWCORE_INDUSTRIES`; that remains
the separate historical synthetic quickstart exhibit.

Use:

```sql
USE ROLE ACCOUNTADMIN;
USE DATABASE SNOWCORE_REAL;
USE WAREHOUSE COMPUTE_WH;
ALTER SESSION SET TIMEZONE='UTC';
ALTER SESSION SET QUERY_TAG='snowcore-real|coco|piade-command-center-deploy';
```

## Execution order

`sql/16_it_synthetic.sql` has already run and supplies Plant B work orders,
technicians, costs, idle incidents and `GOLD.IT_ASSUMPTION`. Do not rerun it.

Execute these repository files in this exact order:

1. `sql/15_plant_b_risk.sql`
2. `sql/18_piade_erp.sql`
3. `sql/17_semantic_cortex.sql`

Do not skip failed statements. If Snowflake rejects syntax, make only the
smallest compatibility fix needed, write that fix back to the repository file,
rerun the whole affected file, and document the exact error and change. Do not
change formulas, labels, split dates, thresholds, assumptions, provenance, or
model hyperparameters to improve a metric.

## Model gates

Run:

```sql
SELECT SCOPE, TEST_ROWS, BASE_RATE, AUC, AVG_PRECISION,
       TOP_DECILE_ROWS, TOP_DECILE_PRECISION, TOP_DECILE_RECALL,
       BASELINE_AUC, BASELINE_AVG_PRECISION,
       BASELINE_TOP_DECILE_PRECISION, BASELINE_TOP_DECILE_RECALL,
       FEATURE_COUNT, BLIND_TEST_START, BLIND_TEST_END, MODEL, MODEL_CONFIG
FROM ML.PLANT_B_MODEL_METRICS
ORDER BY IFF(SCOPE='FLEET',0,1),SCOPE;

SELECT COUNT(*) SCORE_ROWS,
       COUNT_IF(HOUR_TS<'2021-12-01'::TIMESTAMP_NTZ) PRE_BLIND_ROWS,
       COUNT_IF(IS_FLAGGED=1) FLAGGED_ROWS,
       COUNT(DISTINCT MACHINE_CODE) MACHINES
FROM ML.PLANT_B_RISK_SCORE;

SELECT COUNT(*) FEATURE_ROWS,
       COUNT(DISTINCT MACHINE_CODE) MACHINES,
       MIN(HOUR_TS) FIRST_HOUR,MAX(HOUR_TS) LAST_HOUR
FROM ML.PLANT_B_FEATURES;

SELECT COUNT(*) IMPORTANCE_ROWS,ROUND(SUM(IMPORTANCE),6) IMPORTANCE_SUM
FROM ML.PLANT_B_FEATURE_IMPORTANCE;
```

Expected from the offline blind-period run, allowing minor implementation
rounding differences:

- fleet test rows: 1,566;
- feature count: 299;
- AUC approximately 0.6884;
- average precision approximately 0.6414;
- exact top-decile rows: 157;
- top-decile precision approximately 76.43%;
- top-decile recall approximately 17.32%;
- persistence top-decile precision approximately 62.42%;
- no score before 2021-12-01;
- five machines;
- feature importances sum to 1.

Stop and report rather than accepting the result if AUC differs by more than
0.01, top-decile precision differs by more than 2 percentage points, the
feature count is not 299, any score predates the blind period, or more/fewer
than exactly `CEIL(TEST_ROWS*0.10)` rows are flagged.

## ERP and lineage gates

Run every verification query at the bottom of `sql/18_piade_erp.sql`, then:

```sql
SELECT
  (SELECT COUNT(*) FROM GOLD.PRODUCTION_ORDER) PRODUCTION_ORDERS,
  (SELECT COUNT(*) FROM GOLD.DIM_MATERIAL) MATERIALS,
  (SELECT COUNT(*) FROM GOLD.WORK_ORDER_PART) WORK_ORDER_PARTS,
  (SELECT COUNT(*) FROM GOLD.INVENTORY_SNAPSHOT) INVENTORY_ROWS,
  (SELECT COUNT(*) FROM GOLD.EVENT_PRODUCTION_ORDER_LINK) EVENT_LINKS,
  (SELECT COUNT(*) FROM GOLD.V_DIGITAL_THREAD) THREAD_ROWS;

SELECT COUNT(*) FLEET_ROWS,COUNT(DISTINCT MACHINE_CODE) LINES
FROM GOLD.V_EXECUTIVE_FLEET;

SELECT * FROM GOLD.V_EXECUTIVE_KPI;

SELECT OWNER_FUNCTION,COUNT(*) ACTIONS
FROM GOLD.V_EXECUTIVE_ACTION_QUEUE
GROUP BY OWNER_FUNCTION ORDER BY OWNER_FUNCTION;

SELECT COUNT(*) CONTEXT_ROWS FROM GOLD.V_ANALYST_CONTEXT;
```

Required:

- production order count equals the PIADE daily OEE machine/day count;
- work-order-part count equals Plant B work orders with `PARTS_COST > 0`;
- event-link count equals all downtime events having a same-line/same-date
  daily OEE anchor;
- all orphan, wrong-origin, reconciliation and deterministic mismatch counts
  from file 18 equal zero;
- executive fleet has exactly five rows and five lines;
- KPI has one row;
- analyst context has six rows;
- action queue is non-empty for maintenance and planning;
- no new object references CoMoPI or claims real ERP data.

Read a sample of 10 `GOLD.V_DIGITAL_THREAD` rows and confirm it visibly carries
event, production-order, optional work-order, optional material/inventory and
origin fields. A null work order on an idle event is correct, not an orphan.

## Semantic/Cortex gates

Run the verification at the bottom of `sql/17_semantic_cortex.sql`. Confirm:

- semantic-view queries compile;
- direct weighted OEE remains 46.78% within rounding;
- only PIADE appears;
- Cortex briefing has exactly `PIADE_OEE`, `PIADE_RISK`, and
  `PIADE_FINANCIAL`;
- the financial narrative explicitly calls euros/orders synthetic;
- no narrative claims vibration, temperature, RPM, RUL, a named physical
  component, or real ERP integration.

## Upload the app

Upload the repository's revised `streamlit/app.py`:

```sql
PUT 'file://C:/Users/C306242/Phoenix/sainathch45/snowcore-pdm/streamlit/app.py'
  @SNOWCORE_REAL.APPS.STREAMLIT_STAGE/snowcore_pdm/
  OVERWRITE=TRUE AUTO_COMPRESS=FALSE;
ALTER STAGE SNOWCORE_REAL.APPS.STREAMLIT_STAGE REFRESH;
LIST @SNOWCORE_REAL.APPS.STREAMLIT_STAGE/snowcore_pdm/;
SHOW STREAMLITS IN SCHEMA SNOWCORE_REAL.APPS;
```

The existing Streamlit object must remain
`SNOWCORE_REAL.APPS.SNOWCORE_PDM`, with root
`@SNOWCORE_REAL.APPS.STREAMLIT_STAGE/snowcore_pdm` and main file `app.py`.
Do not create a second application.

Smoke-test every query used by the app:

- `GOLD.V_EXECUTIVE_KPI`
- `GOLD.V_EXECUTIVE_FLEET`
- `GOLD.V_EXECUTIVE_ACTION_QUEUE`
- `GOLD.V_DIGITAL_THREAD`
- `GOLD.V_ANALYST_CONTEXT`
- `GOLD.V_OEE_ROLLUP`
- `GOLD.V_OEE_DAILY`
- `GOLD.V_DOWNTIME_PARETO`
- `GOLD.V_COST_BY_MACHINE`
- `GOLD.WORK_ORDER`
- `GOLD.PRODUCTION_ORDER`
- `GOLD.DIM_MATERIAL`
- `GOLD.WORK_ORDER_PART`
- `GOLD.INVENTORY_SNAPSHOT`
- `ML.PLANT_B_MODEL_METRICS`
- `GOLD.V_PLANT_B_RISK`
- `ML.PLANT_B_FEATURE_IMPORTANCE`

Also call `SNOWFLAKE.CORTEX.COMPLETE('llama3.3-70b', ...)` once with a tiny
bounded prompt to confirm the Analyst model is callable.

## Final report

Return:

1. every syntax/runtime fix and whether it was written back;
2. the complete fleet and per-line model metric rows;
3. all ERP object counts and every verification-gate result;
4. executive/action/context counts;
5. weighted OEE;
6. Cortex briefing keys and a short fabrication check;
7. staged app byte count, Streamlit object location and URL;
8. any remaining warning that affects the live demo.

Do not summarize a failed gate as success.

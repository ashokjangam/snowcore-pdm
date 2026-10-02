# Cortex prompt 050 — deploy and verify TRIDENT OPS

Create or replace objects only in the new `TRIDENT_OPS` database and role/warehouse
named `TRIDENT_OPS_ROLE` / `TRIDENT_OPS_WH`. Existing objects in `SNOWCORE_REAL`
and `PNEUMORA` are read-only sources: do not create, alter, drop, insert, update,
delete, grant ownership, or upload anything in those databases.

Do not edit local files. Never create or upload `pyproject.toml`. Stop at the first
failure, report it verbatim, and do not improvise around permissions.

## 1. Execute setup and action SQL

Read and execute, statement by statement, in this order:

1. `C:/Users/C306242/Phoenix/sainathch45/snowcore-pdm/trident_ops/sql/00_setup.sql`
2. `C:/Users/C306242/Phoenix/sainathch45/snowcore-pdm/trident_ops/sql/01_triage_action.sql`

## 2. Upload the warehouse-runtime app

Use role `TRIDENT_OPS_ROLE`, warehouse `TRIDENT_OPS_WH`, database `TRIDENT_OPS`.
Upload these files with `AUTO_COMPRESS=FALSE OVERWRITE=TRUE`:

```sql
PUT 'file://C:/Users/C306242/Phoenix/sainathch45/snowcore-pdm/trident_ops/app.py'
  @TRIDENT_OPS.APP.STREAMLIT_STAGE AUTO_COMPRESS=FALSE OVERWRITE=TRUE;
PUT 'file://C:/Users/C306242/Phoenix/sainathch45/snowcore-pdm/trident_ops/environment.yml'
  @TRIDENT_OPS.APP.STREAMLIT_STAGE AUTO_COMPRESS=FALSE OVERWRITE=TRUE;
PUT 'file://C:/Users/C306242/Phoenix/sainathch45/snowcore-pdm/trident_ops/.streamlit/config.toml'
  @TRIDENT_OPS.APP.STREAMLIT_STAGE/.streamlit/ AUTO_COMPRESS=FALSE OVERWRITE=TRUE;
PUT 'file://C:/Users/C306242/Phoenix/sainathch45/snowcore-pdm/trident_ops/modules/__init__.py'
  @TRIDENT_OPS.APP.STREAMLIT_STAGE/modules/ AUTO_COMPRESS=FALSE OVERWRITE=TRUE;
PUT 'file://C:/Users/C306242/Phoenix/sainathch45/snowcore-pdm/trident_ops/modules/contracts.py'
  @TRIDENT_OPS.APP.STREAMLIT_STAGE/modules/ AUTO_COMPRESS=FALSE OVERWRITE=TRUE;
ALTER STAGE TRIDENT_OPS.APP.STREAMLIT_STAGE REFRESH;
LIST @TRIDENT_OPS.APP.STREAMLIT_STAGE;
```

If the LIST shows `pyproject.toml`, remove it and list again.

Then execute
`C:/Users/C306242/Phoenix/sainathch45/snowcore-pdm/trident_ops/sql/02_deploy_app.sql`
statement by statement.

## 3. Verify source isolation and packages

Run:

```sql
DESCRIBE STREAMLIT TRIDENT_OPS.APP.TRIDENT_OPS;
SHOW STREAMLITS LIKE 'TRIDENT_OPS' IN SCHEMA TRIDENT_OPS.APP;

SELECT COUNT(*) FROM SNOWCORE_REAL.GOLD.V_EXECUTIVE_KPI;
SELECT COUNT(*) FROM SNOWCORE_REAL.GOLD.V_ROOT_CAUSE_ALARM;
SELECT COUNT(*) FROM PNEUMORA.CORE.FAILURES;
SELECT COUNT(*) FROM PNEUMORA.ML.ALERTS;
```

The runtime must be `SYSTEM$WAREHOUSE_RUNTIME`. The user packages must contain
exactly `streamlit==1.52.2`, `plotly==6.5.0`, `pandas==2.3.3`,
`snowflake-snowpark-python`, with no `python` entry.

## 4. Verify idempotent action, then remove the smoke row

Run the same call twice:

```sql
CALL TRIDENT_OPS.OPS.RECORD_TRIAGE_ACTION(
  'PLANT_B','s_2','DEPLOY_SMOKE|s_2','ACKNOWLEDGE',
  'Deployment smoke test',CURRENT_USER()
);
```

Both calls must return the same action id; the second must return
`deduplicated=true`. Confirm exactly one row has `SOURCE_KEY='DEPLOY_SMOKE|s_2'`,
then delete only that smoke row and confirm zero remain.

## Report

Report every error verbatim; stage file names/sizes; whether a pyproject was found;
runtime and user packages; source row counts; both procedure results and before/after
smoke row count; `url_id`; and the complete viewer URL.

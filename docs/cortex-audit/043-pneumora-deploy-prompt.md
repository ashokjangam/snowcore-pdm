# Cortex prompt 043 — deploy PNEUMORA as a standalone Streamlit app

Scope: create and use ONLY the PNEUMORA objects below (role PNEUMORA_ROLE,
warehouse PNEUMORA_WH, database PNEUMORA). Do not read, alter, drop or reference
any SNOWCORE_*, AXISGUARD or other existing database, role or warehouse.
Do not modify any local file. Repository root (use forward slashes in PUT):

    C:/Users/C306242/Phoenix/sainathch45/snowcore-pdm

Run the four scripts in order, statement by statement, replacing `<REPO_ROOT>`
with the repository root above. Read each script from disk exactly as written.

1. `pneumora/sql/00_setup.sql`
2. `pneumora/sql/01_tables.sql`
3. `pneumora/sql/02_load.sql`
4. `pneumora/sql/03_deploy_app.sql`

If a statement fails, print the exact error, stop, and report. Do not invent
workarounds that touch other objects.

## Verify

    USE ROLE PNEUMORA_ROLE;
    SELECT 'TELEMETRY_5M' T, COUNT(*) N FROM PNEUMORA.CORE.TELEMETRY_5M
    UNION ALL SELECT 'FAILURES', COUNT(*) FROM PNEUMORA.CORE.FAILURES
    UNION ALL SELECT 'FAILURE_ZOOM', COUNT(*) FROM PNEUMORA.ML.FAILURE_ZOOM
    UNION ALL SELECT 'ALERTS', COUNT(*) FROM PNEUMORA.ML.ALERTS
    UNION ALL SELECT 'EVIDENCE', COUNT(*) FROM PNEUMORA.ML.EVIDENCE
    UNION ALL SELECT 'WORK_ORDERS', COUNT(*) FROM PNEUMORA.OPS.WORK_ORDERS
    UNION ALL SELECT 'PARTS', COUNT(*) FROM PNEUMORA.OPS.PARTS
    UNION ALL SELECT 'TECHNICIANS', COUNT(*) FROM PNEUMORA.OPS.TECHNICIANS
    UNION ALL SELECT 'DAILY_KPIS', COUNT(*) FROM PNEUMORA.CORE.DAILY_KPIS
    UNION ALL SELECT 'FACTORY_SCENARIO', COUNT(*) FROM PNEUMORA.OPS.FACTORY_SCENARIO;

Expected: TELEMETRY_5M 50782, FAILURES 4, FAILURE_ZOOM 1095, ALERTS 132,
EVIDENCE 4, WORK_ORDERS 41, PARTS 6, TECHNICIANS 6, DAILY_KPIS 214,
FACTORY_SCENARIO 214. Report any mismatch.

    SELECT COUNT_IF(COPILOT_FLAG) FLAGGED, MIN(TS), MAX(TS) FROM PNEUMORA.CORE.TELEMETRY_5M;
    -- expected FLAGGED = 2639

    SELECT SOURCE, OUTCOME, COUNT(*) FROM PNEUMORA.ML.ALERTS GROUP BY 1, 2 ORDER BY 1, 2;
    -- expected copilot: caught_in_time 6, no_reported_failure 12;
    -- low_pressure_alarm: no_reported_failure 111, plus 3 on failures

    LIST @PNEUMORA.APP.STREAMLIT_STAGE;
    -- local sizes: app.py 29827, status_rules.py 6303, environment.yml 134,
    -- .streamlit/config.toml 135, assets/pneumora-logo-reversed.svg 1461

    SHOW STREAMLITS IN SCHEMA PNEUMORA.APP;
    DESCRIBE STREAMLIT PNEUMORA.APP.PNEUMORA_COPILOT;
    SELECT CURRENT_ORGANIZATION_NAME() ORG, CURRENT_ACCOUNT_NAME() ACCOUNT;

## Report

1. Every statement that failed, with the exact error (or "none").
2. The row-count table against the expected numbers.
3. Staged file sizes against the local sizes.
4. The Streamlit object owner, warehouse and `url_id`, and the viewer URL in the form
   `https://app.snowflake.com/streamlit/<ORG>/<ACCOUNT>/#/apps/<url_id>`.

Be blunt about anything that looks wrong.

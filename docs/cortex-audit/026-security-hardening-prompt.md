# Cortex prompt 026 — security hardening deployment

Use the personal hackathon connection:

```sql
USE ROLE ACCOUNTADMIN;
USE DATABASE SNOWCORE_REAL;
USE WAREHOUSE COMPUTE_WH;
ALTER SESSION SET TIMEZONE='UTC';
```

The security review removed process-global Snowpark-session caching, literalised
Cortex output, hid Snowflake exceptions from clients, bounded session scenarios
and filtered work orders to PIADE in SQL. Upload the revised app:

```sql
PUT 'file://C:/Users/C306242/Phoenix/sainathch45/snowcore-pdm/streamlit/app.py'
  @SNOWCORE_REAL.APPS.STREAMLIT_STAGE/snowcore_pdm/
  OVERWRITE=TRUE AUTO_COMPRESS=FALSE;
ALTER STAGE SNOWCORE_REAL.APPS.STREAMLIT_STAGE REFRESH;
LIST @SNOWCORE_REAL.APPS.STREAMLIT_STAGE/snowcore_pdm/;
```

The training procedure must not execute with `ACCOUNTADMIN` owner rights when
called by another role. Apply and verify:

```sql
ALTER PROCEDURE ML.TRAIN_PLANT_B_RISK() EXECUTE AS CALLER;
SHOW PROCEDURES LIKE 'TRAIN_PLANT_B_RISK' IN SCHEMA ML;
SHOW GRANTS ON PROCEDURE ML.TRAIN_PLANT_B_RISK();
```

Do not call the procedure and do not retrain. Report:

1. staged app bytes;
2. procedure `execute as` mode;
3. all roles with USAGE on the procedure;
4. whether PUBLIC or any application-facing role can call it.

If `ALTER ... EXECUTE AS CALLER` is unsupported, recreate the procedure from
the exact DDL in `sql/15_plant_b_risk.sql` but do not execute its trailing
`CALL`. Do not change the procedure body.

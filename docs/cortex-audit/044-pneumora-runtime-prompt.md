# Cortex prompt 044 — put PNEUMORA back on the warehouse runtime

Scope: only `PNEUMORA_ROLE`, `PNEUMORA_WH`, and database `PNEUMORA`. Do not touch
any other database, role, warehouse, or Streamlit app. Do not edit local files.

The app was created without `RUNTIME_NAME`, so the 2026_06 behavior change put
it on the container runtime. That runtime ignores `environment.yml` and fails
with "pyproject.toml file does not exist". Recreate it on the warehouse runtime.

Repository root, forward slashes:

    C:/Users/C306242/Phoenix/sainathch45/snowcore-pdm

Run, in order:

    USE ROLE PNEUMORA_ROLE;
    USE WAREHOUSE PNEUMORA_WH;

    PUT 'file://C:/Users/C306242/Phoenix/sainathch45/snowcore-pdm/pneumora/sis/environment.yml'
      @PNEUMORA.APP.STREAMLIT_STAGE
      AUTO_COMPRESS = FALSE OVERWRITE = TRUE;

    ALTER STAGE PNEUMORA.APP.STREAMLIT_STAGE REFRESH;

    CREATE OR REPLACE STREAMLIT PNEUMORA.APP.PNEUMORA_COPILOT
      FROM '@PNEUMORA.APP.STREAMLIT_STAGE'
      MAIN_FILE = 'app.py'
      QUERY_WAREHOUSE = 'PNEUMORA_WH'
      RUNTIME_NAME = 'SYSTEM$WAREHOUSE_RUNTIME'
      TITLE = 'PNEUMORA early air-leak co-pilot'
      COMMENT = 'Read-only PNEUMORA co-pilot track record, status replay and evidence';

Then verify and print the raw output:

    DESCRIBE STREAMLIT PNEUMORA.APP.PNEUMORA_COPILOT;
    SHOW STREAMLITS IN SCHEMA PNEUMORA.APP;
    LIST @PNEUMORA.APP.STREAMLIT_STAGE;

## Report

1. Any statement that failed, with the exact error.
2. The runtime shown for `PNEUMORA_COPILOT`. It must be the warehouse runtime
   (`SYSTEM$WAREHOUSE_RUNTIME`), not `SYSTEM$ST_CONTAINER_RUNTIME_PY3_11`.
3. Whether `environment.yml` is at the stage root, next to `app.py`.
4. The viewer URL:
   `https://app.snowflake.com/streamlit/FMXJOWH/BRC04642/#/apps/<url_id>`

If `RUNTIME_NAME` is rejected, stop and print the exact error. Do not create a
compute pool, an external access integration, or a `pyproject.toml`.

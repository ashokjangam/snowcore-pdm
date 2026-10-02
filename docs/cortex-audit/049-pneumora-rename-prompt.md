# Cortex prompt 049 — upload renamed leak page and rebuild the app

Scope: only PNEUMORA_ROLE, PNEUMORA_WH and database PNEUMORA. Do not edit local
files. Do not touch any other object. Never create a pyproject.toml. Stop at the
first failure and report it verbatim.

    USE ROLE PNEUMORA_ROLE;
    USE WAREHOUSE PNEUMORA_WH;
    USE DATABASE PNEUMORA;
    PUT 'file://C:/Users/C306242/Phoenix/sainathch45/snowcore-pdm/pneumora/sis/app.py'
      @PNEUMORA.APP.STREAMLIT_STAGE AUTO_COMPRESS = FALSE OVERWRITE = TRUE;
    ALTER STAGE PNEUMORA.APP.STREAMLIT_STAGE REFRESH;
    LIST @PNEUMORA.APP.STREAMLIT_STAGE;

If LIST shows a pyproject.toml anywhere, REMOVE it and LIST again.

    CREATE OR REPLACE STREAMLIT PNEUMORA.APP.PNEUMORA_COPILOT
      FROM '@PNEUMORA.APP.STREAMLIT_STAGE'
      MAIN_FILE = 'app.py'
      QUERY_WAREHOUSE = 'PNEUMORA_WH'
      RUNTIME_NAME = 'SYSTEM$WAREHOUSE_RUNTIME'
      TITLE = 'PNEUMORA early air-leak co-pilot'
      COMMENT = 'Read-only PNEUMORA leak alerts vs real failures, status replay and evidence';

    DESCRIBE STREAMLIT PNEUMORA.APP.PNEUMORA_COPILOT;
    SHOW STREAMLITS LIKE 'PNEUMORA_COPILOT' IN SCHEMA PNEUMORA.APP;

Report: errors verbatim; LIST output (names, sizes; app.py should be about 32 KB);
whether a pyproject.toml was found; from DESCRIBE the runtime_name and
user_packages (must be exactly streamlit==1.52.2,plotly==6.5.0,pandas==2.3.3,snowflake-snowpark-python
with no python entry); url_id from SHOW STREAMLITS.

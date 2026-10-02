# Cortex prompt 048 — diagnose live version, probe packages, then sync

Scope: only PNEUMORA_ROLE, PNEUMORA_WH and database PNEUMORA. Do not edit local
files. Do not touch any other object. Never create a pyproject.toml. Run the
steps in order and STOP at the first step that fails, reporting the error
verbatim.

## Step 1 — what the app is actually running (read-only)

    USE ROLE PNEUMORA_ROLE;
    USE WAREHOUSE PNEUMORA_WH;
    USE DATABASE PNEUMORA;
    DESCRIBE STREAMLIT PNEUMORA.APP.PNEUMORA_COPILOT;
    LIST 'snow://streamlit/PNEUMORA.APP.PNEUMORA_COPILOT/versions/live/';

Then show the content of the live environment.yml:

    SELECT $1 FROM 'snow://streamlit/PNEUMORA.APP.PNEUMORA_COPILOT/versions/live/environment.yml'
      (FILE_FORMAT => (TYPE = 'CSV', FIELD_DELIMITER = NONE));

If reading the snow:// path fails, report the error and continue.

## Step 2 — prove the package set resolves and imports (creates no object)

    WITH probe AS PROCEDURE()
      RETURNS STRING
      LANGUAGE PYTHON
      RUNTIME_VERSION = '3.11'
      PACKAGES = ('streamlit==1.52.2', 'plotly==6.5.0', 'pandas==2.3.3', 'snowflake-snowpark-python')
      HANDLER = 'run'
    AS $$
    def run(session):
        import sys
        import pandas, plotly, streamlit
        import plotly.graph_objects, plotly.subplots
        from snowflake.snowpark.context import get_active_session
        return f"python {sys.version.split()[0]} streamlit {streamlit.__version__} plotly {plotly.__version__} pandas {pandas.__version__}"
    $$
    CALL probe();

If this fails, STOP and report the error verbatim. Do not do Step 3.

## Step 3 — push the source stage into the app's live version

    COPY FILES INTO 'snow://streamlit/PNEUMORA.APP.PNEUMORA_COPILOT/versions/live/'
      FROM @PNEUMORA.APP.STREAMLIT_STAGE;

If COPY FILES fails, report the error and instead run:

    CREATE OR REPLACE STREAMLIT PNEUMORA.APP.PNEUMORA_COPILOT
      FROM '@PNEUMORA.APP.STREAMLIT_STAGE'
      MAIN_FILE = 'app.py'
      QUERY_WAREHOUSE = 'PNEUMORA_WH'
      RUNTIME_NAME = 'SYSTEM$WAREHOUSE_RUNTIME'
      TITLE = 'PNEUMORA early air-leak co-pilot'
      COMMENT = 'Read-only PNEUMORA co-pilot track record, status replay and evidence';

Then verify:

    LIST 'snow://streamlit/PNEUMORA.APP.PNEUMORA_COPILOT/versions/live/';
    SELECT $1 FROM 'snow://streamlit/PNEUMORA.APP.PNEUMORA_COPILOT/versions/live/environment.yml'
      (FILE_FORMAT => (TYPE = 'CSV', FIELD_DELIMITER = NONE));

If the live LIST shows a pyproject.toml, remove it with
`REMOVE 'snow://streamlit/PNEUMORA.APP.PNEUMORA_COPILOT/versions/live/pyproject.toml';`
and LIST again.

    DESCRIBE STREAMLIT PNEUMORA.APP.PNEUMORA_COPILOT;
    SHOW STREAMLITS LIKE 'PNEUMORA_COPILOT' IN SCHEMA PNEUMORA.APP;

## Report

1. Step 1: live file list (names, sizes) and live environment.yml content BEFORE the sync.
2. Step 2: the probe's returned string, or the error verbatim.
3. Step 3: which method was used (COPY FILES or CREATE OR REPLACE), errors verbatim.
4. Live file list and live environment.yml content AFTER the sync; whether a pyproject.toml was found.
5. runtime_name from DESCRIBE, and url_id from SHOW STREAMLITS.

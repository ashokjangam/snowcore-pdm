# Cortex prompt 047 — upload pinned environment.yml and hardened app.py

Scope: only PNEUMORA_ROLE, PNEUMORA_WH and database PNEUMORA. Do not edit local
files. Do not touch any other object. Do not create any pyproject.toml.

    USE ROLE PNEUMORA_ROLE;
    USE WAREHOUSE PNEUMORA_WH;
    USE DATABASE PNEUMORA;
    PUT 'file://C:/Users/C306242/Phoenix/sainathch45/snowcore-pdm/pneumora/sis/environment.yml'
      @PNEUMORA.APP.STREAMLIT_STAGE AUTO_COMPRESS = FALSE OVERWRITE = TRUE;
    PUT 'file://C:/Users/C306242/Phoenix/sainathch45/snowcore-pdm/pneumora/sis/app.py'
      @PNEUMORA.APP.STREAMLIT_STAGE AUTO_COMPRESS = FALSE OVERWRITE = TRUE;
    PUT 'file://C:/Users/C306242/Phoenix/sainathch45/snowcore-pdm/pneumora/sis/status_rules.py'
      @PNEUMORA.APP.STREAMLIT_STAGE AUTO_COMPRESS = FALSE OVERWRITE = TRUE;
    ALTER STAGE PNEUMORA.APP.STREAMLIT_STAGE REFRESH;
    LIST @PNEUMORA.APP.STREAMLIT_STAGE;
    SELECT $1 FROM @PNEUMORA.APP.STREAMLIT_STAGE/environment.yml
      (FILE_FORMAT => (TYPE = CSV, FIELD_DELIMITER = NONE));

If LIST shows a file named pyproject.toml (at any path) in the stage, remove it
with REMOVE @PNEUMORA.APP.STREAMLIT_STAGE/<path>; and LIST again.

The staged environment.yml must list exactly: streamlit=1.52.2, plotly=6.5.0,
pandas=2.3.3, snowflake-snowpark-python, and no python line.

Confirm the pinned versions exist for Python 3.11:

    SELECT PACKAGE_NAME, VERSION, LISTAGG(DISTINCT RUNTIME_VERSION, ',') RUNTIMES
    FROM INFORMATION_SCHEMA.PACKAGES
    WHERE LANGUAGE = 'python'
      AND ((PACKAGE_NAME = 'streamlit' AND VERSION = '1.52.2')
        OR (PACKAGE_NAME = 'plotly' AND VERSION = '6.5.0')
        OR (PACKAGE_NAME = 'pandas' AND VERSION = '2.3.3'))
    GROUP BY 1, 2 ORDER BY 1;

    DESCRIBE STREAMLIT PNEUMORA.APP.PNEUMORA_COPILOT;

Report: any error verbatim; the LIST output (file names and sizes); whether a
pyproject.toml was found/removed; the staged environment.yml content; the
package table; and the runtime from DESCRIBE (must be SYSTEM$WAREHOUSE_RUNTIME).

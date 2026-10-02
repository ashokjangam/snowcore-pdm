# Cortex prompt 045 — replace PNEUMORA environment.yml

Scope: only PNEUMORA_ROLE, PNEUMORA_WH and database PNEUMORA. Do not edit local
files. Do not touch any other object.

    USE ROLE PNEUMORA_ROLE;
    USE WAREHOUSE PNEUMORA_WH;
    PUT 'file://C:/Users/C306242/Phoenix/sainathch45/snowcore-pdm/pneumora/sis/environment.yml'
      @PNEUMORA.APP.STREAMLIT_STAGE AUTO_COMPRESS = FALSE OVERWRITE = TRUE;
    ALTER STAGE PNEUMORA.APP.STREAMLIT_STAGE REFRESH;
    SELECT $1 FROM @PNEUMORA.APP.STREAMLIT_STAGE/environment.yml
      (FILE_FORMAT => (TYPE = CSV, FIELD_DELIMITER = NONE));

The staged file must contain exactly these dependency lines and NO python line:
streamlit=1.52.2, plotly, pandas, snowflake-snowpark-python.

Then check every package resolves in the Snowflake Anaconda channel:

    SELECT PACKAGE_NAME, MAX(VERSION) LATEST, COUNT_IF(VERSION = '1.52.2') HAS_1_52_2
    FROM INFORMATION_SCHEMA.PACKAGES
    WHERE LANGUAGE = 'python'
      AND PACKAGE_NAME IN ('streamlit','plotly','pandas','snowflake-snowpark-python')
    GROUP BY 1 ORDER BY 1;

Run that query in database PNEUMORA (`USE DATABASE PNEUMORA;` first).

    DESCRIBE STREAMLIT PNEUMORA.APP.PNEUMORA_COPILOT;

Report: any error verbatim; the staged environment.yml content; the package
table (all four must be present and streamlit must have HAS_1_52_2 = 1); and the
runtime from DESCRIBE (must be SYSTEM$WAREHOUSE_RUNTIME).

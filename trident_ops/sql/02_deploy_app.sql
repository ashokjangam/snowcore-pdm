-- Run after uploading app.py, environment.yml, .streamlit/config.toml and modules/
-- to @TRIDENT_OPS.APP.STREAMLIT_STAGE with AUTO_COMPRESS=FALSE.

USE ROLE TRIDENT_OPS_ROLE;
USE WAREHOUSE TRIDENT_OPS_WH;
USE DATABASE TRIDENT_OPS;

ALTER STAGE APP.STREAMLIT_STAGE REFRESH;

CREATE OR REPLACE STREAMLIT APP.TRIDENT_OPS
  FROM '@TRIDENT_OPS.APP.STREAMLIT_STAGE'
  MAIN_FILE = 'app.py'
  QUERY_WAREHOUSE = 'TRIDENT_OPS_WH'
  RUNTIME_NAME = 'SYSTEM$WAREHOUSE_RUNTIME'
  TITLE = 'TRIDENT OPS · Evidence-first OEE and maintenance'
  COMMENT = 'PIADE operations and MetroPT sensor evidence remain isolated; operator triage is persisted';

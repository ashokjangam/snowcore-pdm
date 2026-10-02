-- Upload the Streamlit app and create the app object (warehouse runtime).
-- Its writes are PNEUMORA.OPS.RECORD_ACTION, CREATE_WORK_ORDER and SET_WORK_ORDER_STATUS (06_work_orders.sql).
-- The object name is kept so the app URL does not change.
-- Replace <REPO_ROOT> with the absolute repository path using forward slashes.

USE ROLE PNEUMORA_ROLE;
USE WAREHOUSE PNEUMORA_WH;

PUT 'file://<REPO_ROOT>/pneumora/sis/app.py'          @PNEUMORA.APP.STREAMLIT_STAGE AUTO_COMPRESS = FALSE OVERWRITE = TRUE;
PUT 'file://<REPO_ROOT>/pneumora/sis/status_rules.py' @PNEUMORA.APP.STREAMLIT_STAGE AUTO_COMPRESS = FALSE OVERWRITE = TRUE;
PUT 'file://<REPO_ROOT>/pneumora/sis/environment.yml' @PNEUMORA.APP.STREAMLIT_STAGE AUTO_COMPRESS = FALSE OVERWRITE = TRUE;
PUT 'file://<REPO_ROOT>/pneumora/sis/.streamlit/config.toml' @PNEUMORA.APP.STREAMLIT_STAGE/.streamlit/ AUTO_COMPRESS = FALSE OVERWRITE = TRUE;
PUT 'file://<REPO_ROOT>/pneumora/assets/pneumora-logo-reversed.svg' @PNEUMORA.APP.STREAMLIT_STAGE/assets/ AUTO_COMPRESS = FALSE OVERWRITE = TRUE;
ALTER STAGE PNEUMORA.APP.STREAMLIT_STAGE REFRESH;

-- RUNTIME_NAME is required. Since the 2026_06 behavior change, omitting it
-- creates a container-runtime app, which ignores environment.yml and fails
-- unless a pyproject.toml is present. This app uses the warehouse runtime.
CREATE OR REPLACE STREAMLIT PNEUMORA.APP.PNEUMORA_COPILOT
  FROM '@PNEUMORA.APP.STREAMLIT_STAGE'
  MAIN_FILE = 'app.py'
  QUERY_WAREHOUSE = 'PNEUMORA_WH'
  RUNTIME_NAME = 'SYSTEM$WAREHOUSE_RUNTIME'
  TITLE = 'PNEUMORA early air-leak predictor'
  COMMENT = 'PNEUMORA leak predictor: track record, prediction studies, cited RCA and action log';

-- =============================================================================
-- 04_deploy_app.sql  –  Deploy the Streamlit Dashboard
-- =============================================================================
-- This script uploads the Streamlit application files to an internal stage and
-- creates the STREAMLIT object that Snowsight can serve.
--
-- IMPORTANT — Trial / Standard accounts:
--   Trial accounts do NOT have access to Snowpark Container Services (SPCS),
--   so this deployment uses the warehouse-based Streamlit runtime.  The
--   RUNTIME_NAME and COMPUTE_POOL parameters are deliberately omitted.
--   All Python dependencies are declared in environment.yml (Anaconda channel)
--   and requirements.txt, which Snowflake resolves at deploy time.
--
-- Prerequisites:
--   • 01_setup_snowcore.sql has been run (database, schemas, warehouse exist).
--   • The Streamlit source code lives on the local machine at:
--       C:/MyWork/snowflake-hackathon/sfguide-getting-started-with-predictive-maintenance/streamlit/
--   • A SnowSQL or Snowflake CLI session is required for the PUT commands
--     (PUT does not run inside Snowsight worksheets).
-- =============================================================================

USE ROLE ACCOUNTADMIN;
USE DATABASE SNOWCORE_INDUSTRIES;
USE WAREHOUSE SNOWCORE_INDUSTRIES_WH;

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. Create the internal stage for Streamlit files
-- ─────────────────────────────────────────────────────────────────────────────
-- DIRECTORY = (ENABLE = TRUE) makes the stage browsable from Snowsight so you
-- can verify uploaded files.  No external storage or encryption keys are
-- needed — this is a fully managed internal stage.

CREATE STAGE IF NOT EXISTS SNOWCORE_INDUSTRIES.GOLD.STREAMLIT_STAGE
    DIRECTORY = (ENABLE = TRUE);

-- ─────────────────────────────────────────────────────────────────────────────
-- 2. Upload application files to the stage
-- ─────────────────────────────────────────────────────────────────────────────
-- AUTO_COMPRESS = FALSE keeps .py, .yml, .css, and .html files as-is so the
-- Streamlit runtime can read them.  OVERWRITE = TRUE allows re-deployment
-- without manually removing old files.
--
-- NOTE: PUT must be executed from SnowSQL or the Snowflake Python connector,
-- not from a Snowsight worksheet.

-- Root-level files (app entry point, config, styling)
PUT 'file://C:/MyWork/snowflake-hackathon/sfguide-getting-started-with-predictive-maintenance/streamlit/app.py'                  @SNOWCORE_INDUSTRIES.GOLD.STREAMLIT_STAGE AUTO_COMPRESS=FALSE OVERWRITE=TRUE;
PUT 'file://C:/MyWork/snowflake-hackathon/sfguide-getting-started-with-predictive-maintenance/streamlit/environment.yml'          @SNOWCORE_INDUSTRIES.GOLD.STREAMLIT_STAGE AUTO_COMPRESS=FALSE OVERWRITE=TRUE;
PUT 'file://C:/MyWork/snowflake-hackathon/sfguide-getting-started-with-predictive-maintenance/streamlit/requirements.txt'         @SNOWCORE_INDUSTRIES.GOLD.STREAMLIT_STAGE AUTO_COMPRESS=FALSE OVERWRITE=TRUE;
PUT 'file://C:/MyWork/snowflake-hackathon/sfguide-getting-started-with-predictive-maintenance/streamlit/style.css'                @SNOWCORE_INDUSTRIES.GOLD.STREAMLIT_STAGE AUTO_COMPRESS=FALSE OVERWRITE=TRUE;
PUT 'file://C:/MyWork/snowflake-hackathon/sfguide-getting-started-with-predictive-maintenance/streamlit/line_visualization.html'  @SNOWCORE_INDUSTRIES.GOLD.STREAMLIT_STAGE AUTO_COMPRESS=FALSE OVERWRITE=TRUE;

-- Utility modules (data loading, Cortex Analyst integration, AI assistant)
PUT 'file://C:/MyWork/snowflake-hackathon/sfguide-getting-started-with-predictive-maintenance/streamlit/utils/*.py'               @SNOWCORE_INDUSTRIES.GOLD.STREAMLIT_STAGE/utils AUTO_COMPRESS=FALSE OVERWRITE=TRUE;

-- View modules (each page of the dashboard)
PUT 'file://C:/MyWork/snowflake-hackathon/sfguide-getting-started-with-predictive-maintenance/streamlit/views/*.py'               @SNOWCORE_INDUSTRIES.GOLD.STREAMLIT_STAGE/views AUTO_COMPRESS=FALSE OVERWRITE=TRUE;

-- ─────────────────────────────────────────────────────────────────────────────
-- 3. Create the Streamlit application object
-- ─────────────────────────────────────────────────────────────────────────────
-- The STREAMLIT object tells Snowflake where the code lives (FROM stage),
-- which file to execute first (MAIN_FILE), and which warehouse handles the
-- Python compute (QUERY_WAREHOUSE).
--
-- Because this is a trial account WITHOUT SPCS access:
--   • No RUNTIME_NAME parameter  (would require SPCS)
--   • No COMPUTE_POOL parameter  (would require SPCS)
--   • Dependencies come from environment.yml (Anaconda) — not a custom image

CREATE OR REPLACE STREAMLIT SNOWCORE_INDUSTRIES.GOLD.PREDICTIVE_MAINTENANCE_APP
    FROM '@SNOWCORE_INDUSTRIES.GOLD.STREAMLIT_STAGE'
    MAIN_FILE = 'app.py'
    QUERY_WAREHOUSE = 'SNOWCORE_INDUSTRIES_STREAMLIT_WH';

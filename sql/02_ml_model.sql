-- =============================================================================
-- 02_ml_model.sql  –  ML Layer for Predictive Maintenance
-- =============================================================================
-- This script builds the machine-learning pipeline that predicts whether an
-- industrial asset will fail within the next 7 days.
--
-- Prerequisites: run 01_setup_snowcore.sql first so that the GOLD.ML_FEATURE_STORE
-- table exists with sensor-derived features and the binary label
-- FAILED_IN_NEXT_7_DAYS.
--
-- Workflow:
--   1. Create the ML schema.
--   2. Create a TRAINING view (observations on or before 2025-09-30 — ~80 %).
--   3. Create a HOLDOUT  view (observations after  2025-09-30 — ~20 %).
--      Both views coalesce NULL pressure readings to 0 and expose a flag
--      HAS_PRESSURE_SENSOR so the model can distinguish "zero pressure" from
--      "no sensor installed."
--   4. Train a Snowflake-native classification model on the training view.
--   5. Inspect evaluation metrics and feature importance.
--   6. Score the holdout set and persist the results.
--   7. Query the scored table to extract the TRUE-class probability.
-- =============================================================================

USE ROLE ACCOUNTADMIN;
USE DATABASE SNOWCORE_INDUSTRIES;
USE WAREHOUSE SNOWCORE_INDUSTRIES_WH;

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. Create the ML schema
-- ─────────────────────────────────────────────────────────────────────────────
CREATE SCHEMA IF NOT EXISTS SNOWCORE_INDUSTRIES.ML;
USE SCHEMA SNOWCORE_INDUSTRIES.ML;

-- ─────────────────────────────────────────────────────────────────────────────
-- 2. Training view — observations up to the cutoff date (80 % chronological split)
-- ─────────────────────────────────────────────────────────────────────────────
-- OBSERVATION_DATE_SK is an integer date key in YYYYMMDD format.
-- COALESCE(PRESSURE_TREND_7D, 0) replaces NULLs from assets that lack a
-- pressure sensor; HAS_PRESSURE_SENSOR lets the model learn that distinction.

CREATE OR REPLACE VIEW SNOWCORE_INDUSTRIES.ML.TRAINING_VIEW(
    ASSET_ID,
    AVG_TEMP_LAST_24H,
    VIBRATION_STDDEV_7D,
    PRESSURE_TREND_7D,
    HAS_PRESSURE_SENSOR,
    CYCLES_SINCE_LAST_PM,
    DAYS_SINCE_LAST_FAILURE,
    OEM_FAILURE_RATE_EST,
    DOWNTIME_IMPACT_RISK,
    FAILED_IN_NEXT_7_DAYS
) AS
SELECT
    ASSET_ID,
    AVG_TEMP_LAST_24H,
    VIBRATION_STDDEV_7D,
    COALESCE(PRESSURE_TREND_7D, 0) AS PRESSURE_TREND_7D,
    IFF(PRESSURE_TREND_7D IS NOT NULL, 1, 0) AS HAS_PRESSURE_SENSOR,
    CYCLES_SINCE_LAST_PM,
    DAYS_SINCE_LAST_FAILURE,
    OEM_FAILURE_RATE_EST,
    DOWNTIME_IMPACT_RISK,
    FAILED_IN_NEXT_7_DAYS
FROM SNOWCORE_INDUSTRIES.GOLD.ML_FEATURE_STORE
WHERE OBSERVATION_DATE_SK <= 20250930;

-- ─────────────────────────────────────────────────────────────────────────────
-- 3. Holdout view — observations after the cutoff (20 % chronological split)
-- ─────────────────────────────────────────────────────────────────────────────
-- This data was never seen during training, so it gives an unbiased estimate
-- of real-world model performance.

CREATE OR REPLACE VIEW SNOWCORE_INDUSTRIES.ML.HOLDOUT_VIEW(
    ASSET_ID,
    AVG_TEMP_LAST_24H,
    VIBRATION_STDDEV_7D,
    PRESSURE_TREND_7D,
    HAS_PRESSURE_SENSOR,
    CYCLES_SINCE_LAST_PM,
    DAYS_SINCE_LAST_FAILURE,
    OEM_FAILURE_RATE_EST,
    DOWNTIME_IMPACT_RISK,
    FAILED_IN_NEXT_7_DAYS
) AS
SELECT
    ASSET_ID,
    AVG_TEMP_LAST_24H,
    VIBRATION_STDDEV_7D,
    COALESCE(PRESSURE_TREND_7D, 0) AS PRESSURE_TREND_7D,
    IFF(PRESSURE_TREND_7D IS NOT NULL, 1, 0) AS HAS_PRESSURE_SENSOR,
    CYCLES_SINCE_LAST_PM,
    DAYS_SINCE_LAST_FAILURE,
    OEM_FAILURE_RATE_EST,
    DOWNTIME_IMPACT_RISK,
    FAILED_IN_NEXT_7_DAYS
FROM SNOWCORE_INDUSTRIES.GOLD.ML_FEATURE_STORE
WHERE OBSERVATION_DATE_SK > 20250930;

-- ─────────────────────────────────────────────────────────────────────────────
-- 4. Train the classification model
-- ─────────────────────────────────────────────────────────────────────────────
-- SNOWFLAKE.ML.CLASSIFICATION is a built-in AutoML classifier.  It picks the
-- best algorithm, tunes hyper-parameters, and registers the model as a
-- first-class Snowflake object you can call with !PREDICT().

CREATE OR REPLACE SNOWFLAKE.ML.CLASSIFICATION SNOWCORE_INDUSTRIES.ML.FAILURE_RISK_MODEL(
    INPUT_DATA => SYSTEM$REFERENCE('VIEW', 'SNOWCORE_INDUSTRIES.ML.TRAINING_VIEW'),
    TARGET_COLNAME => 'FAILED_IN_NEXT_7_DAYS'
);

-- ─────────────────────────────────────────────────────────────────────────────
-- 5a. Evaluation metrics — accuracy, precision, recall, F1, AUC, etc.
-- ─────────────────────────────────────────────────────────────────────────────

CALL SNOWCORE_INDUSTRIES.ML.FAILURE_RISK_MODEL!SHOW_GLOBAL_EVALUATION_METRICS();

-- ─────────────────────────────────────────────────────────────────────────────
-- 5b. Feature importance — which sensor signals matter most
-- ─────────────────────────────────────────────────────────────────────────────

CALL SNOWCORE_INDUSTRIES.ML.FAILURE_RISK_MODEL!SHOW_FEATURE_IMPORTANCE();

-- ─────────────────────────────────────────────────────────────────────────────
-- 6. Score the holdout set and persist predictions
-- ─────────────────────────────────────────────────────────────────────────────
-- Each row gets a PREDICTION variant containing:
--   { "class": "True"|"False",
--     "probability": { "True": 0.xx, "False": 0.yy } }
-- We pass every feature column via OBJECT_CONSTRUCT so the model receives the
-- same schema it was trained on.

CREATE OR REPLACE TABLE SNOWCORE_INDUSTRIES.ML.HOLDOUT_PREDICTIONS AS
SELECT *,
    SNOWCORE_INDUSTRIES.ML.FAILURE_RISK_MODEL!PREDICT(
        INPUT_DATA => OBJECT_CONSTRUCT(
            'ASSET_ID', ASSET_ID,
            'AVG_TEMP_LAST_24H', AVG_TEMP_LAST_24H,
            'VIBRATION_STDDEV_7D', VIBRATION_STDDEV_7D,
            'PRESSURE_TREND_7D', PRESSURE_TREND_7D,
            'HAS_PRESSURE_SENSOR', HAS_PRESSURE_SENSOR,
            'CYCLES_SINCE_LAST_PM', CYCLES_SINCE_LAST_PM,
            'DAYS_SINCE_LAST_FAILURE', DAYS_SINCE_LAST_FAILURE,
            'OEM_FAILURE_RATE_EST', OEM_FAILURE_RATE_EST,
            'DOWNTIME_IMPACT_RISK', DOWNTIME_IMPACT_RISK
        )
    ) AS PREDICTION
FROM SNOWCORE_INDUSTRIES.ML.HOLDOUT_VIEW;

-- ─────────────────────────────────────────────────────────────────────────────
-- 7. Extract the TRUE-class probability from the scored holdout
-- ─────────────────────────────────────────────────────────────────────────────
-- PARSE_JSON unpacks the VARIANT; we pull the "True" probability so downstream
-- cost analysis can sweep decision thresholds.

SELECT
    ASSET_ID,
    FAILED_IN_NEXT_7_DAYS,
    PARSE_JSON(PREDICTION):class::STRING            AS predicted_class,
    PARSE_JSON(PREDICTION):probability:"True"::FLOAT AS prob_failure
FROM SNOWCORE_INDUSTRIES.ML.HOLDOUT_PREDICTIONS
LIMIT 20;

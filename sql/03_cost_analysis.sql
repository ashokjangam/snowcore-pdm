-- =============================================================================
-- 03_cost_analysis.sql  –  Economic Cost-Benefit Analysis
-- =============================================================================
-- This script turns raw model predictions into dollar values so you can pick
-- the decision threshold that minimises total maintenance cost.
--
-- Concept:
--   • A FALSE ALARM (false positive) means we inspect an asset that was fine.
--     Cost proxy: average cost of an Inspection work order (WO_TYPE_ID = 4).
--   • A MISSED FAILURE (false negative) means an asset broke and we didn't
--     intervene.  Cost proxy: average cost of an Unplanned Emergency work
--     order (WO_TYPE_ID = 1), which includes parts, labour, AND revenue lost
--     during downtime.
--
-- Prerequisites: 02_ml_model.sql must have been run so that
-- SNOWCORE_INDUSTRIES.ML.HOLDOUT_PREDICTIONS exists.
-- =============================================================================

USE ROLE ACCOUNTADMIN;
USE DATABASE SNOWCORE_INDUSTRIES;
USE WAREHOUSE SNOWCORE_INDUSTRIES_WH;

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. False-alarm cost — average cost of an unnecessary inspection
-- ─────────────────────────────────────────────────────────────────────────────
-- WO_TYPE_ID = 4 is "Inspection".  We join to DIM_ASSET (IS_CURRENT = TRUE)
-- to pick up the asset-specific DOWNTIME_IMPACT_PER_HOUR, which captures the
-- revenue lost while the asset is offline for the inspection.

SELECT
    AVG(m.PARTS_COST + m.LABOR_COST + m.DOWNTIME_HOURS * a.DOWNTIME_IMPACT_PER_HOUR) AS FALSE_ALARM_COST,
    COUNT(*) AS n_records
FROM SNOWCORE_INDUSTRIES.SILVER.FCT_MAINTENANCE_LOG m
JOIN SNOWCORE_INDUSTRIES.SILVER.DIM_ASSET a
    ON m.ASSET_ID = a.ASSET_ID AND a.IS_CURRENT = TRUE
WHERE m.WO_TYPE_ID = 4;
-- Result ≈ $6,024.67

-- ─────────────────────────────────────────────────────────────────────────────
-- 2. Missed-failure cost — average cost of an unplanned emergency
-- ─────────────────────────────────────────────────────────────────────────────
-- WO_TYPE_ID = 1 is "Unplanned Emergency".  Same join logic; the average is
-- much higher because emergency repairs are more expensive and downtime is
-- longer.

SELECT
    AVG(m.PARTS_COST + m.LABOR_COST + m.DOWNTIME_HOURS * a.DOWNTIME_IMPACT_PER_HOUR) AS MISSED_FAILURE_COST,
    COUNT(*) AS n_records
FROM SNOWCORE_INDUSTRIES.SILVER.FCT_MAINTENANCE_LOG m
JOIN SNOWCORE_INDUSTRIES.SILVER.DIM_ASSET a
    ON m.ASSET_ID = a.ASSET_ID AND a.IS_CURRENT = TRUE
WHERE m.WO_TYPE_ID = 1;
-- Result ≈ $34,311.55

-- ─────────────────────────────────────────────────────────────────────────────
-- 3. Threshold sweep — find the optimal decision boundary
-- ─────────────────────────────────────────────────────────────────────────────
-- For every candidate threshold (0.05 … 0.50) we classify holdout rows as
-- "predicted failure" when prob_failure >= threshold, then compute the
-- confusion-matrix cells (TP, FP, FN, TN) and the cost-weighted total:
--
--   total_expected_cost = FP × false_alarm_cost + FN × missed_failure_cost
--
-- The threshold with the lowest total_expected_cost is the sweet spot where
-- the model saves the most money.

WITH parsed AS (
    SELECT
        ASSET_ID,
        FAILED_IN_NEXT_7_DAYS,
        PARSE_JSON(PREDICTION):probability:"True"::FLOAT AS prob_failure
    FROM SNOWCORE_INDUSTRIES.ML.HOLDOUT_PREDICTIONS
),
thresholds AS (
    SELECT t.threshold
    FROM (VALUES (0.05),(0.10),(0.15),(0.20),(0.25),(0.30),(0.35),(0.40),(0.45),(0.50)) AS t(threshold)
),
confusion AS (
    SELECT
        t.threshold,
        SUM(CASE WHEN p.prob_failure >= t.threshold AND p.FAILED_IN_NEXT_7_DAYS = 'TRUE'  THEN 1 ELSE 0 END) AS TP,
        SUM(CASE WHEN p.prob_failure >= t.threshold AND p.FAILED_IN_NEXT_7_DAYS = 'FALSE' THEN 1 ELSE 0 END) AS FP,
        SUM(CASE WHEN p.prob_failure <  t.threshold AND p.FAILED_IN_NEXT_7_DAYS = 'TRUE'  THEN 1 ELSE 0 END) AS FN,
        SUM(CASE WHEN p.prob_failure <  t.threshold AND p.FAILED_IN_NEXT_7_DAYS = 'FALSE' THEN 1 ELSE 0 END) AS TN
    FROM parsed p
    CROSS JOIN thresholds t
    GROUP BY t.threshold
)
SELECT
    threshold,
    TP, FP, FN,
    ROUND(TP / NULLIF(TP + FN, 0), 4) AS recall,
    ROUND(TP / NULLIF(TP + FP, 0), 4) AS precision,
    ROUND(FP * 6024.67 + FN * 34311.55, 0) AS total_expected_cost
FROM confusion
ORDER BY threshold;

-- ─────────────────────────────────────────────────────────────────────────────
-- 4. Strategy comparison — do nothing vs. inspect everything vs. model
-- ─────────────────────────────────────────────────────────────────────────────
-- The holdout window spans 83 days.  We annualise each strategy so a finance
-- team can compare them directly.
--
--   A) Inspect nothing  → every actual failure becomes an unplanned emergency.
--   B) Inspect everything → we pay inspection cost for every holdout row.
--   C) Model @ 0.05     → the threshold from step 3 that minimises cost.
--
-- The numbers below (223 failures, 1494 total rows, 548 FP, 26 FN) come from
-- running the sweep on the current holdout set.

SELECT
    'A: Inspect nothing' AS strategy,
    223 * 34311.55 AS holdout_cost_83d,
    ROUND(223 * 34311.55 * (365.0/83), 0) AS annualized_cost
UNION ALL
SELECT
    'B: Inspect everything',
    1494 * 6024.67,
    ROUND(1494 * 6024.67 * (365.0/83), 0)
UNION ALL
SELECT
    'C: Model @ 0.05 threshold',
    548 * 6024.67 + 26 * 34311.55,
    ROUND((548 * 6024.67 + 26 * 34311.55) * (365.0/83), 0)
ORDER BY holdout_cost_83d;

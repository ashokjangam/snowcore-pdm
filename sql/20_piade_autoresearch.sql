/* ============================================================================
   PIADE guarded autoresearch.

   Search space is limited to two fixed rolling-origin validation periods:
     validation 1: 2021-04-01 through 2021-07-31
     validation 2: 2021-08-01 through 2021-11-30
   Rows at or after 2021-12-01 are the reused holdout. They are never loaded
   while any selection decision is still open. They are read at most once, and
   only after every promotion gate has already passed, purely to confirm a
   decision that was made without them.

   This file changes no production object. It never writes PLANT_B_RISK_SCORE,
   PLANT_B_MODEL_METRICS, PLANT_B_FEATURE_IMPORTANCE or PLANT_B_CALIBRATION_BAND.
   When the gates pass it records PROMOTION_ELIGIBLE plus a deterministic
   champion contract in ML.PIADE_CHAMPION_CONTRACT. Promotion remains a separate,
   explicit act performed by sql/15_plant_b_risk.sql reading that contract.

   Honest limits:
   - A finite 25-trial search over an allowlisted space does not find an optimal
     model; it finds the best of what it tried.
   - The holdout is reused across campaigns, so repeated campaigns erode its
     value as evidence. The confirmation metrics are reported, never optimised.
   - The 180-second challenger budget is checked between fits. The baseline is
     exempt so both reference folds always complete, but its overrun is still
     logged. A native scikit-learn, XGBoost or LightGBM fit already running
     inside warehouse Python cannot be preempted, so an overrun is detected
     after the fact. The campaign cap is 1800 seconds after the mandatory
     baseline; no challenger or post-gate refit/registry operation starts after
     that cap. RandomForest on the full 299-feature table exceeded 30 minutes
     on COMPUTE_WH X-Small, so forest sizes are capped; ExtraTrees 700 remains
     the production baseline because it finished both folds in under two minutes.
   ========================================================================== */

USE ROLE ACCOUNTADMIN;
USE DATABASE SNOWCORE_REAL;
USE WAREHOUSE COMPUTE_WH;
ALTER SESSION SET TIMEZONE = 'UTC';
ALTER SESSION SET QUERY_TAG = 'snowcore-real|piade|autoresearch-ddl';

/* --------------------------------------------------------------------------
   Relational logs. These are the system of record. Experiment Tracking and the
   Model Registry are best-effort mirrors and may legitimately be absent.
   -------------------------------------------------------------------------- */

CREATE TABLE IF NOT EXISTS ML.PIADE_RESEARCH_CAMPAIGN (
  CAMPAIGN_ID                 VARCHAR NOT NULL,
  STARTED_AT                  TIMESTAMP_NTZ NOT NULL,
  FINISHED_AT                 TIMESTAMP_NTZ,
  STATUS                      VARCHAR NOT NULL,
  REQUESTED_TRIALS            INTEGER NOT NULL,
  TRIAL_LIMIT                 INTEGER NOT NULL,
  EVALUATED_TRIALS            INTEGER DEFAULT 0,
  REJECTED_PROPOSALS          INTEGER DEFAULT 0,
  CRASHED_TRIALS              INTEGER DEFAULT 0,
  MAX_ELAPSED_SECONDS         INTEGER NOT NULL,
  TRIAL_BUDGET_SECONDS        INTEGER NOT NULL,
  STOP_REASON                 VARCHAR,
  TARGET_DEFINITION           VARCHAR NOT NULL,
  VALIDATION_1_START          TIMESTAMP_NTZ NOT NULL,
  VALIDATION_1_END_EXCLUSIVE  TIMESTAMP_NTZ NOT NULL,
  VALIDATION_2_START          TIMESTAMP_NTZ NOT NULL,
  VALIDATION_2_END_EXCLUSIVE  TIMESTAMP_NTZ NOT NULL,
  HOLDOUT_START               TIMESTAMP_NTZ NOT NULL,
  SEARCH_MAX_HOUR_TS          TIMESTAMP_NTZ,
  BASELINE_CONFIG             VARIANT NOT NULL,
  BASELINE_RUN_ID             VARCHAR,
  BASELINE_MEAN_AUC           FLOAT,
  BASELINE_WORST_AUC          FLOAT,
  BASELINE_PRECISION_LIFT     FLOAT,
  CHAMPION_RUN_ID             VARCHAR,
  CHAMPION_CONFIG             VARIANT,
  CHAMPION_MEAN_AUC           FLOAT,
  CHAMPION_WORST_AUC          FLOAT,
  CHAMPION_PRECISION_LIFT     FLOAT,
  GATES_EVALUATED             INTEGER,
  GATES_PASSED                INTEGER,
  PROMOTION_STATUS            VARCHAR,
  PROMOTION_ELIGIBLE          BOOLEAN DEFAULT FALSE,
  PROMOTION_REASONS           VARIANT,
  HOLDOUT_EVALUATED           BOOLEAN DEFAULT FALSE,
  HOLDOUT_AUC                 FLOAT,
  HOLDOUT_TOP10_PRECISION     FLOAT,
  PRODUCTION_TABLES_MODIFIED  BOOLEAN DEFAULT FALSE,
  QUERY_TAG                   VARCHAR NOT NULL,
  PACKAGE_VERSIONS            VARIANT,
  EXPERIMENT_TRACKING_STATUS  VARCHAR,
  REGISTRY_STATUS             VARCHAR,
  ERROR_MESSAGE               VARCHAR,
  CREATED_BY                  VARCHAR DEFAULT CURRENT_USER()
)
COMMENT = 'Guarded PIADE autoresearch campaigns. PRODUCTION_TABLES_MODIFIED is always FALSE by construction; promotion is performed elsewhere.';

/* TRIAL_DECISION is the durable decision: BASELINE, KEEP, DISCARD, CRASH or
   REJECTED. IN_PROGRESS appears only while a trial is still running.
   EVALUATION_STATUS separately preserves whether the evaluation itself
   completed: COMPLETED, FAILED or NOT_EVALUATED. A trial can therefore be
   DISCARD with EVALUATION_STATUS='COMPLETED' (evaluated, simply not the best)
   which is a very different fact from CRASH with 'FAILED'. */
CREATE TABLE IF NOT EXISTS ML.PIADE_RESEARCH_RUN (
  RUN_ID                    VARCHAR NOT NULL,
  CAMPAIGN_ID               VARCHAR NOT NULL,
  ATTEMPT_SEQ               INTEGER NOT NULL,
  TRIAL_NUMBER              INTEGER,
  PROPOSED_FOR_TRIAL        INTEGER,
  IS_BASELINE_CONFIG        BOOLEAN NOT NULL,
  PROPOSAL_SOURCE           VARCHAR NOT NULL,
  PROPOSAL_RAW              VARIANT,
  MODEL_FAMILY              VARCHAR,
  CONFIG                    VARIANT,
  CONFIG_HASH               VARCHAR,
  FEATURE_GROUPS            VARIANT,
  FEATURE_COUNT             INTEGER,
  RATIONALE                 VARCHAR,
  TRIAL_DECISION            VARCHAR NOT NULL,
  EVALUATION_STATUS         VARCHAR NOT NULL,
  STATUS                    VARCHAR,
  DECISION_REASON           VARCHAR,
  TRIAL_BUDGET_SECONDS      INTEGER,
  BUDGET_EXCEEDED           BOOLEAN DEFAULT FALSE,
  STARTED_AT                TIMESTAMP_NTZ NOT NULL,
  FINISHED_AT               TIMESTAMP_NTZ,
  RUNTIME_SECONDS           FLOAT,
  MEAN_AUC                  FLOAT,
  WORST_AUC                 FLOAT,
  MEAN_AVG_PRECISION        FLOAT,
  MEAN_TOP10_PRECISION      FLOAT,
  MEAN_TOP10_RECALL         FLOAT,
  MEAN_BALANCED_ACCURACY    FLOAT,
  MEAN_PERSISTENCE_AUC      FLOAT,
  MEAN_PERSISTENCE_AP       FLOAT,
  MEAN_PERSISTENCE_TOP10_P  FLOAT,
  MEAN_PERSISTENCE_TOP10_R  FLOAT,
  TOP10_PRECISION_LIFT      FLOAT,
  LINE_PERSISTENCE_FAILURES INTEGER,
  FOLD_METRICS              VARIANT,
  LINE_METRICS              VARIANT,
  QUERY_TAG                 VARCHAR NOT NULL,
  PACKAGE_VERSIONS          VARIANT,
  EXPERIMENT_TRACKING_STATUS VARCHAR,
  ERROR_MESSAGE             VARCHAR,
  CREATED_AT                TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
)
COMMENT = 'One row per proposal. Rejected proposals are logged with TRIAL_NUMBER NULL so the rejection is auditable without consuming a trial slot.';

CREATE TABLE IF NOT EXISTS ML.PIADE_RESEARCH_FOLD_METRIC (
  CAMPAIGN_ID                  VARCHAR NOT NULL,
  RUN_ID                       VARCHAR NOT NULL,
  TRIAL_NUMBER                 INTEGER NOT NULL,
  FOLD_NAME                    VARCHAR NOT NULL,
  TRAIN_START                  TIMESTAMP_NTZ,
  TRAIN_END_EXCLUSIVE          TIMESTAMP_NTZ NOT NULL,
  VALIDATION_START             TIMESTAMP_NTZ NOT NULL,
  VALIDATION_END_EXCLUSIVE     TIMESTAMP_NTZ NOT NULL,
  TRAIN_ROWS                   INTEGER NOT NULL,
  VALIDATION_ROWS              INTEGER NOT NULL,
  POSITIVE_RATE                FLOAT,
  AUC                          FLOAT,
  AVG_PRECISION                FLOAT,
  TOP10_ROWS                   INTEGER,
  TOP10_PRECISION              FLOAT,
  TOP10_RECALL                 FLOAT,
  BALANCED_ACCURACY            FLOAT,
  PERSISTENCE_AUC              FLOAT,
  PERSISTENCE_AVG_PRECISION    FLOAT,
  PERSISTENCE_TOP10_ROWS       INTEGER,
  PERSISTENCE_TOP10_PRECISION  FLOAT,
  PERSISTENCE_TOP10_RECALL     FLOAT,
  PERSISTENCE_BALANCED_ACCURACY FLOAT,
  TOP10_PRECISION_LIFT         FLOAT,
  FIT_SECONDS                  FLOAT,
  RUNTIME_SECONDS              FLOAT,
  QUERY_TAG                    VARCHAR NOT NULL,
  CREATED_AT                   TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
)
COMMENT = 'Fold-level validation metrics. No row may reference data at or after the holdout start.';

CREATE TABLE IF NOT EXISTS ML.PIADE_RESEARCH_LINE_METRIC (
  CAMPAIGN_ID                  VARCHAR NOT NULL,
  RUN_ID                       VARCHAR NOT NULL,
  TRIAL_NUMBER                 INTEGER NOT NULL,
  FOLD_NAME                    VARCHAR NOT NULL,
  MACHINE_CODE                 VARCHAR NOT NULL,
  VALIDATION_START             TIMESTAMP_NTZ NOT NULL,
  VALIDATION_END_EXCLUSIVE     TIMESTAMP_NTZ NOT NULL,
  VALIDATION_ROWS              INTEGER NOT NULL,
  POSITIVE_RATE                FLOAT,
  AUC                          FLOAT,
  AVG_PRECISION                FLOAT,
  TOP10_ROWS                   INTEGER,
  TOP10_PRECISION              FLOAT,
  TOP10_RECALL                 FLOAT,
  PERSISTENCE_AUC              FLOAT,
  PERSISTENCE_TOP10_PRECISION  FLOAT,
  PERSISTENCE_TOP10_RECALL     FLOAT,
  TOP10_PRECISION_LIFT         FLOAT,
  BEATS_PERSISTENCE            BOOLEAN,
  QUERY_TAG                    VARCHAR NOT NULL,
  CREATED_AT                   TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
)
COMMENT = 'Per-line per-fold validation metrics; the evidence for the no-new-persistence-failure gate.';

CREATE TABLE IF NOT EXISTS ML.PIADE_RESEARCH_PROMOTION_GATE (
  CAMPAIGN_ID       VARCHAR NOT NULL,
  GATE_ORDER        INTEGER NOT NULL,
  GATE_NAME         VARCHAR NOT NULL,
  GATE_RULE         VARCHAR NOT NULL,
  PASSED            BOOLEAN NOT NULL,
  CHAMPION_VALUE    FLOAT,
  BASELINE_VALUE    FLOAT,
  MARGIN            FLOAT,
  DETAIL            VARCHAR,
  EVALUATED_AT      TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
)
COMMENT = 'Exact promotion gate outcomes. Any FALSE row preserves production unchanged.';

CREATE TABLE IF NOT EXISTS ML.PIADE_RESEARCH_HOLDOUT_METRIC (
  CAMPAIGN_ID                  VARCHAR NOT NULL,
  RUN_ID                       VARCHAR NOT NULL,
  EVALUATION_LABEL             VARCHAR NOT NULL,
  SCOPE                        VARCHAR NOT NULL,
  HOLDOUT_START                TIMESTAMP_NTZ NOT NULL,
  HOLDOUT_END                  TIMESTAMP_NTZ NOT NULL,
  HOLDOUT_ROWS                 INTEGER NOT NULL,
  POSITIVE_RATE                FLOAT,
  AUC                          FLOAT,
  AVG_PRECISION                FLOAT,
  TOP10_ROWS                   INTEGER,
  TOP10_PRECISION              FLOAT,
  TOP10_RECALL                 FLOAT,
  BALANCED_ACCURACY            FLOAT,
  PERSISTENCE_AUC              FLOAT,
  PERSISTENCE_AVG_PRECISION    FLOAT,
  PERSISTENCE_TOP10_PRECISION  FLOAT,
  PERSISTENCE_TOP10_RECALL     FLOAT,
  TOP10_PRECISION_LIFT         FLOAT,
  USED_FOR_SELECTION           BOOLEAN DEFAULT FALSE,
  QUERY_TAG                    VARCHAR NOT NULL,
  CREATED_AT                   TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
)
COMMENT = 'Reused-holdout confirmation, written only after all gates passed. USED_FOR_SELECTION is FALSE by construction: the champion was already fixed before these rows existed.';

/* The contract is the hand-off. sql/15_plant_b_risk.sql must read it
   explicitly and deliberately; nothing here applies it. */
CREATE TABLE IF NOT EXISTS ML.PIADE_CHAMPION_CONTRACT (
  CONTRACT_ID             VARCHAR NOT NULL,
  CAMPAIGN_ID             VARCHAR NOT NULL,
  CREATED_AT              TIMESTAMP_NTZ NOT NULL,
  PROMOTION_STATUS        VARCHAR NOT NULL,
  PROMOTION_ELIGIBLE      BOOLEAN NOT NULL,
  PROMOTION_REASONS       VARIANT,
  APPLIED_TO_PRODUCTION   BOOLEAN DEFAULT FALSE,
  APPLIED_AT              TIMESTAMP_NTZ,
  APPLIED_BY              VARCHAR,
  CHAMPION_RUN_ID         VARCHAR,
  MODEL_FAMILY            VARCHAR,
  CONFIG                  VARIANT,
  CONFIG_HASH             VARCHAR,
  FEATURE_GROUPS          VARIANT,
  FEATURE_LIST            VARIANT,
  FEATURE_COUNT           INTEGER,
  FEATURE_LIST_HASH       VARCHAR,
  RANDOM_SEED             INTEGER NOT NULL,
  SOURCE_TABLE            VARCHAR NOT NULL,
  TRAIN_END_EXCLUSIVE     TIMESTAMP_NTZ NOT NULL,
  TARGET_DEFINITION       VARCHAR NOT NULL,
  VALIDATION_MEAN_AUC     FLOAT,
  VALIDATION_WORST_AUC    FLOAT,
  VALIDATION_PRECISION_LIFT FLOAT,
  BASELINE_MEAN_AUC       FLOAT,
  BASELINE_WORST_AUC      FLOAT,
  BASELINE_PRECISION_LIFT FLOAT,
  HOLDOUT_AUC             FLOAT,
  HOLDOUT_AVG_PRECISION   FLOAT,
  HOLDOUT_TOP10_PRECISION FLOAT,
  HOLDOUT_TOP10_RECALL    FLOAT,
  NOTES                   VARCHAR
)
COMMENT = 'Deterministic champion contract for explicit downstream promotion. APPLIED_TO_PRODUCTION stays FALSE until sql/15 sets it.';

/* Safe additive migration for accounts where an earlier draft of this file
   already created the tables. CREATE TABLE IF NOT EXISTS does not evolve an
   existing schema; these statements preserve every past campaign and add only
   nullable/defaulted columns needed by the current procedure and views. */
ALTER TABLE ML.PIADE_RESEARCH_CAMPAIGN ADD COLUMN IF NOT EXISTS EVALUATED_TRIALS INTEGER DEFAULT 0;
ALTER TABLE ML.PIADE_RESEARCH_CAMPAIGN ADD COLUMN IF NOT EXISTS REJECTED_PROPOSALS INTEGER DEFAULT 0;
ALTER TABLE ML.PIADE_RESEARCH_CAMPAIGN ADD COLUMN IF NOT EXISTS CRASHED_TRIALS INTEGER DEFAULT 0;
ALTER TABLE ML.PIADE_RESEARCH_CAMPAIGN ADD COLUMN IF NOT EXISTS TRIAL_BUDGET_SECONDS INTEGER;
ALTER TABLE ML.PIADE_RESEARCH_CAMPAIGN ADD COLUMN IF NOT EXISTS BASELINE_RUN_ID VARCHAR;
ALTER TABLE ML.PIADE_RESEARCH_CAMPAIGN ADD COLUMN IF NOT EXISTS BASELINE_MEAN_AUC FLOAT;
ALTER TABLE ML.PIADE_RESEARCH_CAMPAIGN ADD COLUMN IF NOT EXISTS BASELINE_WORST_AUC FLOAT;
ALTER TABLE ML.PIADE_RESEARCH_CAMPAIGN ADD COLUMN IF NOT EXISTS BASELINE_PRECISION_LIFT FLOAT;
ALTER TABLE ML.PIADE_RESEARCH_CAMPAIGN ADD COLUMN IF NOT EXISTS CHAMPION_PRECISION_LIFT FLOAT;
ALTER TABLE ML.PIADE_RESEARCH_CAMPAIGN ADD COLUMN IF NOT EXISTS GATES_EVALUATED INTEGER;
ALTER TABLE ML.PIADE_RESEARCH_CAMPAIGN ADD COLUMN IF NOT EXISTS GATES_PASSED INTEGER;
ALTER TABLE ML.PIADE_RESEARCH_CAMPAIGN ADD COLUMN IF NOT EXISTS PROMOTION_STATUS VARCHAR;
ALTER TABLE ML.PIADE_RESEARCH_CAMPAIGN ADD COLUMN IF NOT EXISTS PROMOTION_ELIGIBLE BOOLEAN DEFAULT FALSE;
ALTER TABLE ML.PIADE_RESEARCH_CAMPAIGN ADD COLUMN IF NOT EXISTS PROMOTION_REASONS VARIANT;
ALTER TABLE ML.PIADE_RESEARCH_CAMPAIGN ADD COLUMN IF NOT EXISTS HOLDOUT_EVALUATED BOOLEAN DEFAULT FALSE;
ALTER TABLE ML.PIADE_RESEARCH_CAMPAIGN ADD COLUMN IF NOT EXISTS HOLDOUT_AUC FLOAT;
ALTER TABLE ML.PIADE_RESEARCH_CAMPAIGN ADD COLUMN IF NOT EXISTS HOLDOUT_TOP10_PRECISION FLOAT;
ALTER TABLE ML.PIADE_RESEARCH_CAMPAIGN ADD COLUMN IF NOT EXISTS PRODUCTION_TABLES_MODIFIED BOOLEAN DEFAULT FALSE;

ALTER TABLE ML.PIADE_RESEARCH_RUN ADD COLUMN IF NOT EXISTS ATTEMPT_SEQ INTEGER;
ALTER TABLE ML.PIADE_RESEARCH_RUN ADD COLUMN IF NOT EXISTS PROPOSED_FOR_TRIAL INTEGER;
ALTER TABLE ML.PIADE_RESEARCH_RUN ADD COLUMN IF NOT EXISTS MODEL_FAMILY VARCHAR;
ALTER TABLE ML.PIADE_RESEARCH_RUN ADD COLUMN IF NOT EXISTS FEATURE_GROUPS VARIANT;
ALTER TABLE ML.PIADE_RESEARCH_RUN ADD COLUMN IF NOT EXISTS FEATURE_COUNT INTEGER;
ALTER TABLE ML.PIADE_RESEARCH_RUN ADD COLUMN IF NOT EXISTS TRIAL_DECISION VARCHAR;
ALTER TABLE ML.PIADE_RESEARCH_RUN ADD COLUMN IF NOT EXISTS EVALUATION_STATUS VARCHAR;
ALTER TABLE ML.PIADE_RESEARCH_RUN ADD COLUMN IF NOT EXISTS STATUS VARCHAR;
ALTER TABLE ML.PIADE_RESEARCH_RUN ADD COLUMN IF NOT EXISTS DECISION_REASON VARCHAR;
ALTER TABLE ML.PIADE_RESEARCH_RUN ADD COLUMN IF NOT EXISTS TRIAL_BUDGET_SECONDS INTEGER;
ALTER TABLE ML.PIADE_RESEARCH_RUN ADD COLUMN IF NOT EXISTS BUDGET_EXCEEDED BOOLEAN DEFAULT FALSE;
ALTER TABLE ML.PIADE_RESEARCH_RUN ADD COLUMN IF NOT EXISTS TOP10_PRECISION_LIFT FLOAT;
ALTER TABLE ML.PIADE_RESEARCH_RUN ADD COLUMN IF NOT EXISTS LINE_PERSISTENCE_FAILURES INTEGER;
ALTER TABLE ML.PIADE_RESEARCH_RUN ADD COLUMN IF NOT EXISTS LINE_METRICS VARIANT;
ALTER TABLE ML.PIADE_RESEARCH_RUN ADD COLUMN IF NOT EXISTS EXPERIMENT_TRACKING_STATUS VARCHAR;
/* The first draft declared TRIAL_NUMBER NOT NULL. Rejections deliberately do
   not consume trial numbers. ALTER COLUMN has no IF EXISTS form, so inspect
   metadata first to keep this migration rerunnable; no row is erased. */
EXECUTE IMMEDIATE $MIGRATE_TRIAL_NUMBER$
DECLARE
  IS_TRIAL_NUMBER_NULLABLE VARCHAR;
BEGIN
  SELECT IS_NULLABLE INTO :IS_TRIAL_NUMBER_NULLABLE
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA='ML'
    AND TABLE_NAME='PIADE_RESEARCH_RUN'
    AND COLUMN_NAME='TRIAL_NUMBER';
  IF (IS_TRIAL_NUMBER_NULLABLE = 'NO') THEN
    ALTER TABLE ML.PIADE_RESEARCH_RUN
      ALTER COLUMN TRIAL_NUMBER DROP NOT NULL;
  END IF;
END;
$MIGRATE_TRIAL_NUMBER$;

ALTER TABLE ML.PIADE_RESEARCH_FOLD_METRIC ADD COLUMN IF NOT EXISTS TOP10_PRECISION_LIFT FLOAT;
ALTER TABLE ML.PIADE_RESEARCH_FOLD_METRIC ADD COLUMN IF NOT EXISTS FIT_SECONDS FLOAT;

/* MAX_TRIALS carries a literal default. If this account rejects DEFAULT in a
   Python procedure signature, drop the DEFAULT clause and always call the
   procedure with an explicit argument; nothing else in the body depends on it.
   snowflake-ml-python is unpinned at CREATE time because `==` in PACKAGES
   broke EXECUTE IMMEDIATE FROM; 2.1.0 was verified present on this account. */
CREATE OR REPLACE PROCEDURE ML.RUN_PIADE_AUTORESEARCH(MAX_TRIALS INTEGER DEFAULT 25)
RETURNS VARIANT
LANGUAGE PYTHON
RUNTIME_VERSION = '3.11'
PACKAGES = (
  'snowflake-snowpark-python',
  'snowflake-ml-python',
  'scikit-learn',
  'xgboost',
  'lightgbm',
  'pandas',
  'numpy',
  'pyarrow'
)
HANDLER = 'run'
EXECUTE AS CALLER
AS
$$
import hashlib
import importlib.metadata
import json
import math
import re
import time
import traceback
import uuid

import numpy as np
import pandas as pd
from sklearn.ensemble import (
    ExtraTreesClassifier,
    HistGradientBoostingClassifier,
    RandomForestClassifier,
)
from sklearn.metrics import (
    average_precision_score,
    balanced_accuracy_score,
    roc_auc_score,
)
from xgboost import XGBClassifier
from lightgbm import LGBMClassifier


SEED = 20260925
HARD_TRIAL_LIMIT = 25
MAX_ELAPSED_SECONDS = 1800
TRIAL_BUDGET_SECONDS = 180
MIN_MASKED_FEATURES = 20
EPS = 1e-9
SOURCE_TABLE = "ML.PLANT_B_FEATURES"
V1_START = pd.Timestamp("2021-04-01")
V1_END = pd.Timestamp("2021-08-01")
V2_START = pd.Timestamp("2021-08-01")
V2_END = pd.Timestamp("2021-12-01")
HOLDOUT_START = pd.Timestamp("2021-12-01")
TARGET = "next machine-hour PCT_DOWNTIME > 0.10"
# MAX_ELAPSED_SECONDS gates challengers and all post-gate work. Trial 1 is the
# mandatory reference and always completes both folds even if it crosses 1800s.
NOT_FEATURES = {
    "ROW_ID", "MACHINE_KEY", "MACHINE_CODE", "HOUR_TS", "SPLIT_PART",
    "DATA_ORIGIN", "LABEL_HEAVY_STOP", "NEXT_HOUR_DOWNTIME",
    "BASELINE_SCORE",
}

# Feature groups partition the 299 published+engineered columns. Rules are
# evaluated in order, so every feature lands in exactly one group.
FEATURE_GROUP_ORDER = [
    "MACHINE_IDENTITY", "CALENDAR", "RECENCY", "ACCELERATION", "LAGS",
    "ROLLING_DISPERSION", "ROLLING_MEAN", "DERIVED_TOTALS", "ALARM_RAW",
    "TRANSITION_RAW", "SOURCE_CORE",
]


def feature_group_of(name):
    if name in {"MACHINE_S_1", "MACHINE_S_2", "MACHINE_S_3", "MACHINE_S_4",
                "MACHINE_S_5"}:
        return "MACHINE_IDENTITY"
    if name in {"HOUR_SIN", "HOUR_COS", "DOW_SIN", "DOW_COS"}:
        return "CALENDAR"
    if name in {"HOURS_SINCE_HEAVY_STOP", "GAP_HOURS"}:
        return "RECENCY"
    if name.endswith("_ACCEL_3_24"):
        return "ACCELERATION"
    if re.search(r"_LAG_\d+$", name):
        return "LAGS"
    if re.search(r"_(MAX|STD)_\d+$", name):
        return "ROLLING_DISPERSION"
    if re.search(r"_MEAN_\d+$", name):
        return "ROLLING_MEAN"
    if name in {"RUN_FRAC", "ALARM_TOTAL", "ALARM_DISTINCT", "TRANSITION_TOTAL"}:
        return "DERIVED_TOTALS"
    if re.fullmatch(r"A_\d+", name):
        return "ALARM_RAW"
    if name.startswith("TRANS_"):
        return "TRANSITION_RAW"
    return "SOURCE_CORE"


def production_feature_order(df):
    """Reproduce sql/15_plant_b_risk.sql's exact 299-feature order.

    ExtraTrees samples feature indices, so matching only the set is not enough:
    source columns retain dataframe order, followed by derived, history and
    extras in the exact order used by the production training procedure.
    """
    derived = ["RUN_FRAC", "ALARM_TOTAL", "ALARM_DISTINCT", "TRANSITION_TOTAL"]
    history = []
    for source_name in [
        "PCT_DOWNTIME", "PCT_IDLE", "RUN_FRAC", "ALARM_TOTAL",
        "ALARM_DISTINCT", "STATE_CHANGES", "COUNT_SUM",
    ]:
        for window in (3, 6, 12, 24, 72):
            history.append(f"{source_name}_MEAN_{window}")
            if window in (12, 24, 72):
                history.extend([
                    f"{source_name}_MAX_{window}",
                    f"{source_name}_STD_{window}",
                ])
        history.extend([
            f"{source_name}_LAG_{lag}" for lag in (1, 2, 3, 6, 12, 24)
        ])
    extras = [
        "DOWNTIME_ACCEL_3_24", "RUN_ACCEL_3_24", "ALARM_ACCEL_3_24",
        "HOURS_SINCE_HEAVY_STOP", "GAP_HOURS",
        "HOUR_SIN", "HOUR_COS", "DOW_SIN", "DOW_COS",
        "MACHINE_S_1", "MACHINE_S_2", "MACHINE_S_3", "MACHINE_S_4",
        "MACHINE_S_5",
    ]
    engineered = set(derived + history + extras)
    source = [
        column for column in df.columns
        if column not in NOT_FEATURES
        and column not in engineered
        and pd.api.types.is_numeric_dtype(df[column])
    ]
    ordered = source + derived + history + extras
    missing = [column for column in ordered if column not in df.columns]
    if missing:
        raise ValueError(
            "Production feature contract is missing columns: "
            + ",".join(missing[:20])
        )
    if len(ordered) != 299 or len(set(ordered)) != 299:
        raise ValueError(
            "Production feature order drift: expected 299 unique columns, got "
            + str(len(ordered)) + " entries and "
            + str(len(set(ordered))) + " unique columns"
        )
    return ordered


BASELINE = {
    "model": "extra_trees",
    "params": {
        "n_estimators": 700,
        "max_features": 0.4,
        "min_samples_leaf": 30,
        "class_weight": "balanced",
    },
    # The baseline must reproduce the current production model exactly, so it
    # uses every group: no mask at all.
    "feature_groups": list(FEATURE_GROUP_ORDER),
}

# Every accepted key and value is checked. Unknown keys never reach a model.
ALLOWED = {
    "extra_trees": {
        "n_estimators": ("int", 200, 800),
        "max_features": ("float", 0.15, 1.0),
        "min_samples_leaf": ("int", 2, 100),
        "class_weight": ("choice", ["balanced", "balanced_subsample", None]),
    },
    "random_forest": {
        "n_estimators": ("int", 200, 400),
        "max_features": ("float", 0.15, 1.0),
        "min_samples_leaf": ("int", 2, 100),
        "class_weight": ("choice", ["balanced", "balanced_subsample", None]),
    },
    "hist_gradient_boosting": {
        "learning_rate": ("float", 0.01, 0.30),
        "max_iter": ("int", 100, 400),
        "max_leaf_nodes": ("int", 7, 127),
        "min_samples_leaf": ("int", 10, 150),
        "l2_regularization": ("float", 0.0, 20.0),
    },
    "xgboost": {
        "n_estimators": ("int", 100, 400),
        "learning_rate": ("float", 0.01, 0.30),
        "max_depth": ("int", 2, 10),
        "min_child_weight": ("float", 1.0, 30.0),
        "subsample": ("float", 0.50, 1.0),
        "colsample_bytree": ("float", 0.30, 1.0),
        "reg_lambda": ("float", 0.0, 30.0),
    },
    "lightgbm": {
        "n_estimators": ("int", 100, 400),
        "learning_rate": ("float", 0.01, 0.30),
        "num_leaves": ("int", 7, 127),
        "min_child_samples": ("int", 10, 150),
        "subsample": ("float", 0.50, 1.0),
        "colsample_bytree": ("float", 0.30, 1.0),
        "reg_lambda": ("float", 0.0, 30.0),
    },
}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False)


def config_hash(config):
    return hashlib.sha256(canonical(config).encode("utf-8")).hexdigest()


def ts_text(value):
    """Bind timestamps as text; Snowflake casts on insert into TIMESTAMP_NTZ."""
    return pd.Timestamp(value).strftime("%Y-%m-%d %H:%M:%S.%f")


def opt_float(value):
    if value is None:
        return None
    value = float(value)
    return None if not math.isfinite(value) else value


def validate_config(candidate):
    """Return a canonical allowlisted config or raise. No partial coercion."""
    if not isinstance(candidate, dict):
        raise ValueError("config must be an object")
    if set(candidate) != {"model", "params", "feature_groups"}:
        raise ValueError(
            "config must contain exactly model, params and feature_groups"
        )
    model = candidate["model"]
    params = candidate["params"]
    groups = candidate["feature_groups"]
    if model not in ALLOWED or not isinstance(params, dict):
        raise ValueError("model or params is not allowlisted")
    if not isinstance(groups, list) or not groups:
        raise ValueError("feature_groups must be a non-empty list")
    if len(set(groups)) != len(groups):
        raise ValueError("feature_groups must not repeat a group")
    for group in groups:
        if group not in FEATURE_GROUP_ORDER:
            raise ValueError(f"{group} is not an allowlisted feature group")
    rules = ALLOWED[model]
    if set(params) != set(rules):
        raise ValueError("params must contain exactly: " + ",".join(sorted(rules)))
    clean = {}
    for name, rule in rules.items():
        value = params[name]
        kind = rule[0]
        if kind == "int":
            if isinstance(value, bool) or not isinstance(value, (int, np.integer)):
                raise ValueError(f"{name} must be an integer")
            value = int(value)
            if value < rule[1] or value > rule[2]:
                raise ValueError(f"{name} is outside its allowlisted range")
        elif kind == "float":
            if isinstance(value, bool) or not isinstance(
                value, (int, float, np.integer, np.floating)
            ):
                raise ValueError(f"{name} must be numeric")
            value = float(value)
            if not math.isfinite(value) or value < rule[1] or value > rule[2]:
                raise ValueError(f"{name} is outside its allowlisted range")
        elif kind == "choice":
            if value not in rule[1]:
                raise ValueError(f"{name} is not an allowlisted choice")
        clean[name] = value
    ordered = [g for g in FEATURE_GROUP_ORDER if g in set(groups)]
    return {"model": model, "params": clean, "feature_groups": ordered}


def masked_features(config, production_features):
    """Filter production order without reordering surviving columns."""
    selected_groups = set(config["feature_groups"])
    selected = [
        column for column in production_features
        if feature_group_of(column) in selected_groups
    ]
    if len(selected) < MIN_MASKED_FEATURES:
        raise ValueError(
            "feature mask yields "
            + str(len(selected))
            + " features, below the "
            + str(MIN_MASKED_FEATURES)
            + "-feature floor"
        )
    return selected


ALL_GROUPS = list(FEATURE_GROUP_ORDER)


def deterministic_candidates():
    """Stable candidates used whenever Cortex cannot supply a usable proposal."""
    tuned = [
        {"model":"extra_trees","params":{"n_estimators":500,"max_features":0.25,"min_samples_leaf":15,"class_weight":"balanced"},"feature_groups":ALL_GROUPS},
        {"model":"extra_trees","params":{"n_estimators":500,"max_features":0.55,"min_samples_leaf":20,"class_weight":"balanced"},"feature_groups":ALL_GROUPS},
        {"model":"extra_trees","params":{"n_estimators":600,"max_features":0.70,"min_samples_leaf":45,"class_weight":"balanced_subsample"},"feature_groups":ALL_GROUPS},
        {"model":"extra_trees","params":{"n_estimators":700,"max_features":0.40,"min_samples_leaf":30,"class_weight":"balanced"},"feature_groups":["ROLLING_MEAN","ROLLING_DISPERSION","LAGS","ACCELERATION","RECENCY","DERIVED_TOTALS","CALENDAR","MACHINE_IDENTITY"]},
        {"model":"extra_trees","params":{"n_estimators":400,"max_features":0.30,"min_samples_leaf":25,"class_weight":"balanced"},"feature_groups":["SOURCE_CORE","DERIVED_TOTALS","ROLLING_MEAN","LAGS","RECENCY"]},
        {"model":"random_forest","params":{"n_estimators":250,"max_features":0.25,"min_samples_leaf":15,"class_weight":"balanced_subsample"},"feature_groups":ALL_GROUPS},
        {"model":"hist_gradient_boosting","params":{"learning_rate":0.06,"max_iter":250,"max_leaf_nodes":31,"min_samples_leaf":40,"l2_regularization":3.0},"feature_groups":ALL_GROUPS},
        {"model":"lightgbm","params":{"n_estimators":350,"learning_rate":0.04,"num_leaves":31,"min_child_samples":40,"subsample":0.8,"colsample_bytree":0.6,"reg_lambda":8.0},"feature_groups":["ROLLING_MEAN","ROLLING_DISPERSION","LAGS","ACCELERATION","RECENCY","DERIVED_TOTALS"]},
        {"model":"hist_gradient_boosting","params":{"learning_rate":0.03,"max_iter":400,"max_leaf_nodes":15,"min_samples_leaf":30,"l2_regularization":1.0},"feature_groups":ALL_GROUPS},
        {"model":"hist_gradient_boosting","params":{"learning_rate":0.05,"max_iter":300,"max_leaf_nodes":31,"min_samples_leaf":50,"l2_regularization":5.0},"feature_groups":ALL_GROUPS},
        {"model":"hist_gradient_boosting","params":{"learning_rate":0.02,"max_iter":350,"max_leaf_nodes":63,"min_samples_leaf":75,"l2_regularization":10.0},"feature_groups":["ROLLING_MEAN","ROLLING_DISPERSION","LAGS","ACCELERATION","RECENCY","CALENDAR","MACHINE_IDENTITY"]},
        {"model":"hist_gradient_boosting","params":{"learning_rate":0.08,"max_iter":200,"max_leaf_nodes":15,"min_samples_leaf":100,"l2_regularization":2.0},"feature_groups":ALL_GROUPS},
        {"model":"xgboost","params":{"n_estimators":300,"learning_rate":0.03,"max_depth":3,"min_child_weight":5.0,"subsample":0.8,"colsample_bytree":0.5,"reg_lambda":5.0},"feature_groups":ALL_GROUPS},
        {"model":"xgboost","params":{"n_estimators":400,"learning_rate":0.02,"max_depth":4,"min_child_weight":10.0,"subsample":0.7,"colsample_bytree":0.7,"reg_lambda":10.0},"feature_groups":ALL_GROUPS},
        {"model":"xgboost","params":{"n_estimators":250,"learning_rate":0.05,"max_depth":2,"min_child_weight":15.0,"subsample":0.9,"colsample_bytree":0.4,"reg_lambda":15.0},"feature_groups":["ROLLING_MEAN","LAGS","ACCELERATION","RECENCY","DERIVED_TOTALS","CALENDAR"]},
        {"model":"xgboost","params":{"n_estimators":350,"learning_rate":0.01,"max_depth":5,"min_child_weight":20.0,"subsample":0.6,"colsample_bytree":0.6,"reg_lambda":20.0},"feature_groups":ALL_GROUPS},
        {"model":"lightgbm","params":{"n_estimators":300,"learning_rate":0.03,"num_leaves":15,"min_child_samples":30,"subsample":0.8,"colsample_bytree":0.5,"reg_lambda":5.0},"feature_groups":ALL_GROUPS},
        {"model":"lightgbm","params":{"n_estimators":400,"learning_rate":0.02,"num_leaves":31,"min_child_samples":50,"subsample":0.7,"colsample_bytree":0.7,"reg_lambda":10.0},"feature_groups":ALL_GROUPS},
        {"model":"lightgbm","params":{"n_estimators":250,"learning_rate":0.05,"num_leaves":7,"min_child_samples":75,"subsample":0.9,"colsample_bytree":0.4,"reg_lambda":15.0},"feature_groups":["ROLLING_MEAN","ROLLING_DISPERSION","LAGS","RECENCY","DERIVED_TOTALS","MACHINE_IDENTITY"]},
        {"model":"lightgbm","params":{"n_estimators":400,"learning_rate":0.01,"num_leaves":63,"min_child_samples":100,"subsample":0.6,"colsample_bytree":0.6,"reg_lambda":20.0},"feature_groups":ALL_GROUPS},
        {"model":"extra_trees","params":{"n_estimators":450,"max_features":0.20,"min_samples_leaf":8,"class_weight":None},"feature_groups":ALL_GROUPS},
        {"model":"random_forest","params":{"n_estimators":300,"max_features":0.75,"min_samples_leaf":20,"class_weight":None},"feature_groups":ALL_GROUPS},
        {"model":"hist_gradient_boosting","params":{"learning_rate":0.04,"max_iter":350,"max_leaf_nodes":31,"min_samples_leaf":20,"l2_regularization":15.0},"feature_groups":ALL_GROUPS},
        {"model":"xgboost","params":{"n_estimators":400,"learning_rate":0.04,"max_depth":6,"min_child_weight":25.0,"subsample":0.75,"colsample_bytree":0.8,"reg_lambda":25.0},"feature_groups":ALL_GROUPS},
        {"model":"lightgbm","params":{"n_estimators":400,"learning_rate":0.04,"num_leaves":47,"min_child_samples":120,"subsample":0.75,"colsample_bytree":0.8,"reg_lambda":25.0},"feature_groups":ALL_GROUPS},
        {"model":"extra_trees","params":{"n_estimators":400,"max_features":0.90,"min_samples_leaf":75,"class_weight":"balanced"},"feature_groups":ALL_GROUPS},
        {"model":"random_forest","params":{"n_estimators":400,"max_features":0.90,"min_samples_leaf":75,"class_weight":"balanced_subsample"},"feature_groups":["SOURCE_CORE","ALARM_RAW","TRANSITION_RAW","DERIVED_TOTALS","ROLLING_MEAN","LAGS"]},
        {"model":"hist_gradient_boosting","params":{"learning_rate":0.10,"max_iter":150,"max_leaf_nodes":7,"min_samples_leaf":40,"l2_regularization":8.0},"feature_groups":ALL_GROUPS},
    ]
    return tuned


class CortexProposalError(Exception):
    """Carries a rejected raw payload when Cortex returned one."""
    def __init__(self, message, raw_payload=None):
        super().__init__(message)
        self.raw_payload = raw_payload


def extract_json(value):
    """Accept AI_COMPLETE text or envelope shapes and return one JSON object."""
    if isinstance(value, dict):
        if "model" in value and "params" in value:
            return value
        for key in ("structured_output", "response", "content", "text", "messages"):
            if key in value:
                return extract_json(value[key])
        return value
    if isinstance(value, list):
        if not value:
            raise ValueError("AI_COMPLETE returned an empty list")
        return extract_json(value[0])
    text = str(value)
    try:
        parsed = json.loads(text)
        if isinstance(parsed, (dict, list)):
            return extract_json(parsed)
    except Exception:
        pass
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        raise ValueError("AI_COMPLETE response contained no JSON object")
    return json.loads(match.group(0))


def propose_with_cortex(session, leaderboard, tried_configs):
    """Structured AI_COMPLETE proposal. Any failure is the caller's fallback."""
    schema = {
        "type": "json",
        "schema": {
            "type": "object",
            "properties": {
                "model": {"type": "string", "enum": sorted(ALLOWED)},
                "params": {"type": "object"},
                "feature_groups": {
                    "type": "array",
                    "items": {"type": "string", "enum": list(FEATURE_GROUP_ORDER)},
                },
                "rationale": {"type": "string"},
            },
            "required": ["model", "params", "feature_groups", "rationale"],
        },
    }
    prompt = (
        "Propose one new classifier configuration for a fixed two-fold "
        "rolling-origin search on hourly manufacturing data. Optimise mean ROC "
        "AUC first and worst-fold ROC AUC second. The period from 2021-12-01 "
        "onward is a forbidden holdout and must not be reasoned about. "
        "feature_groups selects which blocks of engineered columns the model "
        "may see; omitting a group removes those columns entirely. "
        "The configuration must differ from every configuration already tried. "
        "Allowed parameter contracts: "
        + json.dumps(ALLOWED, default=str)
        + ". Allowed feature groups: "
        + json.dumps(list(FEATURE_GROUP_ORDER))
        + ". Results so far: "
        + json.dumps(leaderboard[-8:], default=str)
        + ". Configurations already tried: "
        + json.dumps(tried_configs[-25:], default=str)
    )
    # Named arguments are used for model_parameters and response_format because
    # that is the documented AI_COMPLETE shape for structured output. The model
    # name is an inlined code constant, never user input.
    rows = session.sql(
        """SELECT SNOWFLAKE.CORTEX.AI_COMPLETE(
               'llama3.3-70b',
               ?,
               model_parameters => PARSE_JSON(?),
               response_format => PARSE_JSON(?)
           ) AS RESPONSE""",
        params=[
            prompt,
            json.dumps({"temperature": 0.3, "max_tokens": 800}),
            json.dumps(schema),
        ],
    ).collect()
    raw = rows[0][0]
    try:
        proposal = extract_json(raw)
        if not isinstance(proposal, dict):
            raise ValueError("AI_COMPLETE proposal was not an object")
        proposal = dict(proposal)
        rationale = str(
            proposal.pop("rationale", "Cortex structured proposal")
        )[:4000]
        return validate_config(proposal), rationale, raw
    except Exception as exc:
        raise CortexProposalError(
            "AI_COMPLETE payload rejected: " + str(exc), raw
        ) from exc


def make_model(config):
    p = dict(config["params"])
    name = config["model"]
    if name == "extra_trees":
        return ExtraTreesClassifier(**p, random_state=SEED, n_jobs=1)
    if name == "random_forest":
        return RandomForestClassifier(**p, random_state=SEED, n_jobs=1)
    if name == "hist_gradient_boosting":
        return HistGradientBoostingClassifier(**p, random_state=SEED)
    if name == "xgboost":
        return XGBClassifier(
            **p, random_state=SEED, n_jobs=1, objective="binary:logistic",
            eval_metric="logloss", tree_method="hist",
        )
    if name == "lightgbm":
        return LGBMClassifier(
            **p, random_state=SEED, n_jobs=1, objective="binary",
            verbosity=-1, subsample_freq=1,
        )
    raise ValueError("non-allowlisted model")


def exact_top_ten(y, score, machine, hour):
    """Exactly ceil(10% of n) rows, deterministic machine/time tie-breaking."""
    frame = pd.DataFrame({
        "score": np.asarray(score, dtype=float),
        "machine": np.asarray(machine, dtype=str),
        "hour": np.asarray(
            pd.to_datetime(pd.Series(hour).to_numpy()).astype("int64")
        ),
        "position": np.arange(len(y)),
    })
    order = frame.sort_values(
        ["score", "machine", "hour", "position"],
        ascending=[False, True, True, True],
        kind="mergesort",
    )["position"].to_numpy()
    count = max(1, int(math.ceil(len(order) * 0.10)))
    selected = order[:count]
    yy = np.asarray(y, dtype=int)
    hits = int(yy[selected].sum())
    positives = int(yy.sum())
    return {
        "top10_rows": count,
        "top10_precision": float(hits / count),
        "top10_recall": float(hits / positives) if positives else 0.0,
    }


def metric_set(y, score, machine, hour, strict=True):
    """Metrics for one scope. Single-class scopes drop AUC/AP rather than fail."""
    y = np.asarray(y, dtype=int)
    score = np.asarray(score, dtype=float)
    both_classes = len(np.unique(y)) >= 2
    if strict and not both_classes:
        raise ValueError("validation fold must contain both target classes")
    result = dict(exact_top_ten(y, score, machine, hour))
    result["auc"] = float(roc_auc_score(y, score)) if both_classes else None
    result["avg_precision"] = (
        float(average_precision_score(y, score)) if both_classes else None
    )
    predicted = (score >= 0.5).astype(int)
    result["balanced_accuracy"] = (
        float(balanced_accuracy_score(y, predicted)) if both_classes else None
    )
    return result


def package_versions():
    result = {}
    for package in (
        "snowflake-snowpark-python", "snowflake-ml-python", "scikit-learn",
        "xgboost", "lightgbm", "pandas", "numpy", "pyarrow",
    ):
        try:
            result[package] = importlib.metadata.version(package)
        except Exception:
            result[package] = "unknown"
    return result


def execute(session, sql, params=None):
    params = params or []
    placeholders = sql.count("?")
    if placeholders != len(params):
        raise ValueError(
            "bind count mismatch: sql has %s placeholders, got %s params"
            % (placeholders, len(params))
        )
    return session.sql(sql, params=params).collect()


def insert_rows(session, table, columns, rows):
    """Multi-row bound INSERT. Column names are code constants only."""
    if not rows:
        return
    group = "(" + ",".join(["?"] * len(columns)) + ")"
    sql = (
        "INSERT INTO " + table + " (" + ",".join(columns) + ") VALUES "
        + ",".join([group] * len(rows))
    )
    params = []
    for row in rows:
        if len(row) != len(columns):
            raise ValueError("row width does not match column list for " + table)
        params.extend(row)
    execute(session, sql, params)


def log_rejected_proposal(session, campaign_id, attempt_seq, slot,
                          proposal_source, config, proposal_raw, reason,
                          rationale, query_tag):
    """A refused proposal is auditable but never consumes a trial slot."""
    rejected_record = config if config is not None else {
        "rejected": True,
        "reason": reason[:4000],
    }
    rejected_hash = (
        config_hash(config) if config is not None
        else "REJECTED:" + hashlib.sha256(
            canonical(rejected_record).encode("utf-8")
        ).hexdigest()
    )
    execute(
        session,
        """INSERT INTO ML.PIADE_RESEARCH_RUN (
             RUN_ID,CAMPAIGN_ID,ATTEMPT_SEQ,PROPOSED_FOR_TRIAL,
             IS_BASELINE_CONFIG,PROPOSAL_SOURCE,MODEL_FAMILY,CONFIG_HASH,
             TRIAL_DECISION,EVALUATION_STATUS,DECISION_REASON,RATIONALE,
             STATUS,ERROR_MESSAGE,QUERY_TAG,PROPOSAL_RAW,CONFIG,
             STARTED_AT,FINISHED_AT
           ) SELECT ?,?,?,?,?,?,?,?,'REJECTED','NOT_EVALUATED',?,?,
                    'REJECTED',?,?,
                    PARSE_JSON(?),PARSE_JSON(?),CURRENT_TIMESTAMP(),
                    CURRENT_TIMESTAMP()""",
        [
            str(uuid.uuid4()), campaign_id, attempt_seq, slot, False,
            proposal_source,
            config["model"] if config else None,
            rejected_hash,
            reason[:4000], rationale[:4000], reason[:16000], query_tag,
            json.dumps(proposal_raw, default=str)
            if proposal_raw is not None else "null",
            canonical(rejected_record),
        ],
    )


def best_effort_experiment(session, campaign_id, run_id, config, summary):
    """Experiment Tracking is a mirror. Missing privileges must not fail a run."""
    try:
        from snowflake.ml.experiment import ExperimentTracking
        tracking = ExperimentTracking(session=session)
        tracking.set_experiment("PIADE_AUTORESEARCH")
        with tracking.start_run(run_name=run_id):
            tracking.log_params({
                "campaign_id": campaign_id,
                "config": canonical(config),
                "holdout_excluded": "true",
            })
            tracking.log_metrics({
                "mean_auc": summary["mean_auc"],
                "worst_auc": summary["worst_auc"],
                "mean_avg_precision": summary["mean_avg_precision"],
                "top10_precision_lift": summary["top10_precision_lift"],
            })
        return "LOGGED"
    except Exception as exc:
        return ("BEST_EFFORT_SKIPPED: " + str(exc))[:4000]


def best_effort_registry(session, campaign_id, run_id, model, sample):
    """Registry logging is research provenance only; it promotes nothing."""
    try:
        from snowflake.ml.registry import Registry
        registry = Registry(
            session=session,
            database_name=session.get_current_database().replace('"', ''),
            schema_name="ML",
        )
        version = "C_" + campaign_id.replace("-", "_")[:20]
        registry.log_model(
            model,
            model_name="PIADE_AUTORESEARCH_CHAMPION",
            version_name=version,
            sample_input_data=sample.iloc[:20],
            comment=(
                "Research champion from " + run_id
                + "; gated, not applied to any production table."
            ),
        )
        return "LOGGED_RESEARCH_ONLY:" + version
    except Exception as exc:
        return ("BEST_EFFORT_SKIPPED: " + str(exc))[:4000]


def summarise(fold_results):
    def mean_of(key):
        values = [f[key] for f in fold_results if f[key] is not None]
        return float(np.mean(values)) if values else None

    model_p = mean_of("top10_precision")
    persistence_p = mean_of("persistence_top10_precision")
    lift = (
        float(model_p - persistence_p)
        if model_p is not None and persistence_p is not None else None
    )
    aucs = [f["auc"] for f in fold_results if f["auc"] is not None]
    return {
        "mean_auc": float(np.mean(aucs)) if aucs else None,
        "worst_auc": float(np.min(aucs)) if aucs else None,
        "mean_avg_precision": mean_of("avg_precision"),
        "mean_top10_precision": model_p,
        "mean_top10_recall": mean_of("top10_recall"),
        "mean_balanced_accuracy": mean_of("balanced_accuracy"),
        "mean_persistence_auc": mean_of("persistence_auc"),
        "mean_persistence_ap": mean_of("persistence_avg_precision"),
        "mean_persistence_top10_p": persistence_p,
        "mean_persistence_top10_r": mean_of("persistence_top10_recall"),
        "top10_precision_lift": lift,
    }


def evaluate_config(session, context, config, run_id, trial_number):
    """Fit and score one config on both fixed folds. Returns summary + rows."""
    df = context["df"]
    y_all = context["y_all"]
    features = masked_features(config, context["production_features"])
    is_baseline = trial_number == 1
    fold_rows = []
    line_rows = []
    fold_results = []
    line_results = []
    trial_started = time.monotonic()

    for fold_name, val_start, val_end in context["fold_defs"]:
        # Challengers are aborted between folds after either cap. The baseline
        # is intentionally exempt so both reference folds always complete,
        # while BUDGET_EXCEEDED still records any overrun. Once a native fit has
        # started, warehouse Python cannot preempt it.
        elapsed = time.monotonic() - trial_started
        if not is_baseline and elapsed >= TRIAL_BUDGET_SECONDS:
            raise TimeoutError(
                "per-trial budget of " + str(TRIAL_BUDGET_SECONDS)
                + "s was already spent after " + str(round(elapsed, 1))
                + "s; remaining folds were not started"
            )
        if (
            not is_baseline
            and time.monotonic() - context["campaign_started"]
            >= MAX_ELAPSED_SECONDS
        ):
            raise TimeoutError("campaign elapsed-time limit reached before fold fit")

        fold_started = time.monotonic()
        train_mask = df["HOUR_TS"] < val_start
        valid_mask = (df["HOUR_TS"] >= val_start) & (df["HOUR_TS"] < val_end)
        train = df.loc[train_mask]
        valid = df.loc[valid_mask]

        model = make_model(config)
        fit_started = time.monotonic()
        model.fit(train[features], y_all.loc[train_mask])
        fit_seconds = float(time.monotonic() - fit_started)
        score = model.predict_proba(valid[features])[:, 1]
        del model

        y_valid = y_all.loc[valid_mask]
        machine = valid["MACHINE_CODE"]
        hour = valid["HOUR_TS"]
        metrics = metric_set(y_valid, score, machine, hour, strict=True)
        persistence = metric_set(
            y_valid, valid["BASELINE_SCORE"], machine, hour, strict=True
        )
        lift = float(
            metrics["top10_precision"] - persistence["top10_precision"]
        )
        fold = {
            "fold_name": fold_name,
            "train_start": ts_text(df.loc[train_mask, "HOUR_TS"].min()),
            "train_end": ts_text(val_start),
            "validation_start": ts_text(val_start),
            "validation_end": ts_text(val_end),
            "train_rows": int(train_mask.sum()),
            "validation_rows": int(valid_mask.sum()),
            "positive_rate": float(y_valid.mean()),
            "auc": metrics["auc"],
            "avg_precision": metrics["avg_precision"],
            "top10_rows": metrics["top10_rows"],
            "top10_precision": metrics["top10_precision"],
            "top10_recall": metrics["top10_recall"],
            "balanced_accuracy": metrics["balanced_accuracy"],
            "persistence_auc": persistence["auc"],
            "persistence_avg_precision": persistence["avg_precision"],
            "persistence_top10_rows": persistence["top10_rows"],
            "persistence_top10_precision": persistence["top10_precision"],
            "persistence_top10_recall": persistence["top10_recall"],
            "persistence_balanced_accuracy": persistence["balanced_accuracy"],
            "top10_precision_lift": lift,
            "fit_seconds": fit_seconds,
            "runtime_seconds": float(time.monotonic() - fold_started),
        }
        fold_results.append(fold)
        fold_rows.append([
            context["campaign_id"], run_id, trial_number, fold["fold_name"],
            fold["train_start"], fold["train_end"], fold["validation_start"],
            fold["validation_end"], fold["train_rows"], fold["validation_rows"],
            fold["positive_rate"], opt_float(fold["auc"]),
            opt_float(fold["avg_precision"]), fold["top10_rows"],
            fold["top10_precision"], fold["top10_recall"],
            opt_float(fold["balanced_accuracy"]),
            opt_float(fold["persistence_auc"]),
            opt_float(fold["persistence_avg_precision"]),
            fold["persistence_top10_rows"], fold["persistence_top10_precision"],
            fold["persistence_top10_recall"],
            opt_float(fold["persistence_balanced_accuracy"]),
            fold["top10_precision_lift"], fold["fit_seconds"],
            fold["runtime_seconds"], context["query_tag"],
        ])

        scored = pd.DataFrame({
            "MACHINE_CODE": machine.to_numpy(),
            "HOUR_TS": hour.to_numpy(),
            "Y": y_valid.to_numpy(),
            "SCORE": score,
            "PERSISTENCE": valid["BASELINE_SCORE"].to_numpy(),
        })
        for line_code, part in scored.groupby("MACHINE_CODE", sort=True):
            line_model = metric_set(
                part["Y"], part["SCORE"], part["MACHINE_CODE"], part["HOUR_TS"],
                strict=False,
            )
            line_persistence = metric_set(
                part["Y"], part["PERSISTENCE"], part["MACHINE_CODE"],
                part["HOUR_TS"], strict=False,
            )
            line_lift = float(
                line_model["top10_precision"]
                - line_persistence["top10_precision"]
            )
            beats = bool(line_lift >= -EPS)
            line_results.append({
                "fold_name": fold_name,
                "machine_code": str(line_code),
                "rows": int(len(part)),
                "top10_precision": line_model["top10_precision"],
                "persistence_top10_precision": line_persistence["top10_precision"],
                "top10_precision_lift": line_lift,
                "beats_persistence": beats,
            })
            line_rows.append([
                context["campaign_id"], run_id, trial_number, fold_name,
                str(line_code), fold["validation_start"], fold["validation_end"],
                int(len(part)), float(part["Y"].mean()),
                opt_float(line_model["auc"]), opt_float(line_model["avg_precision"]),
                line_model["top10_rows"], line_model["top10_precision"],
                line_model["top10_recall"], opt_float(line_persistence["auc"]),
                line_persistence["top10_precision"],
                line_persistence["top10_recall"], line_lift, beats,
                context["query_tag"],
            ])

    insert_rows(
        session, "ML.PIADE_RESEARCH_FOLD_METRIC",
        ["CAMPAIGN_ID", "RUN_ID", "TRIAL_NUMBER", "FOLD_NAME", "TRAIN_START",
         "TRAIN_END_EXCLUSIVE", "VALIDATION_START", "VALIDATION_END_EXCLUSIVE",
         "TRAIN_ROWS", "VALIDATION_ROWS", "POSITIVE_RATE", "AUC",
         "AVG_PRECISION", "TOP10_ROWS", "TOP10_PRECISION", "TOP10_RECALL",
         "BALANCED_ACCURACY", "PERSISTENCE_AUC", "PERSISTENCE_AVG_PRECISION",
         "PERSISTENCE_TOP10_ROWS", "PERSISTENCE_TOP10_PRECISION",
         "PERSISTENCE_TOP10_RECALL", "PERSISTENCE_BALANCED_ACCURACY",
         "TOP10_PRECISION_LIFT", "FIT_SECONDS", "RUNTIME_SECONDS", "QUERY_TAG"],
        fold_rows,
    )
    insert_rows(
        session, "ML.PIADE_RESEARCH_LINE_METRIC",
        ["CAMPAIGN_ID", "RUN_ID", "TRIAL_NUMBER", "FOLD_NAME", "MACHINE_CODE",
         "VALIDATION_START", "VALIDATION_END_EXCLUSIVE", "VALIDATION_ROWS",
         "POSITIVE_RATE", "AUC", "AVG_PRECISION", "TOP10_ROWS",
         "TOP10_PRECISION", "TOP10_RECALL", "PERSISTENCE_AUC",
         "PERSISTENCE_TOP10_PRECISION", "PERSISTENCE_TOP10_RECALL",
         "TOP10_PRECISION_LIFT", "BEATS_PERSISTENCE", "QUERY_TAG"],
        line_rows,
    )

    summary = summarise(fold_results)
    failures = sorted(
        line["fold_name"] + "|" + line["machine_code"]
        for line in line_results if not line["beats_persistence"]
    )
    summary["feature_count"] = len(features)
    summary["runtime_seconds"] = float(time.monotonic() - trial_started)
    summary["budget_exceeded"] = bool(
        summary["runtime_seconds"] > TRIAL_BUDGET_SECONDS
    )
    summary["line_persistence_failures"] = failures
    return summary, fold_results, line_results


def evaluate_gates(champion, baseline):
    """Four explicit gates. Any FALSE leaves production exactly as it was."""
    champion_failures = set(champion["line_persistence_failures"])
    baseline_failures = set(baseline["line_persistence_failures"])
    new_failures = sorted(champion_failures - baseline_failures)

    champion_lift = champion["top10_precision_lift"]
    baseline_lift = baseline["top10_precision_lift"]
    lift_known = champion_lift is not None and baseline_lift is not None

    gates = [
        {
            "order": 1,
            "name": "CHAMPION_MEAN_AUC_EXCEEDS_BASELINE",
            "rule": "champion mean validation AUC > baseline mean validation AUC",
            "champion_value": champion["mean_auc"],
            "baseline_value": baseline["mean_auc"],
            "passed": bool(
                champion["mean_auc"] is not None
                and baseline["mean_auc"] is not None
                and champion["mean_auc"] > baseline["mean_auc"] + EPS
            ),
        },
        {
            "order": 2,
            "name": "WORST_FOLD_AUC_NO_REGRESSION",
            "rule": "champion worst-fold AUC >= baseline worst-fold AUC",
            "champion_value": champion["worst_auc"],
            "baseline_value": baseline["worst_auc"],
            "passed": bool(
                champion["worst_auc"] is not None
                and baseline["worst_auc"] is not None
                and champion["worst_auc"] >= baseline["worst_auc"] - EPS
            ),
        },
        {
            "order": 3,
            "name": "TOP_DECILE_PRECISION_LIFT_NO_REGRESSION",
            "rule": (
                "champion (top-decile precision - matched persistence precision) "
                ">= same quantity for baseline"
            ),
            "champion_value": champion_lift,
            "baseline_value": baseline_lift,
            "passed": bool(
                lift_known and champion_lift >= baseline_lift - EPS
            ),
        },
        {
            "order": 4,
            "name": "NO_NEW_PER_LINE_PERSISTENCE_FAILURES",
            "rule": (
                "no machine line loses to persistence under the champion "
                "unless it already lost under the baseline"
            ),
            "champion_value": float(len(champion_failures)),
            "baseline_value": float(len(baseline_failures)),
            "passed": bool(not new_failures),
        },
    ]
    for gate in gates:
        champion_value = gate["champion_value"]
        baseline_value = gate["baseline_value"]
        gate["margin"] = (
            float(champion_value - baseline_value)
            if champion_value is not None and baseline_value is not None
            else None
        )
        if gate["name"] == "NO_NEW_PER_LINE_PERSISTENCE_FAILURES":
            gate["detail"] = (
                "new failures: " + (", ".join(new_failures) if new_failures else "none")
            )[:4000]
        elif champion_value is None or baseline_value is None:
            gate["detail"] = "undefined metric on one side; gate treated as failed"
        else:
            gate["detail"] = (
                "champion=" + format(champion_value, ".6f")
                + " baseline=" + format(baseline_value, ".6f")
            )
    return gates, new_failures


def holdout_confirmation(session, context, champion_config, run_id, features):
    """Confirm on holdout without starting post-gate work after campaign cap."""
    if time.monotonic() - context["campaign_started"] >= MAX_ELAPSED_SECONDS:
        return None, None, (
            "campaign cap reached before reused-holdout query; confirmation "
            "and registry logging were not started"
        )
    holdout = session.sql(
        """SELECT * FROM ML.PLANT_B_FEATURES
           WHERE HOUR_TS >= '2021-12-01'::TIMESTAMP_NTZ
           ORDER BY MACHINE_CODE,HOUR_TS"""
    ).to_pandas()
    if holdout.empty:
        return None, None, None
    holdout.columns = [str(c).upper() for c in holdout.columns]
    holdout["HOUR_TS"] = pd.to_datetime(holdout["HOUR_TS"])
    if holdout["HOUR_TS"].min() < HOLDOUT_START:
        raise ValueError("holdout query returned pre-holdout rows")
    holdout[features] = (
        holdout[features].replace([np.inf, -np.inf], np.nan).fillna(0)
    )

    if time.monotonic() - context["campaign_started"] >= MAX_ELAPSED_SECONDS:
        return None, None, (
            "campaign cap reached after holdout read but before champion refit; "
            "no confirmation metrics or registry model were written"
        )
    df = context["df"]
    model = make_model(champion_config)
    model.fit(df[features], context["y_all"])
    if time.monotonic() - context["campaign_started"] >= MAX_ELAPSED_SECONDS:
        return None, model, (
            "champion refit overran the 1800-second campaign cap; confirmation "
            "scoring and registry logging were blocked"
        )
    score = model.predict_proba(holdout[features])[:, 1]

    y = holdout["LABEL_HEAVY_STOP"].astype(int)
    rows = []
    fleet = None
    scopes = [("FLEET", holdout, y, score)]
    for line_code in sorted(holdout["MACHINE_CODE"].astype(str).unique()):
        mask = (holdout["MACHINE_CODE"].astype(str) == line_code).to_numpy()
        scopes.append((line_code, holdout.loc[mask], y[mask], score[mask]))

    for scope, part, y_part, score_part in scopes:
        model_metrics = metric_set(
            y_part, score_part, part["MACHINE_CODE"], part["HOUR_TS"], strict=False
        )
        persistence = metric_set(
            y_part, part["BASELINE_SCORE"], part["MACHINE_CODE"], part["HOUR_TS"],
            strict=False,
        )
        lift = float(
            model_metrics["top10_precision"] - persistence["top10_precision"]
        )
        if scope == "FLEET":
            fleet = {
                "auc": model_metrics["auc"],
                "avg_precision": model_metrics["avg_precision"],
                "top10_precision": model_metrics["top10_precision"],
                "top10_recall": model_metrics["top10_recall"],
                "top10_precision_lift": lift,
            }
        rows.append([
            context["campaign_id"], run_id, "REUSED_HOLDOUT_CONFIRMATION", scope,
            ts_text(HOLDOUT_START), ts_text(part["HOUR_TS"].max()),
            int(len(part)), float(y_part.mean()),
            opt_float(model_metrics["auc"]),
            opt_float(model_metrics["avg_precision"]),
            model_metrics["top10_rows"], model_metrics["top10_precision"],
            model_metrics["top10_recall"],
            opt_float(model_metrics["balanced_accuracy"]),
            opt_float(persistence["auc"]),
            opt_float(persistence["avg_precision"]),
            persistence["top10_precision"], persistence["top10_recall"],
            lift, False, context["query_tag"],
        ])

    insert_rows(
        session, "ML.PIADE_RESEARCH_HOLDOUT_METRIC",
        ["CAMPAIGN_ID", "RUN_ID", "EVALUATION_LABEL", "SCOPE", "HOLDOUT_START",
         "HOLDOUT_END", "HOLDOUT_ROWS", "POSITIVE_RATE", "AUC", "AVG_PRECISION",
         "TOP10_ROWS", "TOP10_PRECISION", "TOP10_RECALL", "BALANCED_ACCURACY",
         "PERSISTENCE_AUC", "PERSISTENCE_AVG_PRECISION",
         "PERSISTENCE_TOP10_PRECISION", "PERSISTENCE_TOP10_RECALL",
         "TOP10_PRECISION_LIFT", "USED_FOR_SELECTION", "QUERY_TAG"],
        rows,
    )
    return fleet, model, None


def run(session, max_trials=25):
    requested = 25 if max_trials is None else int(max_trials)
    if requested < 1:
        raise ValueError("MAX_TRIALS must be at least 1")
    trial_limit = min(requested, HARD_TRIAL_LIMIT)
    campaign_id = str(uuid.uuid4())
    query_tag = "snowcore-real|piade|autoresearch|" + campaign_id
    packages = package_versions()
    campaign_started = time.monotonic()
    baseline_config = validate_config(BASELINE)

    # ALTER SESSION does not accept bind variables, so the tag is inlined after
    # being reduced to a known-safe character set.
    safe_tag = re.sub(r"[^A-Za-z0-9|:_.\-]", "", query_tag)
    execute(session, "ALTER SESSION SET QUERY_TAG = '" + safe_tag + "'")

    execute(
        session,
        """INSERT INTO ML.PIADE_RESEARCH_CAMPAIGN (
             CAMPAIGN_ID,STARTED_AT,STATUS,REQUESTED_TRIALS,TRIAL_LIMIT,
             MAX_ELAPSED_SECONDS,TRIAL_BUDGET_SECONDS,TARGET_DEFINITION,
             VALIDATION_1_START,VALIDATION_1_END_EXCLUSIVE,VALIDATION_2_START,
             VALIDATION_2_END_EXCLUSIVE,HOLDOUT_START,BASELINE_CONFIG,
             PROMOTION_STATUS,PROMOTION_ELIGIBLE,PRODUCTION_TABLES_MODIFIED,
             QUERY_TAG,PACKAGE_VERSIONS
           ) SELECT ?,CURRENT_TIMESTAMP(),'RUNNING',?,?,?,?,?,
                    TO_TIMESTAMP_NTZ(?),TO_TIMESTAMP_NTZ(?),TO_TIMESTAMP_NTZ(?),
                    TO_TIMESTAMP_NTZ(?),TO_TIMESTAMP_NTZ(?),PARSE_JSON(?),
                    'PENDING',FALSE,FALSE,?,PARSE_JSON(?)""",
        [
            campaign_id, requested, trial_limit, MAX_ELAPSED_SECONDS,
            TRIAL_BUDGET_SECONDS, TARGET,
            ts_text(V1_START), ts_text(V1_END), ts_text(V2_START),
            ts_text(V2_END), ts_text(HOLDOUT_START), canonical(baseline_config),
            query_tag, json.dumps(packages),
        ],
    )

    try:
        # The holdout predicate is pushed into Snowflake. While any selection
        # decision is open, holdout rows are never transferred to Python and so
        # cannot influence proposals, fitting, metrics or the champion choice.
        df = session.sql(
            """SELECT * FROM ML.PLANT_B_FEATURES
               WHERE HOUR_TS < '2021-12-01'::TIMESTAMP_NTZ
               ORDER BY MACHINE_CODE,HOUR_TS"""
        ).to_pandas()
        if df.empty:
            raise ValueError("ML.PLANT_B_FEATURES has no pre-holdout rows")
        df.columns = [str(c).upper() for c in df.columns]
        df["HOUR_TS"] = pd.to_datetime(df["HOUR_TS"])
        if df["HOUR_TS"].max() >= HOLDOUT_START:
            raise ValueError("holdout guard failed before model search")

        # This is deliberately not dataframe order. It reproduces sql/15's
        # source + derived + history + extras order byte-for-byte in intent.
        production_features = production_feature_order(df)
        if masked_features(baseline_config, production_features) != production_features:
            raise ValueError(
                "Baseline feature mask changed the production feature order"
            )
        group_counts = {name: 0 for name in FEATURE_GROUP_ORDER}
        for column in production_features:
            group_counts[feature_group_of(column)] += 1
        if sum(group_counts.values()) != 299:
            raise ValueError("feature-group partition does not cover all features")

        df[production_features] = (
            df[production_features].replace([np.inf, -np.inf], np.nan).fillna(0)
        )
        y_all = df["LABEL_HEAVY_STOP"].astype(int)
        fold_defs = [
            ("VALIDATION_1", V1_START, V1_END),
            ("VALIDATION_2", V2_START, V2_END),
        ]
        for _, val_start, val_end in fold_defs:
            if df[df["HOUR_TS"] < val_start].empty:
                raise ValueError("rolling-origin training partition is empty")
            if df[(df["HOUR_TS"] >= val_start) & (df["HOUR_TS"] < val_end)].empty:
                raise ValueError("fixed validation partition is empty")

        context = {
            "df": df,
            "y_all": y_all,
            "production_features": production_features,
            "fold_defs": fold_defs,
            "campaign_id": campaign_id,
            "query_tag": query_tag,
            "campaign_started": campaign_started,
        }

        execute(
            session,
            """UPDATE ML.PIADE_RESEARCH_CAMPAIGN
               SET SEARCH_MAX_HOUR_TS=TO_TIMESTAMP_NTZ(?)
               WHERE CAMPAIGN_ID=?""",
            [ts_text(df["HOUR_TS"].max()), campaign_id],
        )

        run_columns = [
            "RUN_ID", "CAMPAIGN_ID", "ATTEMPT_SEQ", "TRIAL_NUMBER",
            "PROPOSED_FOR_TRIAL", "IS_BASELINE_CONFIG", "PROPOSAL_SOURCE",
            "MODEL_FAMILY", "CONFIG_HASH", "FEATURE_COUNT", "RATIONALE",
            "TRIAL_DECISION", "EVALUATION_STATUS", "DECISION_REASON",
            "STATUS", "TRIAL_BUDGET_SECONDS", "QUERY_TAG",
        ]
        run_insert_sql = (
            "INSERT INTO ML.PIADE_RESEARCH_RUN ("
            + ",".join(run_columns)
            + ",PROPOSAL_RAW,CONFIG,FEATURE_GROUPS,PACKAGE_VERSIONS,STARTED_AT"
            + ") SELECT " + ",".join(["?"] * len(run_columns))
            + ",PARSE_JSON(?),PARSE_JSON(?),PARSE_JSON(?),PARSE_JSON(?),"
            + "CURRENT_TIMESTAMP()"
        )

        candidates = deterministic_candidates()
        fallback_position = 0
        tried_hashes = set()
        tried_configs = []
        leaderboard = []
        baseline_summary = None
        baseline_run_id = None
        attempt_seq = 0
        trial_number = 0
        rejected = 0
        crashed = 0
        stop_reason = "TRIAL_LIMIT_REACHED"
        max_attempts = trial_limit * 3
        cortex_enabled = True

        while trial_number < trial_limit and attempt_seq < max_attempts:
            # Trial 1 is the mandatory two-fold baseline. It is allowed to
            # finish even if setup or its first fold consumed the campaign cap.
            if (
                trial_number > 0
                and time.monotonic() - campaign_started >= MAX_ELAPSED_SECONDS
            ):
                stop_reason = "ELAPSED_TIME_LIMIT_REACHED"
                break
            slot = trial_number + 1
            proposal_raw = None
            config = None

            if trial_number == 0:
                config = baseline_config
                rationale = (
                    "Fixed baseline: the ExtraTrees configuration currently used "
                    "by sql/15_plant_b_risk.sql, on the full feature set."
                )
                proposal_source = "FIXED_BASELINE"
            else:
                cortex_error = None
                if cortex_enabled:
                    try:
                        config, rationale, proposal_raw = propose_with_cortex(
                            session, leaderboard, tried_configs
                        )
                        masked_features(config, production_features)
                        if config_hash(config) in tried_hashes:
                            cortex_error = (
                                "Cortex proposed a configuration already tried"
                            )
                    except Exception as cortex_exc:
                        if isinstance(cortex_exc, CortexProposalError):
                            proposal_raw = cortex_exc.raw_payload
                        cortex_error = (
                            "Cortex proposal unusable: " + str(cortex_exc)
                        )
                    proposal_source = "CORTEX_AI_COMPLETE"
                else:
                    cortex_error = "Cortex disabled after its first failure"
                    proposal_source = "DETERMINISTIC_FALLBACK"

                if cortex_error is not None and cortex_enabled:
                    attempt_seq += 1
                    rejected += 1
                    log_rejected_proposal(
                        session, campaign_id, attempt_seq, slot,
                        proposal_source, config, proposal_raw, cortex_error,
                        cortex_error, query_tag,
                    )
                    # One failure is enough. Remaining slots use deterministic
                    # candidates and never spend more time or credits on Cortex.
                    cortex_enabled = False

                if cortex_error is not None:
                    config = None
                    proposal_raw = None
                    proposal_source = "DETERMINISTIC_FALLBACK"
                    rationale = (
                        "Deterministic fallback after: " + cortex_error
                    )[:4000]
                    while fallback_position < len(candidates):
                        try:
                            candidate = validate_config(
                                candidates[fallback_position]
                            )
                            masked_features(candidate, production_features)
                        except Exception:
                            fallback_position += 1
                            continue
                        fallback_position += 1
                        if config_hash(candidate) not in tried_hashes:
                            config = candidate
                            break
                    if config is None:
                        attempt_seq += 1
                        rejected += 1
                        log_rejected_proposal(
                            session, campaign_id, attempt_seq, slot,
                            proposal_source, None, None,
                            "no unique allowlisted fallback remained",
                            rationale, query_tag,
                        )
                        stop_reason = "NO_UNIQUE_ALLOWLISTED_CONFIGS"
                        break

            attempt_seq += 1
            digest = config_hash(config)
            tried_hashes.add(digest)
            tried_configs.append(canonical(config))
            trial_number += 1
            is_baseline = trial_number == 1
            run_id = str(uuid.uuid4())

            execute(
                session, run_insert_sql,
                [
                    run_id, campaign_id, attempt_seq, trial_number, slot,
                    is_baseline, proposal_source, config["model"], digest,
                    len(masked_features(config, production_features)),
                    rationale[:4000],
                    "IN_PROGRESS", "RUNNING", "evaluation not finished",
                    "RUNNING", TRIAL_BUDGET_SECONDS, query_tag,
                    json.dumps(proposal_raw, default=str)
                    if proposal_raw is not None else "null",
                    canonical(config), canonical(config["feature_groups"]),
                    json.dumps(packages),
                ],
            )

            run_started = time.monotonic()
            try:
                summary, fold_results, line_results = evaluate_config(
                    session, context, config, run_id, trial_number
                )
                incumbent = max(
                    (entry["mean_auc"] for entry in leaderboard
                     if entry["eligible"] and entry["mean_auc"] is not None),
                    default=None,
                )
                if is_baseline:
                    decision = "BASELINE"
                    reason = "fixed reference configuration; never a candidate"
                    if summary["budget_exceeded"]:
                        reason += (
                            "; it also ran " + str(round(summary["runtime_seconds"], 1))
                            + "s, past the " + str(TRIAL_BUDGET_SECONDS)
                            + "s budget, which the gates do not penalise because "
                            "the reference must always be measured"
                        )
                    eligible = False
                elif summary["budget_exceeded"]:
                    decision = "DISCARD"
                    reason = (
                        "evaluated in " + str(round(summary["runtime_seconds"], 1))
                        + "s, over the " + str(TRIAL_BUDGET_SECONDS)
                        + "s per-trial budget, so it is not promotable"
                    )
                    eligible = False
                elif incumbent is None or summary["mean_auc"] > incumbent + EPS:
                    decision = "KEEP"
                    reason = (
                        "new best candidate mean validation AUC "
                        + format(summary["mean_auc"], ".6f")
                    )
                    eligible = True
                else:
                    decision = "DISCARD"
                    reason = (
                        "mean validation AUC " + format(summary["mean_auc"], ".6f")
                        + " did not beat the incumbent "
                        + format(incumbent, ".6f")
                    )
                    eligible = True

                experiment_status = best_effort_experiment(
                    session, campaign_id, run_id, config, summary
                )
                execute(
                    session,
                    """UPDATE ML.PIADE_RESEARCH_RUN SET
                         TRIAL_DECISION=?,EVALUATION_STATUS='COMPLETED',
                         STATUS='COMPLETED',
                         DECISION_REASON=?,FINISHED_AT=CURRENT_TIMESTAMP(),
                         RUNTIME_SECONDS=?,BUDGET_EXCEEDED=?,MEAN_AUC=?,
                         WORST_AUC=?,MEAN_AVG_PRECISION=?,MEAN_TOP10_PRECISION=?,
                         MEAN_TOP10_RECALL=?,MEAN_BALANCED_ACCURACY=?,
                         MEAN_PERSISTENCE_AUC=?,MEAN_PERSISTENCE_AP=?,
                         MEAN_PERSISTENCE_TOP10_P=?,MEAN_PERSISTENCE_TOP10_R=?,
                         TOP10_PRECISION_LIFT=?,LINE_PERSISTENCE_FAILURES=?,
                         FOLD_METRICS=PARSE_JSON(?),LINE_METRICS=PARSE_JSON(?),
                         EXPERIMENT_TRACKING_STATUS=?
                       WHERE RUN_ID=?""",
                    [
                        decision, reason[:4000], summary["runtime_seconds"],
                        summary["budget_exceeded"], opt_float(summary["mean_auc"]),
                        opt_float(summary["worst_auc"]),
                        opt_float(summary["mean_avg_precision"]),
                        opt_float(summary["mean_top10_precision"]),
                        opt_float(summary["mean_top10_recall"]),
                        opt_float(summary["mean_balanced_accuracy"]),
                        opt_float(summary["mean_persistence_auc"]),
                        opt_float(summary["mean_persistence_ap"]),
                        opt_float(summary["mean_persistence_top10_p"]),
                        opt_float(summary["mean_persistence_top10_r"]),
                        opt_float(summary["top10_precision_lift"]),
                        len(summary["line_persistence_failures"]),
                        json.dumps(fold_results, default=str),
                        json.dumps(line_results, default=str),
                        experiment_status, run_id,
                    ],
                )

                entry = dict(summary)
                entry["run_id"] = run_id
                entry["trial_number"] = trial_number
                entry["config"] = config
                entry["decision"] = decision
                entry["eligible"] = eligible
                leaderboard.append(entry)
                if is_baseline:
                    baseline_summary = entry
                    baseline_run_id = run_id
            except Exception as trial_exc:
                crashed += 1
                execute(
                    session,
                    """UPDATE ML.PIADE_RESEARCH_RUN SET
                         TRIAL_DECISION='CRASH',EVALUATION_STATUS='FAILED',
                         STATUS='FAILED',
                         DECISION_REASON=?,FINISHED_AT=CURRENT_TIMESTAMP(),
                         RUNTIME_SECONDS=?,ERROR_MESSAGE=?
                       WHERE RUN_ID=?""",
                    [
                        (
                            "evaluation did not complete ("
                            + type(trial_exc).__name__ + "): " + str(trial_exc)
                        )[:4000],
                        float(time.monotonic() - run_started),
                        (str(trial_exc) + "\n" + traceback.format_exc())[:16000],
                        run_id,
                    ],
                )

        if (
            trial_number < trial_limit
            and attempt_seq >= max_attempts
            and stop_reason == "TRIAL_LIMIT_REACHED"
        ):
            stop_reason = "PROPOSAL_ATTEMPT_LIMIT_REACHED"

        if baseline_summary is None:
            raise ValueError(
                "The baseline trial did not complete; without it no gate can be "
                "evaluated and nothing may be promoted."
            )

        candidates_evaluated = [e for e in leaderboard if e["eligible"]]
        promotion_reasons = []
        gates = []
        champion = None
        registry_status = "NOT_ATTEMPTED"
        holdout_fleet = None
        holdout_done = False

        if not candidates_evaluated:
            promotion_status = "NO_CANDIDATE"
            promotion_eligible = False
            promotion_reasons.append(
                "no candidate configuration completed inside the per-trial budget"
            )
        else:
            # Selection: mean AUC, then worst-fold AUC. Later keys are
            # deterministic tie-breakers, never holdout-derived.
            champion = sorted(
                candidates_evaluated,
                key=lambda r: (
                    -(r["mean_auc"] if r["mean_auc"] is not None else -1.0),
                    -(r["worst_auc"] if r["worst_auc"] is not None else -1.0),
                    -(r["mean_avg_precision"]
                      if r["mean_avg_precision"] is not None else -1.0),
                    r["trial_number"],
                ),
            )[0]
            gates, new_failures = evaluate_gates(champion, baseline_summary)
            insert_rows(
                session, "ML.PIADE_RESEARCH_PROMOTION_GATE",
                ["CAMPAIGN_ID", "GATE_ORDER", "GATE_NAME", "GATE_RULE", "PASSED",
                 "CHAMPION_VALUE", "BASELINE_VALUE", "MARGIN", "DETAIL"],
                [[
                    campaign_id, gate["order"], gate["name"], gate["rule"],
                    gate["passed"], opt_float(gate["champion_value"]),
                    opt_float(gate["baseline_value"]), opt_float(gate["margin"]),
                    gate["detail"],
                ] for gate in gates],
            )
            failed = [gate for gate in gates if not gate["passed"]]
            promotion_eligible = not failed
            if failed:
                promotion_status = "BLOCKED_BY_GATES"
                for gate in failed:
                    promotion_reasons.append(gate["name"] + ": " + gate["detail"])
            else:
                promotion_status = "PROMOTION_ELIGIBLE"
                promotion_reasons.append(
                    "all four promotion gates passed on validation data only"
                )

        champion_features = (
            masked_features(champion["config"], production_features)
            if champion else []
        )

        if champion is not None and promotion_eligible:
            # Only now may the reused holdout be touched. The 1800-second cap is
            # checked before the query, again before refit, and before registry.
            if time.monotonic() - campaign_started >= MAX_ELAPSED_SECONDS:
                confirmation_block = (
                    "1800-second campaign cap reached before reused-holdout "
                    "confirmation; holdout refit and registry were not started"
                )
                holdout_fleet, refit_model = None, None
            else:
                holdout_fleet, refit_model, confirmation_block = (
                    holdout_confirmation(
                        session, context, champion["config"],
                        champion["run_id"], champion_features,
                    )
                )
            holdout_done = holdout_fleet is not None
            if confirmation_block is not None:
                promotion_status = "BLOCKED_CONFIRMATION_TIMEOUT"
                promotion_eligible = False
                promotion_reasons.append(confirmation_block)
                registry_status = "SKIPPED_CAMPAIGN_CAP"
            elif not holdout_done:
                promotion_status = "BLOCKED_CONFIRMATION_MISSING"
                promotion_eligible = False
                promotion_reasons.append(
                    "gates passed but the holdout window returned no rows; "
                    "confirmation could not be produced"
                )
            if refit_model is not None:
                if (
                    time.monotonic() - campaign_started
                    >= MAX_ELAPSED_SECONDS
                ):
                    promotion_status = "BLOCKED_CONFIRMATION_TIMEOUT"
                    promotion_eligible = False
                    promotion_reasons.append(
                        "1800-second campaign cap reached before registry "
                        "logging; registry operation was not started"
                    )
                    registry_status = "SKIPPED_CAMPAIGN_CAP"
                else:
                    registry_status = best_effort_registry(
                        session, campaign_id, champion["run_id"], refit_model,
                        df.loc[
                            df["HOUR_TS"] < V2_START, champion_features
                        ],
                    )
                del refit_model
        elif champion is not None:
            registry_status = "SKIPPED_GATES_FAILED"
            promotion_reasons.append(
                "production left untouched; no holdout evaluation was performed"
            )

        contract_id = str(uuid.uuid4())
        feature_list_hash = hashlib.sha256(
            canonical(champion_features).encode("utf-8")
        ).hexdigest() if champion_features else None
        execute(
            session,
            """INSERT INTO ML.PIADE_CHAMPION_CONTRACT (
                 CONTRACT_ID,CAMPAIGN_ID,CREATED_AT,PROMOTION_STATUS,
                 PROMOTION_ELIGIBLE,PROMOTION_REASONS,APPLIED_TO_PRODUCTION,
                 CHAMPION_RUN_ID,MODEL_FAMILY,CONFIG,CONFIG_HASH,FEATURE_GROUPS,
                 FEATURE_LIST,FEATURE_COUNT,FEATURE_LIST_HASH,RANDOM_SEED,
                 SOURCE_TABLE,TRAIN_END_EXCLUSIVE,TARGET_DEFINITION,
                 VALIDATION_MEAN_AUC,VALIDATION_WORST_AUC,
                 VALIDATION_PRECISION_LIFT,BASELINE_MEAN_AUC,BASELINE_WORST_AUC,
                 BASELINE_PRECISION_LIFT,HOLDOUT_AUC,HOLDOUT_AVG_PRECISION,
                 HOLDOUT_TOP10_PRECISION,HOLDOUT_TOP10_RECALL,NOTES
               ) SELECT ?,?,CURRENT_TIMESTAMP(),?,?,PARSE_JSON(?),FALSE,?,?,
                        PARSE_JSON(?),?,PARSE_JSON(?),PARSE_JSON(?),?,?,?,?,
                        TO_TIMESTAMP_NTZ(?),?,
                        TRY_TO_DOUBLE(?),TRY_TO_DOUBLE(?),TRY_TO_DOUBLE(?),
                        TRY_TO_DOUBLE(?),TRY_TO_DOUBLE(?),TRY_TO_DOUBLE(?),
                        TRY_TO_DOUBLE(?),TRY_TO_DOUBLE(?),TRY_TO_DOUBLE(?),
                        TRY_TO_DOUBLE(?),?""",
            [
                contract_id, campaign_id, promotion_status, promotion_eligible,
                json.dumps(promotion_reasons),
                champion["run_id"] if champion else None,
                champion["config"]["model"] if champion else None,
                canonical(champion["config"]) if champion else "null",
                config_hash(champion["config"]) if champion else None,
                canonical(champion["config"]["feature_groups"])
                if champion else "null",
                canonical(champion_features) if champion_features else "null",
                len(champion_features) if champion_features else None,
                feature_list_hash, SEED, SOURCE_TABLE, ts_text(HOLDOUT_START),
                TARGET,
                opt_float(champion["mean_auc"]) if champion else None,
                opt_float(champion["worst_auc"]) if champion else None,
                opt_float(champion["top10_precision_lift"]) if champion else None,
                opt_float(baseline_summary["mean_auc"]),
                opt_float(baseline_summary["worst_auc"]),
                opt_float(baseline_summary["top10_precision_lift"]),
                opt_float(holdout_fleet["auc"]) if holdout_fleet else None,
                opt_float(holdout_fleet["avg_precision"]) if holdout_fleet else None,
                opt_float(holdout_fleet["top10_precision"]) if holdout_fleet else None,
                opt_float(holdout_fleet["top10_recall"]) if holdout_fleet else None,
                (
                    "Refit contract for sql/15_plant_b_risk.sql. Fit "
                    + SOURCE_TABLE + " rows before " + ts_text(HOLDOUT_START)
                    + " with this config, seed and feature list. Promotion is "
                    "not applied by sql/20."
                ),
            ],
        )

        experiment_values = execute(
            session,
            """SELECT LISTAGG(DISTINCT EXPERIMENT_TRACKING_STATUS,'; ') AS S
               FROM ML.PIADE_RESEARCH_RUN
               WHERE CAMPAIGN_ID=? AND EXPERIMENT_TRACKING_STATUS IS NOT NULL""",
            [campaign_id],
        )
        experiment_summary = (
            experiment_values[0][0] if experiment_values else None
        )
        execute(
            session,
            """UPDATE ML.PIADE_RESEARCH_CAMPAIGN SET
                 FINISHED_AT=CURRENT_TIMESTAMP(),STATUS='COMPLETED',
                 EVALUATED_TRIALS=?,REJECTED_PROPOSALS=?,CRASHED_TRIALS=?,
                 STOP_REASON=?,BASELINE_RUN_ID=?,
                 BASELINE_MEAN_AUC=TRY_TO_DOUBLE(?),
                 BASELINE_WORST_AUC=TRY_TO_DOUBLE(?),
                 BASELINE_PRECISION_LIFT=TRY_TO_DOUBLE(?),
                 CHAMPION_RUN_ID=?,CHAMPION_CONFIG=PARSE_JSON(?),
                 CHAMPION_MEAN_AUC=TRY_TO_DOUBLE(?),
                 CHAMPION_WORST_AUC=TRY_TO_DOUBLE(?),
                 CHAMPION_PRECISION_LIFT=TRY_TO_DOUBLE(?),
                 GATES_EVALUATED=?,GATES_PASSED=?,
                 PROMOTION_STATUS=?,PROMOTION_ELIGIBLE=?,
                 PROMOTION_REASONS=PARSE_JSON(?),HOLDOUT_EVALUATED=?,
                 HOLDOUT_AUC=TRY_TO_DOUBLE(?),
                 HOLDOUT_TOP10_PRECISION=TRY_TO_DOUBLE(?),
                 PRODUCTION_TABLES_MODIFIED=FALSE,
                 EXPERIMENT_TRACKING_STATUS=?,REGISTRY_STATUS=?
               WHERE CAMPAIGN_ID=?""",
            [
                len(leaderboard), rejected, crashed, stop_reason,
                baseline_run_id, opt_float(baseline_summary["mean_auc"]),
                opt_float(baseline_summary["worst_auc"]),
                opt_float(baseline_summary["top10_precision_lift"]),
                champion["run_id"] if champion else None,
                canonical(champion["config"]) if champion else "null",
                opt_float(champion["mean_auc"]) if champion else None,
                opt_float(champion["worst_auc"]) if champion else None,
                opt_float(champion["top10_precision_lift"]) if champion else None,
                len(gates), sum(1 for gate in gates if gate["passed"]),
                promotion_status, promotion_eligible,
                json.dumps(promotion_reasons), holdout_done,
                opt_float(holdout_fleet["auc"]) if holdout_fleet else None,
                opt_float(holdout_fleet["top10_precision"]) if holdout_fleet else None,
                experiment_summary, registry_status, campaign_id,
            ],
        )
        return {
            "campaign_id": campaign_id,
            "status": "COMPLETED",
            "requested_trials": requested,
            "hard_capped_trials": trial_limit,
            "evaluated_trials": len(leaderboard),
            "rejected_proposals": rejected,
            "crashed_trials": crashed,
            "stop_reason": stop_reason,
            "champion_run_id": champion["run_id"] if champion else None,
            "champion_config": champion["config"] if champion else None,
            "gates": [
                {"name": gate["name"], "passed": gate["passed"],
                 "detail": gate["detail"]}
                for gate in gates
            ],
            "promotion_status": promotion_status,
            "promotion_eligible": promotion_eligible,
            "promotion_reasons": promotion_reasons,
            "champion_contract_id": contract_id,
            "holdout_evaluated": holdout_done,
            "holdout_used_for_selection": False,
            "production_tables_modified": False,
            "registry_status": registry_status,
        }
    except Exception as campaign_exc:
        execute(
            session,
            """UPDATE ML.PIADE_RESEARCH_CAMPAIGN SET
                 FINISHED_AT=CURRENT_TIMESTAMP(),STATUS='FAILED',
                 STOP_REASON='ERROR',PROMOTION_STATUS='BLOCKED_BY_ERROR',
                 PROMOTION_ELIGIBLE=FALSE,PRODUCTION_TABLES_MODIFIED=FALSE,
                 ERROR_MESSAGE=?
               WHERE CAMPAIGN_ID=?""",
            [
                (str(campaign_exc) + "\n" + traceback.format_exc())[:16000],
                campaign_id,
            ],
        )
        raise
$$;

/* --------------------------------------------------------------------------
   Display-ready views for Streamlit.
   -------------------------------------------------------------------------- */

CREATE OR REPLACE VIEW ML.V_PIADE_RESEARCH_TRIALS AS
SELECT
  c.CAMPAIGN_ID,
  c.STARTED_AT AS CAMPAIGN_STARTED_AT,
  c.FINISHED_AT AS CAMPAIGN_FINISHED_AT,
  c.STATUS AS CAMPAIGN_STATUS,
  c.STOP_REASON,
  c.HOLDOUT_START,
  c.SEARCH_MAX_HOUR_TS,
  c.PROMOTION_STATUS,
  c.PROMOTION_ELIGIBLE,
  ARRAY_TO_STRING(TO_ARRAY(c.PROMOTION_REASONS),' | ') AS PROMOTION_REASONS,
  r.ATTEMPT_SEQ,
  r.TRIAL_NUMBER,
  r.PROPOSED_FOR_TRIAL,
  r.RUN_ID,
  r.TRIAL_DECISION,
  r.EVALUATION_STATUS,
  r.DECISION_REASON,
  r.IS_BASELINE_CONFIG,
  r.PROPOSAL_SOURCE,
  COALESCE(r.MODEL_FAMILY,'n/a') AS MODEL_FAMILY,
  TO_JSON(r.CONFIG) AS CONFIG_JSON,
  TRY_TO_NUMBER(r.CONFIG:params:n_estimators::VARCHAR)::INTEGER AS N_ESTIMATORS,
  TRY_TO_DOUBLE(r.CONFIG:params:max_features::VARCHAR) AS MAX_FEATURES,
  TRY_TO_NUMBER(r.CONFIG:params:min_samples_leaf::VARCHAR)::INTEGER
    AS MIN_SAMPLES_LEAF,
  r.CONFIG:params:class_weight::VARCHAR AS CLASS_WEIGHT,
  TRY_TO_DOUBLE(r.CONFIG:params:learning_rate::VARCHAR) AS LEARNING_RATE,
  TRY_TO_NUMBER(r.CONFIG:params:max_iter::VARCHAR)::INTEGER AS MAX_ITER,
  TRY_TO_NUMBER(r.CONFIG:params:max_leaf_nodes::VARCHAR)::INTEGER
    AS MAX_LEAF_NODES,
  TRY_TO_DOUBLE(r.CONFIG:params:l2_regularization::VARCHAR)
    AS L2_REGULARIZATION,
  TRY_TO_NUMBER(r.CONFIG:params:max_depth::VARCHAR)::INTEGER AS MAX_DEPTH,
  TRY_TO_DOUBLE(r.CONFIG:params:min_child_weight::VARCHAR)
    AS MIN_CHILD_WEIGHT,
  TRY_TO_DOUBLE(r.CONFIG:params:subsample::VARCHAR) AS SUBSAMPLE,
  TRY_TO_DOUBLE(r.CONFIG:params:colsample_bytree::VARCHAR) AS COLSAMPLE_BYTREE,
  TRY_TO_DOUBLE(r.CONFIG:params:reg_lambda::VARCHAR) AS REG_LAMBDA,
  TRY_TO_NUMBER(r.CONFIG:params:num_leaves::VARCHAR)::INTEGER AS NUM_LEAVES,
  TRY_TO_NUMBER(r.CONFIG:params:min_child_samples::VARCHAR)::INTEGER
    AS MIN_CHILD_SAMPLES,
  ARRAY_TO_STRING(TO_ARRAY(r.FEATURE_GROUPS),', ') AS FEATURE_GROUPS,
  r.FEATURE_COUNT,
  r.CONFIG_HASH,
  r.RATIONALE,
  r.STARTED_AT AS RUN_STARTED_AT,
  r.FINISHED_AT AS RUN_FINISHED_AT,
  r.RUNTIME_SECONDS,
  r.TRIAL_BUDGET_SECONDS,
  r.BUDGET_EXCEEDED,
  r.MEAN_AUC,
  r.WORST_AUC,
  r.MEAN_AVG_PRECISION,
  r.MEAN_TOP10_PRECISION,
  r.MEAN_TOP10_RECALL,
  r.MEAN_BALANCED_ACCURACY,
  r.MEAN_PERSISTENCE_AUC,
  r.MEAN_PERSISTENCE_AP,
  r.MEAN_PERSISTENCE_TOP10_P,
  r.MEAN_PERSISTENCE_TOP10_R,
  r.TOP10_PRECISION_LIFT,
  r.MEAN_AUC - c.BASELINE_MEAN_AUC AS MEAN_AUC_VS_BASELINE,
  r.TOP10_PRECISION_LIFT - c.BASELINE_PRECISION_LIFT AS PRECISION_LIFT_VS_BASELINE,
  r.LINE_PERSISTENCE_FAILURES,
  r.FOLD_METRICS,
  r.LINE_METRICS,
  TO_JSON(r.PROPOSAL_RAW) AS PROPOSAL_RAW_JSON,
  r.EXPERIMENT_TRACKING_STATUS,
  r.ERROR_MESSAGE,
  IFF(r.RUN_ID=c.CHAMPION_RUN_ID,TRUE,FALSE) AS IS_CHAMPION,
  r.QUERY_TAG,
  r.PACKAGE_VERSIONS
FROM ML.PIADE_RESEARCH_CAMPAIGN c
JOIN ML.PIADE_RESEARCH_RUN r USING (CAMPAIGN_ID);

CREATE OR REPLACE VIEW ML.V_PIADE_RESEARCH_CHAMPION AS
WITH gates AS (
  SELECT CAMPAIGN_ID,
         COUNT(*) AS GATE_COUNT,
         COUNT_IF(PASSED) AS GATES_PASSED,
         /* LISTAGG skips NULL, so the failure list contains only failures. */
         LISTAGG(GATE_NAME || '=' || IFF(PASSED,'PASS','FAIL'),' | ')
           WITHIN GROUP (ORDER BY GATE_ORDER) AS GATE_SUMMARY,
         LISTAGG(IFF(PASSED,NULL,GATE_NAME || ': ' || DETAIL),' | ')
           WITHIN GROUP (ORDER BY GATE_ORDER) AS GATE_FAILURE_DETAIL
  FROM ML.PIADE_RESEARCH_PROMOTION_GATE
  GROUP BY CAMPAIGN_ID
),
holdout AS (
  SELECT CAMPAIGN_ID,AUC,AVG_PRECISION,TOP10_PRECISION,TOP10_RECALL,
         PERSISTENCE_AUC,PERSISTENCE_TOP10_PRECISION,TOP10_PRECISION_LIFT,
         HOLDOUT_ROWS,HOLDOUT_END,USED_FOR_SELECTION
  FROM ML.PIADE_RESEARCH_HOLDOUT_METRIC
  WHERE SCOPE='FLEET' AND EVALUATION_LABEL='REUSED_HOLDOUT_CONFIRMATION'
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY CAMPAIGN_ID ORDER BY CREATED_AT DESC,RUN_ID DESC
  )=1
),
contract AS (
  SELECT *
  FROM ML.PIADE_CHAMPION_CONTRACT
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY CAMPAIGN_ID ORDER BY CREATED_AT DESC,CONTRACT_ID DESC
  )=1
)
SELECT
  c.CAMPAIGN_ID,
  c.STARTED_AT,
  c.FINISHED_AT,
  c.STATUS AS CAMPAIGN_STATUS,
  c.STOP_REASON,
  c.EVALUATED_TRIALS,
  c.REJECTED_PROPOSALS,
  c.CRASHED_TRIALS,
  c.TARGET_DEFINITION,
  c.VALIDATION_1_START,
  c.VALIDATION_1_END_EXCLUSIVE,
  c.VALIDATION_2_START,
  c.VALIDATION_2_END_EXCLUSIVE,
  c.HOLDOUT_START,
  c.SEARCH_MAX_HOUR_TS,
  c.CHAMPION_RUN_ID,
  COALESCE(r.MODEL_FAMILY,'n/a') AS MODEL_FAMILY,
  TO_JSON(c.CHAMPION_CONFIG) AS CONFIG_JSON,
  ARRAY_TO_STRING(TO_ARRAY(r.FEATURE_GROUPS),', ') AS FEATURE_GROUPS,
  r.FEATURE_COUNT,
  r.TRIAL_DECISION,
  r.EVALUATION_STATUS,
  c.CHAMPION_MEAN_AUC,
  c.CHAMPION_WORST_AUC,
  c.BASELINE_MEAN_AUC,
  c.BASELINE_WORST_AUC,
  c.CHAMPION_MEAN_AUC - c.BASELINE_MEAN_AUC AS MEAN_AUC_VS_BASELINE,
  c.CHAMPION_PRECISION_LIFT,
  c.BASELINE_PRECISION_LIFT,
  c.CHAMPION_PRECISION_LIFT - c.BASELINE_PRECISION_LIFT AS PRECISION_LIFT_VS_BASELINE,
  r.MEAN_AVG_PRECISION,
  r.MEAN_TOP10_PRECISION,
  r.MEAN_TOP10_RECALL,
  r.MEAN_BALANCED_ACCURACY,
  r.MEAN_PERSISTENCE_TOP10_P,
  r.LINE_PERSISTENCE_FAILURES,
  r.RUNTIME_SECONDS,
  r.RATIONALE,
  c.PROMOTION_STATUS,
  c.PROMOTION_ELIGIBLE,
  ARRAY_TO_STRING(TO_ARRAY(c.PROMOTION_REASONS),' | ') AS PROMOTION_REASONS,
  g.GATE_COUNT,
  g.GATES_PASSED,
  g.GATE_SUMMARY,
  g.GATE_FAILURE_DETAIL,
  c.HOLDOUT_EVALUATED,
  h.HOLDOUT_ROWS AS REUSED_HOLDOUT_ROWS,
  h.HOLDOUT_END AS REUSED_HOLDOUT_END,
  h.AUC AS REUSED_HOLDOUT_AUC,
  h.AVG_PRECISION AS REUSED_HOLDOUT_AVG_PRECISION,
  h.TOP10_PRECISION AS REUSED_HOLDOUT_TOP10_PRECISION,
  h.TOP10_RECALL AS REUSED_HOLDOUT_TOP10_RECALL,
  h.PERSISTENCE_AUC AS REUSED_HOLDOUT_PERSISTENCE_AUC,
  h.PERSISTENCE_TOP10_PRECISION AS REUSED_HOLDOUT_PERSISTENCE_TOP10_PRECISION,
  h.TOP10_PRECISION_LIFT AS REUSED_HOLDOUT_PRECISION_LIFT,
  COALESCE(h.USED_FOR_SELECTION,FALSE) AS REUSED_HOLDOUT_USED_FOR_SELECTION,
  c.PRODUCTION_TABLES_MODIFIED,
  k.CONTRACT_ID AS CHAMPION_CONTRACT_ID,
  k.APPLIED_TO_PRODUCTION AS CONTRACT_APPLIED_TO_PRODUCTION,
  c.EXPERIMENT_TRACKING_STATUS,
  c.REGISTRY_STATUS,
  c.QUERY_TAG,
  c.PACKAGE_VERSIONS
FROM ML.PIADE_RESEARCH_CAMPAIGN c
LEFT JOIN ML.PIADE_RESEARCH_RUN r ON r.RUN_ID=c.CHAMPION_RUN_ID
LEFT JOIN gates g ON g.CAMPAIGN_ID=c.CAMPAIGN_ID
LEFT JOIN holdout h ON h.CAMPAIGN_ID=c.CAMPAIGN_ID
LEFT JOIN contract k ON k.CAMPAIGN_ID=c.CAMPAIGN_ID;

/* ==========================================================================
   Verification queries. Run after CALL ML.RUN_PIADE_AUTORESEARCH();
   Every violation count below must be zero.
   ========================================================================== */

-- 1. No holdout row influenced selection. Search data, every validation fold
--    and every per-line fold row stay strictly before the holdout start, and
--    holdout confirmation rows exist only for campaigns that already passed
--    all gates.
SELECT
  c.CAMPAIGN_ID,
  c.HOLDOUT_START,
  c.SEARCH_MAX_HOUR_TS,
  MAX(f.VALIDATION_END_EXCLUSIVE) AS MAX_SELECTION_END_EXCLUSIVE,
  COUNT_IF(c.SEARCH_MAX_HOUR_TS >= c.HOLDOUT_START) AS CAMPAIGN_HOLDOUT_VIOLATIONS,
  COUNT_IF(f.TRAIN_END_EXCLUSIVE > c.HOLDOUT_START
           OR f.VALIDATION_END_EXCLUSIVE > c.HOLDOUT_START)
    AS FOLD_HOLDOUT_VIOLATIONS
FROM ML.PIADE_RESEARCH_CAMPAIGN c
LEFT JOIN ML.PIADE_RESEARCH_FOLD_METRIC f USING (CAMPAIGN_ID)
GROUP BY c.CAMPAIGN_ID,c.HOLDOUT_START,c.SEARCH_MAX_HOUR_TS
ORDER BY c.STARTED_AT DESC;

SELECT
  c.CAMPAIGN_ID,
  c.PROMOTION_ELIGIBLE,
  COUNT(h.SCOPE) AS HOLDOUT_ROWS_WRITTEN,
  COUNT_IF(h.USED_FOR_SELECTION) AS HOLDOUT_USED_FOR_SELECTION,
  COUNT_IF(h.SCOPE IS NOT NULL AND NOT c.PROMOTION_ELIGIBLE)
    AS HOLDOUT_BEFORE_GATES_PASSED,
  COUNT_IF(h.HOLDOUT_START < c.HOLDOUT_START) AS HOLDOUT_WINDOW_VIOLATIONS
FROM ML.PIADE_RESEARCH_CAMPAIGN c
LEFT JOIN ML.PIADE_RESEARCH_HOLDOUT_METRIC h USING (CAMPAIGN_ID)
GROUP BY c.CAMPAIGN_ID,c.PROMOTION_ELIGIBLE
ORDER BY c.CAMPAIGN_ID;

-- 2. No duplicate configuration was ever evaluated. Rejected proposals are
--    excluded because a rejection is precisely the record of a refused repeat.
SELECT
  CAMPAIGN_ID,
  COUNT(*) AS EVALUATED_RUNS,
  COUNT(DISTINCT CONFIG_HASH) AS DISTINCT_CONFIGS,
  COUNT(*)-COUNT(DISTINCT CONFIG_HASH) AS DUPLICATE_CONFIGS,
  COUNT_IF(CONFIG_HASH IS NULL) AS MISSING_CONFIG_HASHES
FROM ML.PIADE_RESEARCH_RUN
WHERE TRIAL_DECISION <> 'REJECTED'
GROUP BY CAMPAIGN_ID
ORDER BY CAMPAIGN_ID;

-- 3. Decision vocabulary and evaluation completeness. The distribution should
--    show BASELINE, KEEP, DISCARD, CRASH and REJECTED rather than a single
--    COMPLETED/FAILED pair, and every violation count must be zero.
SELECT CAMPAIGN_ID,TRIAL_DECISION,EVALUATION_STATUS,COUNT(*) AS RUNS
FROM ML.PIADE_RESEARCH_RUN
GROUP BY CAMPAIGN_ID,TRIAL_DECISION,EVALUATION_STATUS
ORDER BY CAMPAIGN_ID,TRIAL_DECISION,EVALUATION_STATUS;

SELECT
  CAMPAIGN_ID,
  COUNT(*) AS RUN_ROWS,
  COUNT_IF(TRIAL_DECISION NOT IN
           ('BASELINE','KEEP','DISCARD','CRASH','REJECTED','IN_PROGRESS'))
    AS UNKNOWN_DECISIONS,
  COUNT_IF(TRIAL_DECISION='IN_PROGRESS') AS STUCK_IN_PROGRESS_RUNS,
  COUNT_IF(TRIAL_DECISION='REJECTED' AND TRIAL_NUMBER IS NOT NULL)
    AS REJECTED_CONSUMED_A_TRIAL,
  COUNT_IF(TRIAL_DECISION IN ('BASELINE','KEEP','DISCARD')
           AND EVALUATION_STATUS <> 'COMPLETED') AS DECISION_WITHOUT_EVALUATION,
  COUNT_IF(TRIAL_DECISION='CRASH' AND EVALUATION_STATUS <> 'FAILED')
    AS CRASH_WITHOUT_FAILED_EVALUATION,
  COUNT_IF(TRIAL_NUMBER IS NOT NULL) AS EVALUATED_TRIAL_SLOTS,
  COUNT_IF(TRIAL_NUMBER > 25) AS TRIALS_BEYOND_HARD_CAP
FROM ML.PIADE_RESEARCH_RUN
GROUP BY CAMPAIGN_ID
ORDER BY CAMPAIGN_ID;

SELECT
  r.CAMPAIGN_ID,r.RUN_ID,r.TRIAL_NUMBER,r.TRIAL_DECISION,r.EVALUATION_STATUS,
  COUNT(f.FOLD_NAME) AS FOLD_ROWS,
  COUNT(DISTINCT f.FOLD_NAME) AS DISTINCT_FOLDS,
  SUM(f.TOP10_ROWS) AS EXACT_TOP10_ROWS_LOGGED
FROM ML.PIADE_RESEARCH_RUN r
LEFT JOIN ML.PIADE_RESEARCH_FOLD_METRIC f
  USING (CAMPAIGN_ID,RUN_ID,TRIAL_NUMBER)
GROUP BY r.CAMPAIGN_ID,r.RUN_ID,r.TRIAL_NUMBER,r.TRIAL_DECISION,
         r.EVALUATION_STATUS
ORDER BY r.CAMPAIGN_ID,r.TRIAL_NUMBER NULLS LAST;

-- 4. Gate evidence, recomputed from the fold and line logs rather than trusted.
SELECT CAMPAIGN_ID,GATE_ORDER,GATE_NAME,PASSED,CHAMPION_VALUE,BASELINE_VALUE,
       MARGIN,GATE_RULE,DETAIL
FROM ML.PIADE_RESEARCH_PROMOTION_GATE
ORDER BY CAMPAIGN_ID,GATE_ORDER;

SELECT
  c.CAMPAIGN_ID,
  l.MACHINE_CODE,
  l.FOLD_NAME,
  MAX(IFF(l.RUN_ID=c.BASELINE_RUN_ID,l.TOP10_PRECISION_LIFT,NULL))
    AS BASELINE_LINE_LIFT,
  MAX(IFF(l.RUN_ID=c.CHAMPION_RUN_ID,l.TOP10_PRECISION_LIFT,NULL))
    AS CHAMPION_LINE_LIFT,
  COUNT_IF(l.RUN_ID=c.CHAMPION_RUN_ID AND NOT l.BEATS_PERSISTENCE)
    AS CHAMPION_PERSISTENCE_FAILURES,
  COUNT_IF(l.RUN_ID=c.BASELINE_RUN_ID AND NOT l.BEATS_PERSISTENCE)
    AS BASELINE_PERSISTENCE_FAILURES
FROM ML.PIADE_RESEARCH_CAMPAIGN c
JOIN ML.PIADE_RESEARCH_LINE_METRIC l
  ON l.CAMPAIGN_ID=c.CAMPAIGN_ID
 AND l.RUN_ID IN (c.BASELINE_RUN_ID,c.CHAMPION_RUN_ID)
GROUP BY c.CAMPAIGN_ID,l.MACHINE_CODE,l.FOLD_NAME
ORDER BY c.CAMPAIGN_ID,l.MACHINE_CODE,l.FOLD_NAME;

-- 5. Production is untouched and promotion remains an explicit downstream act.
SELECT
  CAMPAIGN_ID,
  PROMOTION_STATUS,
  PROMOTION_ELIGIBLE,
  COUNT_IF(PRODUCTION_TABLES_MODIFIED) AS PRODUCTION_TABLES_MODIFIED
FROM ML.PIADE_RESEARCH_CAMPAIGN
GROUP BY CAMPAIGN_ID,PROMOTION_STATUS,PROMOTION_ELIGIBLE
ORDER BY CAMPAIGN_ID;

SELECT CONTRACT_ID,CAMPAIGN_ID,PROMOTION_STATUS,PROMOTION_ELIGIBLE,
       MODEL_FAMILY,FEATURE_COUNT,FEATURE_LIST_HASH,RANDOM_SEED,
       TRAIN_END_EXCLUSIVE,APPLIED_TO_PRODUCTION,
       VALIDATION_MEAN_AUC,BASELINE_MEAN_AUC,HOLDOUT_AUC,
       ARRAY_TO_STRING(TO_ARRAY(PROMOTION_REASONS),' | ') AS PROMOTION_REASONS
FROM ML.PIADE_CHAMPION_CONTRACT
ORDER BY CREATED_AT DESC;

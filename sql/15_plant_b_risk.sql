/* ============================================================================
   Plant B (PIADE) — hourly stop-risk model.

   WHAT IT PREDICTS

   For each machine-hour, will the NEXT hour lose more than 10% of its time to
   unplanned downtime? Call that a heavy stop.

   WHY THIS TARGET AND NOT A MORE IMPRESSIVE ONE

   Several were measured before anything was built here
   (scripts/probe_piade_predictability.py, chronological holdout):

     target            base    model AUC   baseline AUC   verdict
     any stop next 1h   ~99%       -            -         degenerate, almost
                                                          every hour has some
     heavy stop 1h     40.3%     0.654        0.609       usable, kept
     severe stop 1h    11.5%     0.643        0.602       model loses to the
                                                          baseline on precision
     heavy stop 4h     80.6%     0.680        0.601       base rate too high
                                                          to be actionable
     OEE drop 1h       24.9%     0.580        0.539       too weak

   Predicting a specific alarm code looked far better — alarm A_065 reached
   AUC 0.955 and 4.93x lift — and was discarded. The trivial rule "A_065 fired
   this hour" scores 4.65x on its own, and removing current-hour alarm counts
   dropped the model to 4.34x, below that rule. It was autocorrelation, not
   prediction, and shipping it would have been misleading.

   HOW GOOD IT ACTUALLY IS

   Flagging the riskiest 10% of hours gives 68.8% precision against a 40.3%
   base rate: a lift of 1.71x. The do-nothing baseline of "this hour had
   downtime", flagged under the same top-decile rule, already reaches 55.6%.
   So the model's real contribution is 68.8% against 55.6%, not against 40.3%.

   Per machine it is weaker — AUC 0.524 to 0.609 — meaning part of the
   fleet-level figure comes from the model learning which machines stop more
   rather than when a given machine will stop. The app must show the
   per-machine numbers, not only the fleet number.

   These figures are recomputed by the procedure below and written to
   ML.PLANT_B_MODEL_METRICS. The application reads them from that table rather
   than from any comment, so the displayed accuracy cannot drift from the
   measured accuracy.

   WHY A STORED PROCEDURE AND NOT SNOWFLAKE.ML.CLASSIFICATION

   SNOWFLAKE.ML.CLASSIFICATION, ANOMALY_DETECTION and FORECAST all fail on this
   account with "Provider share does not have sufficient privileges", verified
   in docs/cortex-audit/009-capability-check-result.md. That is a provisioning
   state, not a missing grant. Snowpark Python is the substitute: the model
   still trains and scores inside Snowflake and no data leaves the account.
   ========================================================================= */

USE ROLE ACCOUNTADMIN;
USE DATABASE SNOWCORE_REAL;
USE WAREHOUSE COMPUTE_WH;
ALTER SESSION SET TIMEZONE = 'UTC';
ALTER SESSION SET QUERY_TAG = 'snowcore-real|coco|plant-b-risk';

/* --------------------------------------------------------------------------
   Feature store, built in SQL so every input is auditable without reading
   Python. The procedure that follows does no feature engineering of its own.

   Rolling windows are row-based, matching how the offline probe measured the
   result. Hours are nearly contiguous per machine, and HOURS_SINCE_PREV
   carries the exception so the model can discount a stale window.
   -------------------------------------------------------------------------- */

CREATE OR REPLACE TABLE ML.PLANT_B_FEATURES AS
WITH base AS (
  SELECT
    'PLANT_B:' || EQUIPMENT_ID                                AS MACHINE_KEY,
    EQUIPMENT_ID                                              AS MACHINE_CODE,
    INTERVAL_START                                            AS HOUR_TS,
    /* Everything published for this hour: 133 alarm counts, 25 state
       transitions, 5 state fractions, the package count and the change count.
       Named columns are re-derived below, so they are excluded here to avoid
       duplication. */
    * EXCLUDE (EQUIPMENT_ID, INTERVAL_START, SOURCE_KEY, SOURCE_FILE,
               DATA_ORIGIN, LOAD_TS)
  FROM BRONZE.PIADE_HOURLY_RAW
),
derived AS (
  SELECT
    b.*,
    /* Time actually making product, slow or not. Same definition as Silver. */
    PCT_PRODUCTION + PCT_PERFORMANCE_LOSS                     AS RUN_FRAC,
    DATEDIFF('hour',
      LAG(HOUR_TS) OVER (PARTITION BY MACHINE_KEY ORDER BY HOUR_TS),
      HOUR_TS)                                                AS HOURS_SINCE_PREV
  FROM base b
),
rolled AS (
  SELECT
    d.*,
    AVG(PCT_DOWNTIME) OVER W3   AS DOWNTIME_M3,
    AVG(PCT_DOWNTIME) OVER W12  AS DOWNTIME_M12,
    AVG(PCT_DOWNTIME) OVER W24  AS DOWNTIME_M24,
    AVG(RUN_FRAC)     OVER W3   AS RUN_M3,
    AVG(RUN_FRAC)     OVER W12  AS RUN_M12,
    AVG(RUN_FRAC)     OVER W24  AS RUN_M24,
    AVG(STATE_CHANGES) OVER W12 AS CHANGES_M12,
    AVG(STATE_CHANGES) OVER W24 AS CHANGES_M24,
    AVG(COUNT_SUM)    OVER W12  AS COUNT_M12,
    AVG(COUNT_SUM)    OVER W24  AS COUNT_M24,
    STDDEV_POP(PCT_DOWNTIME) OVER W24 AS DOWNTIME_S24
  FROM derived d
  WINDOW
    W3  AS (PARTITION BY MACHINE_KEY ORDER BY HOUR_TS ROWS BETWEEN 2 PRECEDING AND CURRENT ROW),
    W12 AS (PARTITION BY MACHINE_KEY ORDER BY HOUR_TS ROWS BETWEEN 11 PRECEDING AND CURRENT ROW),
    W24 AS (PARTITION BY MACHINE_KEY ORDER BY HOUR_TS ROWS BETWEEN 23 PRECEDING AND CURRENT ROW)
)
SELECT
  HASH(MACHINE_KEY, HOUR_TS)                                  AS ROW_ID,
  MACHINE_KEY,
  MACHINE_CODE,
  HOUR_TS,
  r.* EXCLUDE (MACHINE_KEY, MACHINE_CODE, HOUR_TS),
  RUN_M3 - RUN_M24                                            AS RUN_TREND,
  COALESCE(HOURS_SINCE_PREV, -1)                              AS GAP_HOURS,

  /* The do-nothing comparison, carried next to the model so the app can show
     both. This hour's downtime, used directly as a prediction of the next. */
  PCT_DOWNTIME                                                AS BASELINE_SCORE,

  /* Target. Strictly the next hour, never this one. */
  IFF(LEAD(PCT_DOWNTIME) OVER (PARTITION BY MACHINE_KEY ORDER BY HOUR_TS) > 0.10,
      1, 0)                                                   AS LABEL_HEAVY_STOP,
  LEAD(PCT_DOWNTIME) OVER (PARTITION BY MACHINE_KEY ORDER BY HOUR_TS)
                                                              AS NEXT_HOUR_DOWNTIME,

  CASE
    WHEN HOUR_TS < '2021-08-01'::TIMESTAMP_NTZ THEN 'TRAIN'
    ELSE 'TEST'
  END                                                         AS SPLIT_PART,
  'DERIVED_FROM_OBSERVED'                                     AS DATA_ORIGIN
FROM rolled r
/* The final hour of each machine has no next hour, so it has no label. */
QUALIFY LEAD(PCT_DOWNTIME) OVER (PARTITION BY MACHINE_KEY ORDER BY HOUR_TS) IS NOT NULL;

COMMENT ON TABLE ML.PLANT_B_FEATURES IS
  'Plant B hourly features and the heavy-stop label. Split is chronological at 2021-08-01; nothing is sampled at random.';

/* Reconciliation. 23,376 hourly rows minus one per machine that has no
   following hour, so 23,371 expected. */
SELECT
  SPLIT_PART,
  COUNT(*)                                  AS ROWS_IN_PART,
  SUM(LABEL_HEAVY_STOP)                     AS POSITIVES,
  ROUND(AVG(LABEL_HEAVY_STOP) * 100, 2)     AS POSITIVE_PCT,
  MIN(HOUR_TS)                              AS FIRST_HOUR,
  MAX(HOUR_TS)                              AS LAST_HOUR
FROM ML.PLANT_B_FEATURES
GROUP BY SPLIT_PART
ORDER BY FIRST_HOUR;

/* --------------------------------------------------------------------------
   Train and score, inside Snowflake.

   The procedure deliberately does nothing clever. It reads the feature table,
   splits on the column that is already there, fits one model, scores the
   held-out period, and writes both the scores and the measured metrics. Any
   judgement about the target, the features or the split was made in SQL above
   where it can be reviewed.
   -------------------------------------------------------------------------- */

CREATE OR REPLACE PROCEDURE ML.TRAIN_PLANT_B_RISK()
RETURNS VARIANT
LANGUAGE PYTHON
RUNTIME_VERSION = '3.11'
PACKAGES = ('snowflake-snowpark-python', 'scikit-learn', 'pandas', 'numpy', 'pyarrow')
HANDLER = 'run'
AS
$$
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import average_precision_score, roc_auc_score

# Columns that describe a row rather than the machine's condition. Feeding any
# of these to the model would either leak the answer or teach it the calendar.
NOT_FEATURES = {
    "ROW_ID", "MACHINE_KEY", "MACHINE_CODE", "HOUR_TS", "SPLIT_PART",
    "DATA_ORIGIN", "LABEL_HEAVY_STOP", "NEXT_HOUR_DOWNTIME", "BASELINE_SCORE",
}

SEED = 20260924


def _top_decile(y: pd.Series, score: np.ndarray) -> tuple[float, float]:
    """Precision and recall when only the riskiest 10% of hours are flagged.

    A maintenance team cannot act on half the hours in a week, so this is the
    operating point that matters rather than the 0.5 threshold.
    """
    if len(score) == 0:
        return 0.0, 0.0
    cut = float(np.quantile(score, 0.90))
    flagged = score >= cut
    if flagged.sum() == 0:
        return 0.0, 0.0
    precision = float(y[flagged].mean())
    recall = float(y[flagged].sum() / y.sum()) if y.sum() else 0.0
    return precision, recall


def run(session):
    df = session.table("ML.PLANT_B_FEATURES").to_pandas()

    features = [
        c for c in df.columns
        if c not in NOT_FEATURES and pd.api.types.is_numeric_dtype(df[c])
    ]
    df[features] = df[features].fillna(0)

    train = df[df["SPLIT_PART"] == "TRAIN"]
    test = df[df["SPLIT_PART"] == "TEST"].copy()
    y_train = train["LABEL_HEAVY_STOP"].astype(int)
    y_test = test["LABEL_HEAVY_STOP"].astype(int)

    model = GradientBoostingClassifier(
        n_estimators=250, max_depth=5, learning_rate=0.08,
        subsample=0.8, random_state=SEED,
    )
    model.fit(train[features], y_train)
    prob = model.predict_proba(test[features])[:, 1]
    test["RISK_SCORE"] = prob

    base_rate = float(y_test.mean())
    model_prec, model_rec = _top_decile(y_test, prob)
    base_prec, base_rec = _top_decile(y_test, test["BASELINE_SCORE"].to_numpy())

    # The threshold that flags the riskiest decile, persisted so the app uses
    # the same cut the metrics were measured at.
    decile_cut = float(np.quantile(prob, 0.90))
    test["IS_FLAGGED"] = (prob >= decile_cut).astype(int)
    test["RISK_BAND"] = pd.cut(
        prob, bins=[-0.01, 0.25, 0.50, 0.75, 1.01],
        labels=["LOW", "MODERATE", "ELEVATED", "HIGH"],
    ).astype(str)

    scores = test[[
        "ROW_ID", "MACHINE_KEY", "MACHINE_CODE", "HOUR_TS", "RISK_SCORE",
        "RISK_BAND", "IS_FLAGGED", "BASELINE_SCORE", "LABEL_HEAVY_STOP",
        "NEXT_HOUR_DOWNTIME",
    ]].copy()
    scores["DATA_ORIGIN"] = "DERIVED_FROM_OBSERVED"
    session.write_pandas(
        scores, "PLANT_B_RISK_SCORE", schema="ML",
        auto_create_table=True, overwrite=True, quote_identifiers=False,
    )

    # Per machine, because the fleet number hides the weak machines.
    per_machine = []
    for code, grp in test.groupby("MACHINE_CODE"):
        yg = grp["LABEL_HEAVY_STOP"].astype(int)
        if yg.nunique() < 2:
            continue
        p, r = _top_decile(yg, grp["RISK_SCORE"].to_numpy())
        per_machine.append({
            "SCOPE": code,
            "TEST_ROWS": int(len(grp)),
            "BASE_RATE": float(yg.mean()),
            "AUC": float(roc_auc_score(yg, grp["RISK_SCORE"])),
            "AVG_PRECISION": float(average_precision_score(yg, grp["RISK_SCORE"])),
            "TOP_DECILE_PRECISION": p,
            "TOP_DECILE_RECALL": r,
            "BASELINE_TOP_DECILE_PRECISION": float(
                _top_decile(yg, grp["BASELINE_SCORE"].to_numpy())[0]),
        })

    rows = [{
        "SCOPE": "FLEET",
        "TEST_ROWS": int(len(test)),
        "BASE_RATE": base_rate,
        "AUC": float(roc_auc_score(y_test, prob)),
        "AVG_PRECISION": float(average_precision_score(y_test, prob)),
        "TOP_DECILE_PRECISION": model_prec,
        "TOP_DECILE_RECALL": model_rec,
        "BASELINE_TOP_DECILE_PRECISION": base_prec,
    }] + per_machine

    metrics = pd.DataFrame(rows)
    metrics["DECILE_THRESHOLD"] = decile_cut
    metrics["TRAIN_ROWS"] = int(len(train))
    metrics["FEATURE_COUNT"] = len(features)
    metrics["TARGET"] = "next hour loses more than 10% to unplanned downtime"
    metrics["EVALUATION"] = "chronological holdout from 2021-08-01, never a random split"
    metrics["MODEL"] = "sklearn GradientBoostingClassifier in Snowpark; SNOWFLAKE.ML.CLASSIFICATION unavailable on this account"
    metrics["SEED"] = SEED
    metrics["TRAINED_AT"] = pd.Timestamp.utcnow().tz_localize(None)
    session.write_pandas(
        metrics, "PLANT_B_MODEL_METRICS", schema="ML",
        auto_create_table=True, overwrite=True, quote_identifiers=False,
    )

    imp = pd.DataFrame({
        "FEATURE": features,
        "IMPORTANCE": model.feature_importances_.astype(float),
    }).sort_values("IMPORTANCE", ascending=False).head(40).reset_index(drop=True)
    imp["RANK"] = imp.index + 1
    session.write_pandas(
        imp, "PLANT_B_FEATURE_IMPORTANCE", schema="ML",
        auto_create_table=True, overwrite=True, quote_identifiers=False,
    )

    return {
        "train_rows": int(len(train)),
        "test_rows": int(len(test)),
        "features": len(features),
        "base_rate": round(base_rate, 4),
        "auc": round(float(roc_auc_score(y_test, prob)), 4),
        "top_decile_precision": round(model_prec, 4),
        "baseline_top_decile_precision": round(base_prec, 4),
        "lift_over_base_rate": round(model_prec / base_rate, 3) if base_rate else None,
        "lift_over_baseline": round(model_prec / base_prec, 3) if base_prec else None,
    }
$$;

CALL ML.TRAIN_PLANT_B_RISK();

/* ==========================================================================
   Verification.
   ========================================================================== */

/* 1. The headline numbers, read from the table the app will read.
      Expected from the offline probe: base rate near 40.3%, AUC near 0.654,
      top-decile precision near 68.8%, baseline near 55.6%. A large departure
      means the SQL features do not match what was measured offline. */
SELECT
  SCOPE, TEST_ROWS,
  ROUND(BASE_RATE * 100, 2)                     AS BASE_RATE_PCT,
  ROUND(AUC, 4)                                 AS AUC,
  ROUND(TOP_DECILE_PRECISION * 100, 2)          AS TOP_DECILE_PRECISION_PCT,
  ROUND(BASELINE_TOP_DECILE_PRECISION * 100, 2) AS BASELINE_PRECISION_PCT,
  ROUND(TOP_DECILE_RECALL * 100, 2)             AS TOP_DECILE_RECALL_PCT,
  ROUND(DIV0(TOP_DECILE_PRECISION, BASE_RATE), 3)                     AS LIFT_OVER_BASE,
  ROUND(DIV0(TOP_DECILE_PRECISION, BASELINE_TOP_DECILE_PRECISION), 3) AS LIFT_OVER_BASELINE
FROM ML.PLANT_B_MODEL_METRICS
ORDER BY IFF(SCOPE = 'FLEET', 0, 1), SCOPE;

/* 2. Does the score separate the classes? Plant A failed exactly here. */
SELECT
  LABEL_HEAVY_STOP,
  COUNT(*)                        AS ROWS_IN_CLASS,
  ROUND(AVG(RISK_SCORE), 4)       AS MEAN_SCORE,
  ROUND(MEDIAN(RISK_SCORE), 4)    AS MEDIAN_SCORE
FROM ML.PLANT_B_RISK_SCORE
GROUP BY LABEL_HEAVY_STOP
ORDER BY LABEL_HEAVY_STOP;

/* 3. Calibration. Within each band, what fraction of hours really did suffer
      a heavy stop? A band labelled HIGH that behaves like LOW is worse than
      no band at all, because the app would be lying in colour. */
SELECT
  RISK_BAND,
  COUNT(*)                                        AS HOURS,
  ROUND(AVG(RISK_SCORE), 4)                       AS MEAN_PREDICTED,
  ROUND(AVG(LABEL_HEAVY_STOP), 4)                 AS ACTUAL_RATE,
  ROUND(AVG(NEXT_HOUR_DOWNTIME) * 100, 2)         AS AVG_NEXT_HOUR_DOWNTIME_PCT
FROM ML.PLANT_B_RISK_SCORE
GROUP BY RISK_BAND
ORDER BY MEAN_PREDICTED;

/* 4. What the model is actually using. If the top features are all recent
      downtime, the model is a smoothed persistence rule and should be
      described as one. */
SELECT RANK, FEATURE, ROUND(IMPORTANCE, 4) AS IMPORTANCE
FROM ML.PLANT_B_FEATURE_IMPORTANCE
ORDER BY RANK
LIMIT 15;

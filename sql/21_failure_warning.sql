/* ============================================================================
   PIADE 4-hour breakdown warning.

   Question answered: at the end of machine-hour H, will this line suffer a
   breakdown (STOP_STATE='downtime', one interval of at least 10 minutes)
   that STARTS in the next four hours, i.e. in [H+1h, H+5h)?

   A breakdown here is the same definition GOLD.WORK_ORDER already uses, so a
   positive label is exactly "a real maintenance work order was raised".

   Design, stated so it can be challenged:
   - Inputs are the unchanged 299-feature contract in ML.PLANT_B_FEATURES and
     the unchanged production configuration (ExtraTrees 700/0.4/30). Nothing
     is tuned on the December 2021 holdout.
   - Training rows whose 4-hour label window reaches into the holdout are
     purged, so no holdout breakdown ever labels a training row.
   - Rows whose next four hours are less than 90% covered by the logged state
     intervals are excluded: a logging gap is not evidence that no breakdown
     happened. Coverage comes from SILVER.PIADE_INTERVAL, not the hourly
     table, because the published hourly table omits many logged hours.
   - Three do-nothing rules are scored beside the model:
       PERSISTENCE  current-hour downtime share
       RECENT_BREAKDOWNS  long breakdowns already visible in the last 24 hours
       LINE_RATE  the line's training-period breakdown rate ("worst line first")
     (ties broken by current-hour downtime share). The model is only useful
     where it beats the best of the three.
   - Alerts are flagged two ways: the fleet top 10% and each line's own top
     10%. The fleet cut concentrates on the worst line; the per-line cut asks
     which hours are unusual for that line.
   - Scores are rankings on one anonymised five-line site, not calibrated
     failure probabilities and not remaining useful life.

   Existing PLANT_B_RISK_* tables are not read for training and not modified.
   ========================================================================== */

USE ROLE ACCOUNTADMIN;
USE DATABASE SNOWCORE_REAL;
USE WAREHOUSE COMPUTE_WH;
ALTER SESSION SET TIMEZONE = 'UTC';
ALTER SESSION SET QUERY_TAG = 'snowcore-real|piade|failure-warning-4h';

CREATE OR REPLACE TABLE ML.PLANT_B_INTERVAL_COVERAGE_HOUR AS
WITH iv AS (
  SELECT MACHINE_KEY,
         CONVERT_TIMEZONE('UTC', INTERVAL_START)::TIMESTAMP_NTZ AS S,
         DATEADD('millisecond', ROUND(DURATION_SEC * 1000)::INT,
                 CONVERT_TIMEZONE('UTC', INTERVAL_START)::TIMESTAMP_NTZ) AS E
  FROM SILVER.PIADE_INTERVAL
  WHERE DURATION_SEC > 0
),
exploded AS (
  SELECT MACHINE_KEY, S, E,
         DATEADD('hour', g.value::INT, DATE_TRUNC('hour', S)) AS HOUR_TS
  FROM iv,
       LATERAL FLATTEN(ARRAY_GENERATE_RANGE(0, DATEDIFF('hour', DATE_TRUNC('hour', S), E) + 1)) g
)
SELECT MACHINE_KEY, HOUR_TS,
  LEAST(3600, SUM(GREATEST(0, DATEDIFF('millisecond', GREATEST(S, HOUR_TS),
                                       LEAST(E, DATEADD('hour', 1, HOUR_TS))))) / 1000) AS COVERED_SEC
FROM exploded
GROUP BY MACHINE_KEY, HOUR_TS;

CREATE OR REPLACE TABLE ML.PLANT_B_FAILURE_LABEL AS
WITH hours AS (
  SELECT ROW_ID, MACHINE_KEY, MACHINE_CODE, HOUR_TS
  FROM ML.PLANT_B_FEATURES
),
long_stop AS (
  /* Interval timestamps are TIMESTAMP_TZ; hourly timestamps are UTC NTZ. */
  SELECT MACHINE_KEY,
         CONVERT_TIMEZONE('UTC', STOP_START)::TIMESTAMP_NTZ AS STOP_START_UTC,
         STOP_DURATION_MIN
  FROM GOLD.PIADE_DOWNTIME_EVENT
  WHERE STOP_STATE = 'downtime' AND STOP_DURATION_MIN >= 10
),
future AS (
  SELECT h.ROW_ID, COUNT(s.STOP_START_UTC) AS N, MIN(s.STOP_START_UTC) AS FIRST_START
  FROM hours h
  LEFT JOIN long_stop s
    ON s.MACHINE_KEY = h.MACHINE_KEY
   AND s.STOP_START_UTC >= DATEADD('hour', 1, h.HOUR_TS)
   AND s.STOP_START_UTC <  DATEADD('hour', 5, h.HOUR_TS)
  GROUP BY h.ROW_ID
),
past AS (
  /* Only breakdowns that had already lasted 10 minutes by the end of hour H
     are knowable at H; a stop that started late in H is not yet "long". */
  SELECT h.ROW_ID, COUNT(s.STOP_START_UTC) AS N
  FROM hours h
  LEFT JOIN long_stop s
    ON s.MACHINE_KEY = h.MACHINE_KEY
   AND s.STOP_START_UTC >= DATEADD('hour', -23, h.HOUR_TS)
   AND DATEADD('minute', 10, s.STOP_START_UTC) <= DATEADD('hour', 1, h.HOUR_TS)
  GROUP BY h.ROW_ID
),
observed AS (
  SELECT h.ROW_ID, COALESCE(SUM(c.COVERED_SEC), 0) / 14400 AS COVERAGE
  FROM hours h
  LEFT JOIN ML.PLANT_B_INTERVAL_COVERAGE_HOUR c
    ON c.MACHINE_KEY = h.MACHINE_KEY
   AND c.HOUR_TS >= DATEADD('hour', 1, h.HOUR_TS)
   AND c.HOUR_TS <  DATEADD('hour', 5, h.HOUR_TS)
  GROUP BY h.ROW_ID
)
SELECT
  h.ROW_ID, h.MACHINE_KEY, h.MACHINE_CODE, h.HOUR_TS,
  IFF(f.N > 0, 1, 0)                                              AS LABEL_BREAKDOWN_4H,
  f.N                                                             AS FUTURE_LONG_BREAKDOWNS,
  DATEDIFF('minute', DATEADD('hour', 1, h.HOUR_TS), f.FIRST_START) AS LEAD_TIME_MIN,
  p.N                                                             AS PAST_LONG_BREAKDOWNS_24H,
  ROUND(o.COVERAGE, 4)                                            AS FUTURE_COVERAGE,
  o.COVERAGE >= 0.9                                               AS LABEL_IS_COMPLETE,
  CASE
    WHEN h.HOUR_TS >= '2021-12-01'::TIMESTAMP_NTZ THEN 'FINAL_BLIND_TEST'
    WHEN DATEADD('hour', 5, h.HOUR_TS) > '2021-12-01'::TIMESTAMP_NTZ THEN 'PURGED_BOUNDARY'
    ELSE 'TRAIN'
  END                                                             AS SPLIT_PART,
  'DERIVED_FROM_OBSERVED'                                         AS DATA_ORIGIN
FROM hours h
JOIN future f   ON f.ROW_ID = h.ROW_ID
JOIN past p     ON p.ROW_ID = h.ROW_ID
JOIN observed o ON o.ROW_ID = h.ROW_ID;

COMMENT ON TABLE ML.PLANT_B_FAILURE_LABEL IS
  'Label: observed breakdown (downtime interval >= 10 min) starting within [H+1h, H+5h). Rows whose future window is under 90% covered by logged intervals are excluded at training time.';

CREATE OR REPLACE PROCEDURE ML.TRAIN_PLANT_B_FAILURE_WARNING()
RETURNS VARIANT
LANGUAGE PYTHON
RUNTIME_VERSION = '3.11'
PACKAGES = ('snowflake-snowpark-python','scikit-learn','pandas','numpy','pyarrow')
HANDLER = 'run'
EXECUTE AS CALLER
AS
$$
import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesClassifier
from sklearn.metrics import average_precision_score, roc_auc_score

SEED = 20260925
FINAL_TEST_START = pd.Timestamp("2021-12-01")
LABEL = "LABEL_BREAKDOWN_4H"
NOT_FEATURES = {
    "ROW_ID","MACHINE_KEY","MACHINE_CODE","HOUR_TS","SPLIT_PART","DATA_ORIGIN",
    "LABEL_HEAVY_STOP","NEXT_HOUR_DOWNTIME","BASELINE_SCORE",
    "LABEL_BREAKDOWN_4H","FUTURE_LONG_BREAKDOWNS","LEAD_TIME_MIN",
    "PAST_LONG_BREAKDOWNS_24H","FUTURE_COVERAGE","LABEL_SPLIT",
}
BASELINES = [("PERSISTENCE", "PERSISTENCE_SCORE"),
             ("RECENT", "RECENT_BREAKDOWN_SCORE"),
             ("LINE_RATE", "LINE_RATE_SCORE")]

def exact_fraction(y, score, machine, hour, fraction=0.10):
    """Exactly ceil(n*fraction) rows; deterministic tie break, no inflation."""
    order = pd.DataFrame({
        "score": np.asarray(score, dtype=float),
        "machine": machine.astype(str).to_numpy(),
        "hour": pd.to_datetime(hour).astype("int64").to_numpy(),
        "position": np.arange(len(y)),
    }).sort_values(
        ["score","machine","hour"], ascending=[False,True,True], kind="mergesort"
    )["position"].to_numpy()
    take = max(1, int(np.ceil(len(order) * fraction)))
    selected = order[:take]
    yy = np.asarray(y, dtype=int)
    hits = int(yy[selected].sum())
    return selected, hits / take, hits / int(yy.sum()) if yy.sum() else 0.0

def safe_metrics(y, score):
    if pd.Series(y).nunique() < 2:
        return None, None
    return float(roc_auc_score(y, score)), float(average_precision_score(y, score))

def run(session):
    df = session.sql("""
        SELECT f.*, l.LABEL_BREAKDOWN_4H, l.FUTURE_LONG_BREAKDOWNS, l.LEAD_TIME_MIN,
               l.PAST_LONG_BREAKDOWNS_24H, l.FUTURE_COVERAGE,
               l.SPLIT_PART AS LABEL_SPLIT
        FROM ML.PLANT_B_FEATURES f
        JOIN ML.PLANT_B_FAILURE_LABEL l ON l.ROW_ID = f.ROW_ID
        WHERE l.LABEL_IS_COMPLETE
    """).to_pandas()
    df = df.sort_values(["MACHINE_CODE","HOUR_TS"], kind="mergesort").reset_index(drop=True)
    derived = ["RUN_FRAC","ALARM_TOTAL","ALARM_DISTINCT","TRANSITION_TOTAL"]
    history = []
    for source in [
        "PCT_DOWNTIME","PCT_IDLE","RUN_FRAC","ALARM_TOTAL",
        "ALARM_DISTINCT","STATE_CHANGES","COUNT_SUM",
    ]:
        for window in (3,6,12,24,72):
            history.append(f"{source}_MEAN_{window}")
            if window in (12,24,72):
                history.extend([f"{source}_MAX_{window}",f"{source}_STD_{window}"])
        history.extend([f"{source}_LAG_{lag}" for lag in (1,2,3,6,12,24)])
    extras = [
        "DOWNTIME_ACCEL_3_24","RUN_ACCEL_3_24","ALARM_ACCEL_3_24",
        "HOURS_SINCE_HEAVY_STOP","GAP_HOURS",
        "HOUR_SIN","HOUR_COS","DOW_SIN","DOW_COS",
        "MACHINE_S_1","MACHINE_S_2","MACHINE_S_3","MACHINE_S_4","MACHINE_S_5",
    ]
    engineered = set(derived + history + extras)
    source = [c for c in df.columns if c not in NOT_FEATURES
              and c not in engineered and pd.api.types.is_numeric_dtype(df[c])]
    features = source + derived + history + extras
    if len(features) != 299:
        raise ValueError(f"Feature contract drift: expected 299 numeric features, got {len(features)}")
    df[features] = df[features].replace([np.inf,-np.inf], np.nan).fillna(0)

    train = df[df["LABEL_SPLIT"] == "TRAIN"]
    test = df[df["LABEL_SPLIT"] == "FINAL_BLIND_TEST"].copy()
    if train.empty or test.empty:
        raise ValueError("Chronological train/final-blind-test split produced an empty partition")
    if pd.to_datetime(train["HOUR_TS"]).max() + pd.Timedelta(hours=5) > FINAL_TEST_START:
        raise ValueError("Purge violated: a training label window reaches the holdout")

    model = ExtraTreesClassifier(
        n_estimators=700, max_features=0.4, min_samples_leaf=30,
        class_weight="balanced", n_jobs=-1, random_state=SEED,
    )
    model.fit(train[features], train[LABEL].astype(int))
    test["FAILURE_SCORE"] = model.predict_proba(test[features])[:, 1]
    test["PERSISTENCE_SCORE"] = test["BASELINE_SCORE"].astype(float)
    test["RECENT_BREAKDOWN_SCORE"] = (
        test["PAST_LONG_BREAKDOWNS_24H"].astype(float)
        + 0.001 * test["BASELINE_SCORE"].astype(float)
    )
    line_rate = train.groupby("MACHINE_CODE")[LABEL].mean()
    test["LINE_TRAIN_RATE"] = test["MACHINE_CODE"].map(line_rate).astype(float)
    test["LINE_RATE_SCORE"] = test["LINE_TRAIN_RATE"] + 0.001 * test["BASELINE_SCORE"].astype(float)

    chosen, _, _ = exact_fraction(
        test[LABEL], test["FAILURE_SCORE"], test["MACHINE_CODE"], test["HOUR_TS"])
    test["IS_FLAGGED"] = 0
    test.iloc[chosen, test.columns.get_loc("IS_FLAGGED")] = 1
    threshold = float(test.loc[test["IS_FLAGGED"] == 1, "FAILURE_SCORE"].min())
    test["IS_FLAGGED_LINE"] = 0
    test["LINE_THRESHOLD_SCORE"] = np.nan
    for _, grp in test.groupby("MACHINE_CODE", sort=True):
        picked, _, _ = exact_fraction(
            grp[LABEL], grp["FAILURE_SCORE"], grp["MACHINE_CODE"], grp["HOUR_TS"])
        index = grp.index[picked]
        test.loc[index, "IS_FLAGGED_LINE"] = 1
        test.loc[grp.index, "LINE_THRESHOLD_SCORE"] = float(grp.loc[index, "FAILURE_SCORE"].min())
    rank = test[["FAILURE_SCORE","MACHINE_CODE","HOUR_TS"]].sort_values(
        ["FAILURE_SCORE","MACHINE_CODE","HOUR_TS"],
        ascending=[True,True,True], kind="mergesort").index
    percentile = pd.Series(np.arange(1, len(test)+1) / len(test), index=rank)
    test["FAILURE_PERCENTILE"] = test.index.map(percentile)

    scores = test[[
        "ROW_ID","MACHINE_KEY","MACHINE_CODE","FAILURE_SCORE","FAILURE_PERCENTILE",
        "IS_FLAGGED","IS_FLAGGED_LINE","LINE_THRESHOLD_SCORE","LINE_TRAIN_RATE",
        "PERSISTENCE_SCORE","RECENT_BREAKDOWN_SCORE","LINE_RATE_SCORE",
        "PAST_LONG_BREAKDOWNS_24H",LABEL,"FUTURE_LONG_BREAKDOWNS","LEAD_TIME_MIN",
        "FUTURE_COVERAGE",
    ]].copy()
    # write_pandas stores pandas timestamps as epoch nanoseconds on this
    # account, so timestamps travel as text and are cast in SQL below.
    scores["HOUR_TS_TEXT"] = pd.to_datetime(test["HOUR_TS"]).dt.strftime("%Y-%m-%d %H:%M:%S")
    scores["FLAG_THRESHOLD_SCORE"] = threshold
    scores["DATA_ORIGIN"] = "DERIVED_FROM_OBSERVED"
    session.write_pandas(scores, "PLANT_B_FAILURE_SCORE_STAGE", schema="ML",
                         auto_create_table=True, overwrite=True, quote_identifiers=False)
    session.sql("""
        CREATE OR REPLACE TABLE ML.PLANT_B_FAILURE_SCORE AS
        SELECT ROW_ID, MACHINE_KEY, MACHINE_CODE,
               TO_TIMESTAMP_NTZ(HOUR_TS_TEXT) AS HOUR_TS,
               DATEADD('hour', 1, TO_TIMESTAMP_NTZ(HOUR_TS_TEXT)) AS WARNING_ISSUED_AT,
               FAILURE_SCORE, FAILURE_PERCENTILE, IS_FLAGGED, FLAG_THRESHOLD_SCORE,
               IS_FLAGGED_LINE, LINE_THRESHOLD_SCORE, LINE_TRAIN_RATE,
               PERSISTENCE_SCORE, RECENT_BREAKDOWN_SCORE, LINE_RATE_SCORE,
               PAST_LONG_BREAKDOWNS_24H,
               LABEL_BREAKDOWN_4H, FUTURE_LONG_BREAKDOWNS, LEAD_TIME_MIN, FUTURE_COVERAGE,
               'FINAL_BLIND_TEST' AS SCORE_PERIOD, DATA_ORIGIN
        FROM ML.PLANT_B_FAILURE_SCORE_STAGE
    """).collect()
    session.sql("DROP TABLE IF EXISTS ML.PLANT_B_FAILURE_SCORE_STAGE").collect()

    rows = []
    for scope, grp in [("FLEET", test)] + list(test.groupby("MACHINE_CODE", sort=True)):
        y = grp[LABEL].astype(int)
        row = {"SCOPE": scope, "TEST_ROWS": int(len(grp)), "BASE_RATE": float(y.mean()),
               "TOP_DECILE_ROWS": int(np.ceil(len(grp) * 0.10))}
        for prefix, column in [("MODEL", "FAILURE_SCORE")] + BASELINES:
            auc, ap = safe_metrics(y, grp[column])
            _, p, r = exact_fraction(y, grp[column], grp["MACHINE_CODE"], grp["HOUR_TS"])
            row.update({f"{prefix}_AUC": auc, f"{prefix}_AVG_PRECISION": ap,
                        f"{prefix}_TOP_DECILE_PRECISION": p, f"{prefix}_TOP_DECILE_RECALL": r})
        # Within one line the line-rate rule is a constant, so it collapses
        # to persistence; it only differs from persistence at fleet scope.
        best_prefix = max((prefix for prefix, _ in BASELINES),
                          key=lambda prefix: row[f"{prefix}_TOP_DECILE_PRECISION"])
        best = row[f"{best_prefix}_TOP_DECILE_PRECISION"]
        row["BEST_BASELINE"] = best_prefix
        row["BEST_BASELINE_TOP_DECILE_PRECISION"] = best
        row["MODEL_ADVANTAGE_PTS"] = (row["MODEL_TOP_DECILE_PRECISION"] - best) * 100
        row["VERDICT"] = ("MODEL_BEATS_BEST_BASELINE" if row["MODEL_TOP_DECILE_PRECISION"] > best
                          else "MODEL_DOES_NOT_BEAT_BEST_BASELINE")
        rows.append(row)
    metrics = pd.DataFrame(rows)
    metrics["TRAIN_ROWS"] = int(len(train))
    metrics["TRAIN_POSITIVE_RATE"] = float(train[LABEL].mean())
    metrics["EXCLUDED_INCOMPLETE_ROWS"] = int(
        session.sql("SELECT COUNT(*) N FROM ML.PLANT_B_FAILURE_LABEL WHERE NOT LABEL_IS_COMPLETE").collect()[0]["N"])
    metrics["FEATURE_COUNT"] = len(features)
    metrics["FLAG_THRESHOLD_SCORE"] = threshold
    metrics["TARGET"] = "breakdown (downtime interval >= 10 min) starting within the next 4 hours"
    metrics["MODEL"] = "sklearn ExtraTreesClassifier"
    metrics["MODEL_CONFIG"] = "n_estimators=700,max_features=0.4,min_samples_leaf=30,class_weight=balanced"
    metrics["SELECTION_METHOD"] = "production configuration reused unchanged; nothing tuned on the holdout"
    metrics["BLIND_TEST_START"] = str(FINAL_TEST_START.date())
    metrics["BLIND_TEST_END"] = str(pd.to_datetime(test["HOUR_TS"]).max())
    metrics["SEED"] = SEED
    metrics["CAVEAT"] = ("One anonymised five-line site; one holdout month; the top-10% threshold "
                         "is taken from the holdout score distribution; rankings are not causal.")
    metrics["TRAINED_AT"] = str(pd.Timestamp.utcnow().tz_localize(None))
    session.write_pandas(metrics, "PLANT_B_FAILURE_METRICS", schema="ML",
                         auto_create_table=True, overwrite=True, quote_identifiers=False)

    importance = pd.DataFrame({
        "FEATURE": features,
        "IMPORTANCE": model.feature_importances_.astype(float),
    }).sort_values(["IMPORTANCE","FEATURE"], ascending=[False,True]).reset_index(drop=True)
    importance["RANK"] = np.arange(1, len(importance)+1)
    importance["MODEL"] = "ExtraTreesClassifier"
    session.write_pandas(importance, "PLANT_B_FAILURE_IMPORTANCE", schema="ML",
                         auto_create_table=True, overwrite=True, quote_identifiers=False)

    fleet = metrics[metrics["SCOPE"] == "FLEET"].iloc[0]
    return {
        "train_rows": int(len(train)), "blind_test_rows": int(len(test)),
        "base_rate": float(fleet["BASE_RATE"]),
        "model_top_decile_precision": float(fleet["MODEL_TOP_DECILE_PRECISION"]),
        "persistence_top_decile_precision": float(fleet["PERSISTENCE_TOP_DECILE_PRECISION"]),
        "recent_top_decile_precision": float(fleet["RECENT_TOP_DECILE_PRECISION"]),
        "line_rate_top_decile_precision": float(fleet["LINE_RATE_TOP_DECILE_PRECISION"]),
        "model_auc": fleet["MODEL_AUC"], "verdict": fleet["VERDICT"],
    }
$$;

CALL ML.TRAIN_PLANT_B_FAILURE_WARNING();

CREATE OR REPLACE VIEW GOLD.V_FAILURE_WARNING AS
SELECT 'PLANT_B' PLANT_CODE, s.*,
  m.VERDICT AS LINE_VERDICT, m.MODEL_TOP_DECILE_PRECISION AS LINE_MODEL_PRECISION,
  m.BEST_BASELINE_TOP_DECILE_PRECISION AS LINE_BASELINE_PRECISION
FROM ML.PLANT_B_FAILURE_SCORE s
LEFT JOIN ML.PLANT_B_FAILURE_METRICS m ON m.SCOPE = s.MACHINE_CODE;

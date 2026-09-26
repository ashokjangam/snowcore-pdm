# Cortex prompt 037g2 result — campaign 233717d9

Use connection `hackathon` only if verifying; this file is the measured record.

Campaign `233717d9-b657-4d83-a030-e918e9849237` STATUS=COMPLETED,
EVALUATED_TRIALS=25, CRASHED_TRIALS=0, STOP_REASON=TRIAL_LIMIT_REACHED,
started 2026-09-26 04:46, finished 2026-09-26 05:08 (account TZ),
PRODUCTION_TABLES_MODIFIED=FALSE.

Baseline ExtraTrees 700 / 0.4 / 30: mean validation AUC 0.687942.
Champion trial 4 ExtraTrees 600 / 0.7 / 45, class_weight balanced_subsample,
299 features, seed 20260925: mean validation AUC 0.688040, worst-fold 0.678699.
Four gates passed. PROMOTION_ELIGIBLE=TRUE.
Contract `9e96f29e-4f98-41d3-a5eb-e08d5f3aa797` APPLIED_TO_PRODUCTION=FALSE.
Reused-holdout fleet AUC 0.688842, top-10 precision 0.764331,
USED_FOR_SELECTION=FALSE on all six holdout rows.
SEARCH_MAX_HOUR_TS=2021-11-30 23:00:00, HOLDOUT_START=2021-12-01.
Registry BEST_EFFORT_SKIPPED (snowflake-ml-python version spec).
PLANT_B_* last_altered 2026-09-24 14:08:13 -0700 — not written by this campaign.

The validation lift is ~0.0001 AUC. sql/15 was not applied.

# Cortex prompt 037g3 — verification queries for campaign 233717d9

Use connection `hackathon`. Do not CALL the procedure. Do not write PLANT_B_*.

Run the verification block at the end of `sql/20_piade_autoresearch.sql`
(holdout violations, duplicate configs, decision vocabulary, trial cap,
gate rows) filtered to CAMPAIGN_ID
`233717d9-b657-4d83-a030-e918e9849237` where a campaign filter is natural.

Return only: CAMPAIGN_HOLDOUT_VIOLATIONS, FOLD_HOLDOUT_VIOLATIONS,
HOLDOUT_USED_FOR_SELECTION, HOLDOUT_BEFORE_GATES_PASSED,
DUPLICATE_CONFIGS, UNKNOWN_DECISIONS, STUCK_IN_PROGRESS_RUNS,
REJECTED_CONSUMED_A_TRIAL, TRIALS_BEYOND_HARD_CAP, EVALUATED_TRIAL_SLOTS,
GATES_PASSED count, APPLIED_TO_PRODUCTION, PRODUCTION_TABLES_MODIFIED.
Every violation count must be zero.

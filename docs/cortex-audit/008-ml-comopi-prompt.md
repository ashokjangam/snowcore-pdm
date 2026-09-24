Execute `sql/14_ml_comopi.sql` against Snowflake, in order, statement by
statement. Read the file first; its header explains the label design and the
measured counts the checks below refer to.

This script builds the Plant A predictive-maintenance model: a feature store,
a chronological train/test split with a purge gap, a `SNOWFLAKE.ML.CLASSIFICATION`
model, held-out scoring, and five evaluation queries.

## Syntax you may need to correct

I wrote this from the documented forms, but three things are version-sensitive
and you should fix them against what the account actually accepts, then tell me
exactly what you changed and why:

1. The `INPUT_DATA` argument to `CREATE SNOWFLAKE.ML.CLASSIFICATION`. If
   `SYSTEM$REFERENCE('VIEW', 'ML.COMOPI_TRAIN')` is rejected, try the
   `TABLE(ML.COMOPI_TRAIN)` form or `SYSTEM$QUERY_REFERENCE`.
2. The JSON keys returned by `!PREDICT`. I assumed `PRED:class` and
   `PRED:probability:ALARM_60M`. Select one raw prediction row first and read
   the actual key names before creating `ML.COMOPI_PREDICTIONS`.
3. `SHOW_GLOBAL_EVALUATION_METRICS` may not exist on this version. If it
   errors, skip that one call and continue; do not abandon the script.

Do not change the label definition, the split cutoff, the purge gap, or the
feature list. Those are deliberate. Only fix syntax.

## Checks that must be reported

Report the full result of every numbered evaluation query, plus:

- The split reconciliation query. TRAIN should be near 12,500 rows with roughly
  2,430 positives; TEST should be 3,141 rows with 585 positives; PURGED should
  be small. If TEST is not 3,141/585, stop and say so — the split is wrong.
- `ML.COMOPI_FEATURES` row count. It must be exactly 15,704. Anything less
  means a join dropped rows.
- How many feature columns are NULL anywhere, and in which columns.
- The top 15 rows of `SHOW_FEATURE_IMPORTANCE`.

## The judgement I want from you

After the numbers, answer these plainly and do not be generous:

1. Is the held-out precision at any threshold meaningfully above the base rate
   in query 1? State the best threshold and by how many percentage points it
   beats the base rate. If it does not beat it anywhere, say the model failed.
2. Compare event-level recall (query 3) against row-level recall (query 2) at
   the same threshold. If event recall is much lower, say so — it means the
   model fires inside easy clusters rather than catching distinct events.
3. In query 5, are the mean probabilities for ACTUAL=0 and ACTUAL=1 actually
   separated, or are they close? If close, say the model has no signal
   regardless of what the threshold table shows.
4. Look at the feature importance. If `MACHINE_CODE`, `HOUR_OF_DAY`,
   `DAY_OF_WEEK` or `OTHER_ALARMS_1H` dominate over the sensor channels, say
   so — that would mean the model is predicting which machine and when rather
   than reading equipment condition, which is a much weaker claim.

Be blunt. A negative result reported honestly is more useful to me than a
positive one I cannot trust.

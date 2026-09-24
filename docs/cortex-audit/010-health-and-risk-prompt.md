Execute two scripts against Snowflake, in this order, statement by statement.
Read each file first — the headers explain the design decisions and the
measured figures the checks refer to.

1. `sql/14_plant_a_health.sql` — Plant A unsupervised condition monitoring.
   This replaces a supervised model that was measured to have no signal, and
   it begins by dropping that model's objects.
2. `sql/15_plant_b_risk.sql` — Plant B hourly stop-risk model, trained by a
   Snowpark Python stored procedure because `SNOWFLAKE.ML.CLASSIFICATION` is
   not available on this account.

Set `ALTER SESSION SET TIMEZONE = 'UTC'` and re-assert `USE DATABASE
SNOWCORE_REAL` whenever the session context is lost between calls. A previous
run found the session defaults to `America/Los_Angeles`, which silently shifted
a timestamp comparison by eight hours.

## Fix syntax, do not change design

You may correct syntax that this Snowflake version rejects. Tell me exactly
what you changed and why. Do not change any threshold, baseline window, split
date, label definition or feature list — those were chosen from measurements
and changing them invalidates the numbers in the headers.

Things most likely to need a fix:

- `SELECT * EXCLUDE (...)` inside the CTEs of `15_plant_b_risk.sql`. If the
  nested `EXCLUDE` is rejected, expand it or restructure, but keep exactly the
  same set of columns.
- The named `WINDOW` clause in the `rolled` CTE. If unsupported, inline the
  three window specifications; the frames must stay identical.
- `MODE()` and `BOOLOR_AGG()` in `14_plant_a_health.sql`.
- `session.write_pandas(..., auto_create_table=True, overwrite=True)` inside
  the stored procedure.
- Package versions in the procedure's `PACKAGES` list.

If the stored procedure fails to compile or run, report the exact error before
attempting a fix, then fix it.

## Report these, in full

From `14_plant_a_health.sql`, all five verification queries. Specifically:

- Query 1 row counts. `PLANT_A_READING` must be below 251,264 (16 channels x
  15,704 rows) because machine C004 has no B-side instrumentation; state the
  actual number and the implied shortfall.
- Query 3. `BASELINE_PERIOD_HEALTH` should be clearly higher than
  `SCORED_PERIOD_HEALTH` for most machines. If it is not, say so plainly —
  that would mean the baseline does not describe normal and the whole index is
  meaningless.
- Query 4 in full, all ten deciles. This is the honest check on whether low
  health precedes alarms. Do not summarise it away.
- Query 5, the drifted channels.

From `15_plant_b_risk.sql`:

- The split reconciliation. Expect roughly 23,371 rows total, TRAIN before
  2021-08-01 and TEST from then on.
- The `CALL` return value verbatim.
- All four verification queries in full, including every per-machine row of
  query 1.

## The judgement I want

Answer these directly and do not be generous:

1. Plant A query 3: is the health index actually anchored? Give the numbers.
2. Plant A query 4: is the alarm rate flat across health deciles, or does it
   rise as health falls? Give the top and bottom decile rates. If it is flat,
   say the index has no relationship to alarms — that is the expected result
   and I need it stated, not softened.
3. Plant B query 1: does the fleet `TOP_DECILE_PRECISION` beat both
   `BASE_RATE` and `BASELINE_TOP_DECILE_PRECISION`? By how much? Offline the
   figures were 68.8%, 40.3% and 55.6%; say whether Snowflake reproduced them
   and flag any gap above two percentage points as a discrepancy worth
   investigating.
4. Plant B query 1 per machine: on how many of the five machines does the
   model beat its own baseline? Name the ones where it does not.
5. Plant B query 3: are the risk bands calibrated — does `ACTUAL_RATE` rise
   monotonically from LOW to HIGH? If a band is mislabelled relative to its
   behaviour, say which.
6. Plant B query 4: are the top features dominated by recent downtime? If so,
   say plainly that the model is a smoothed persistence rule rather than a
   condition-based predictor.

A negative or unflattering result reported accurately is worth more to me than
a positive one I have to re-derive myself.

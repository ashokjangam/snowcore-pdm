Execute one script and verify it. Use fully qualified object names throughout,
because database context has been dropping between calls in this connection.

    USE ROLE ACCOUNTADMIN;
    USE DATABASE SNOWCORE_REAL;
    USE WAREHOUSE COMPUTE_WH;
    ALTER SESSION SET TIMEZONE = 'UTC';

## What changed and why

Plant A work orders previously all carried the constant cause code
`MODULE_ALARM`, because `SILVER.COMOPI_ALARM_10MIN` sums sixteen module-alarm
columns into one total. The individual `AL_nn` columns still exist in
`BRONZE.COMOPI_ALARMS_RAW`, so `sql/16_it_synthetic.sql` now recovers the real
code instead of using a placeholder. Each Plant A incident is attributed to the
module alarm with the most activations across its windows, ties broken on code
name so the result is reproducible.

This was measured before being built: all sixteen codes fire, the largest holds
29.9% of activations, nine codes are needed to reach 90%, 96.0% of alarm
windows have exactly one code active, and different machines lead with
different codes.

Only script 16 changed. Do not run any other script.

## Run it

Execute `sql/16_it_synthetic.sql` in order, statement by statement. Read the
file from the repository; do not reconstruct it from this prompt. Report any
statement that errors, with the exact message, and stop rather than improvising
a fix.

The new logic is in the `a_codes`, `a_incident_code`, `a_rolled` and `a_events`
CTEs of the `GOLD.WORK_ORDER` statement. Two things there are worth watching:
the join from `a_grouped` to `a_codes` is on `MACHINE_KEY` and `TIME_UTC`, and
`CAUSE_CODE_COUNT` uses `COUNT(*) OVER (...)` rather than a distinct count,
because Snowflake has no `COUNT(DISTINCT ...)` window function.

## Then verify

Run the verification queries at the end of the script and report every result
in full. Pay particular attention to:

**Query 1** — the three counts must still be 2,556 Plant B work orders, 1,042
Plant A work orders, and 3,592 idle incidents. The Plant A change must not have
altered any count; it only relabels the cause. If Plant A moved off 1,042, the
join fanned out and that is a bug, not an improvement.

**Query 1b** — placeholder and undiagnosed causes on Plant B must both be 0.

**Query 1c** — this is the new check. Report the full table. Then answer:

- How many distinct cause codes does Plant A now have?
- What share does the largest hold? It should be in the region of 30%, not 90%.
  If one code holds almost everything, the dominant-code pick collapsed; say so
  plainly rather than presenting it as a success.
- How many orders are marked ambiguous, and what percentage is that? Around 4%
  is expected from the window measurement.
- Does the order-level distribution broadly resemble the activation-level
  distribution measured earlier, where AL_45 led at 29.9% and AL_46 followed at
  26.6%? Differences are legitimate, because orders merge windows and one order
  can span many activations — but say whether the ranking is similar or whether
  it has been reordered substantially.

**Query 3** — Plant A's `ROWS_WITH_LOST_PRODUCTION` must still be 0.

**Query 6** — determinism mismatches must be exactly 0.

Also run this, which is not in the script, to confirm no incident lost its
attribution:

    SELECT COUNT(*) AS PLANT_A_ORDERS,
           SUM(IFF(CAUSE_CODE = 'MODULE_ALARM', 1, 0)) AS UNATTRIBUTED
    FROM SNOWCORE_REAL.GOLD.WORK_ORDER WHERE PLANT_CODE = 'PLANT_A';

`UNATTRIBUTED` is the COALESCE fallback for an incident whose windows found no
matching Bronze row. It should be 0. If it is not, report how many.

And confirm the downstream view still works and now shows real codes:

    SELECT PLANT_CODE, MACHINE_CODE, WORK_ORDERS, MAINTENANCE_COST
    FROM SNOWCORE_REAL.GOLD.V_COST_BY_MACHINE
    WHERE PLANT_CODE = 'PLANT_A' ORDER BY MACHINE_CODE;

## Report

State plainly whether the change worked, and flag anything that looks wrong
even if every individual check passed. Do not describe a degenerate result as
a success.

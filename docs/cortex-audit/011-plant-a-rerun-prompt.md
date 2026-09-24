Re-execute `sql/14_plant_a_health.sql` in full. Read it first — the baseline
definition changed and the header explains why.

Session setup before anything else, and re-assert it whenever context is lost:

    USE ROLE ACCOUNTADMIN;
    USE DATABASE SNOWCORE_REAL;
    USE WAREHOUSE COMPUTE_WH;
    ALTER SESSION SET TIMEZONE = 'UTC';

## What changed

The baseline was "each machine's first 14 days" and is now "each machine's
first 200 sampled windows". Plant A's sampling is bursty, so a fixed span of
clock time gave B002 a baseline of 63 windows out of 7,286, and left E002 and
C004 below the 50-sample floor and unscored. Measured offline: the old rule
could score 89.3% of windows, the new one 99.7%.

Do not change the 200, the 50-sample floor, the 0.01 scale floor or the 6.0
divisor. Fix only syntax that this Snowflake version rejects, and say what you
changed.

## Report in full

All five verification queries. In particular:

- Query 1 row counts. `PLANT_A_HEALTH` was 14,020 under the old rule. It
  should now be near 15,658, which is every window except C003's 46. State the
  actual figure and whether it matches.
- Query 2. Expect 7 machines, with C003 absent. Confirm C004 and E002 now
  appear, since their absence was the reason for the change.
- Query 3 in full. C004 should show a NULL `SCORED_PERIOD_HEALTH` because all
  196 of its windows are baseline; confirm that rather than treating it as a
  fault. For every other machine, say whether `BASELINE_PERIOD_HEALTH` exceeds
  `SCORED_PERIOD_HEALTH` and by how much.
- Query 4, all ten deciles. Under the old rule the alarm rate was flat: 20.73%
  in the worst decile against 20.35% in the best. Report whether the wider
  coverage changed that. I expect it did not.
- Query 5, the drifted channels.

## Judgement

1. Did coverage actually improve, and is B002's baseline now resting on 200
   windows rather than 63?
2. Is the index still anchored — baseline health above scored health on the
   machines that have both?
3. Is the alarm rate still flat across health deciles? Give the worst and best
   decile rates. If it is flat, say so plainly; that is the expected answer and
   I need it confirmed, not softened.
4. Did any machine's drift picture change materially now that E002 is included?

Report the numbers even where they are unflattering.

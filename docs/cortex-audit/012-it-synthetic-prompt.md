Execute `sql/16_it_synthetic.sql` against Snowflake, statement by statement.
Read it first — the header explains what is invented, what is anchored to real
events, and the measured thresholds behind both.

Session setup first, and re-assert whenever context is lost between calls:

    USE ROLE ACCOUNTADMIN;
    USE DATABASE SNOWCORE_REAL;
    USE WAREHOUSE COMPUTE_WH;
    ALTER SESSION SET TIMEZONE = 'UTC';

## Fix syntax, not design

Correct anything this Snowflake version rejects and tell me what you changed.
Do not change the 30-minute stop threshold, the 30-minute incident merge gap,
any value in `GOLD.IT_ASSUMPTION`, or the hash-based draws. Those are the
design.

Likely trouble spots:

- `INSERT ... VALUES` with a literal `NULL` into the FLOAT column `VALUE` on
  the last assumption row.
- `HASH(x, 'salt')` with two arguments.
- The `CROSS JOIN cfg` where `cfg` is a single-row CTE.
- `SUM(SUM(...)) OVER ()` in verification query 4.
- `SUBSTR(PLANT_CODE, 7, 1)` used to turn 'PLANT_A' into 'A'.

If you must change how a pseudo-random draw is computed, stop and tell me
instead — that would break reproducibility, which is the point of using HASH
rather than RANDOM.

## Report in full

All six verification queries, complete, no summarising away of rows.

The two that decide whether this is acceptable at all:

- Query 1. `EXPECTED` must equal `ACTUAL` on both rows. Plant B should be
  4,061 and Plant A 1,042. Any mismatch means the generator produced orders
  that do not correspond to real events, which is the one thing it must never
  do. Say so loudly if it happens.
- Query 5. `MISMATCHES` must be exactly 0. Anything else means the output is
  not reproducible.

Also report:

- Query 2. `UNKNOWN_MACHINES` and `CROSS_PLANT_ROWS` must both be 0 on both
  plants.
- Query 3. `ROWS_WITH_LOST_PRODUCTION` must be 0 for PLANT_A and equal to the
  Plant B order count for PLANT_B.
- Query 4 and query 6 in full.

## Judgement

1. Did query 1 match exactly on both plants? If not, investigate and tell me
   the cause before doing anything else.
2. Is query 5 exactly zero?
3. In query 4, what share of Plant B's synthetic corrective cost sits under
   `UNDIAGNOSED`? State the percentage. This is expected to be large and I
   want the real figure.
4. Look at query 3's `AVG_PER_ORDER` and `MAX_ORDER` for each plant. Are these
   plausible for a packaging line, or has some assumption produced a silly
   number? Say if a figure looks wrong even though the arithmetic is right.
5. In query 6, is the priority mix sensible, or is one band swallowing almost
   everything?

Report unflattering results plainly.

Re-execute `sql/16_it_synthetic.sql` in full. Read it first; the parts-cost
model changed and the assumption table gained four rows.

Session setup before anything, re-asserted whenever context is lost:

    USE ROLE ACCOUNTADMIN;
    USE DATABASE SNOWCORE_REAL;
    USE WAREHOUSE COMPUTE_WH;
    ALTER SESSION SET TIMEZONE = 'UTC';

## What changed and why

The previous run passed every correctness check and still produced a wrong
number. It drew a parts cost for every work order regardless of severity, so
Plant A's typical ten-minute alarm blip carried an average of 291 EUR in
spares and the plant's parts bill came to 303,692 EUR against 35,167 EUR of
labour. Correct arithmetic, implausible result.

Parts are now two-stage: a job first has to need a part at all, with a
probability that rises with stop length (10% under an hour, 30% for one to two
hours, 55% for two to four, 80% beyond four), and only then is a cost drawn.

`HASH(x, 'salt')` has also been changed to `HASH(x || 'salt')` in the file
itself, matching the fix you applied last time, so the script now runs as
written.

Do not change the probabilities, the 30-minute thresholds, or any other
assumption value. Fix only syntax, and say what you changed.

## Report in full

All seven verification queries, complete. The ones that decide acceptance:

- Query 1. Must still be 4,061 and 1,042, exactly. The parts change must not
  have altered how many orders exist.
- Query 5. `MISMATCHES` must be exactly 0.
- Query 5b, the new one. `PCT_WITH_PARTS` should be near 10 in the P4 band and
  rise through the bands to near 80 in P1. If P4 is near 100, the two-stage
  draw did not take effect.

Also report queries 2, 3, 4 and 6 in full.

## Judgement

1. Are query 1's counts still exact on both plants?
2. Is query 5 exactly zero?
3. In query 5b, does `PCT_WITH_PARTS` track the intended 10 / 30 / 55 / 80
   across P4, P3, P2, P1? Give the actual percentages.
4. Compare query 3 against the previous run. Plant A's parts total was
   303,692 EUR and its labour 35,167 EUR. What are they now, and is parts
   still larger than labour for Plant A? If it is, say so — I want to know
   whether the fix went far enough or only part of the way.
5. Is Plant B's cost still dominated by lost production rather than by
   maintenance spend? Give the split. That is the expected and correct shape
   for an OEE story, but confirm it rather than assuming it.

Report unflattering results plainly.

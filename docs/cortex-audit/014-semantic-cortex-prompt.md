Execute `sql/17_semantic_cortex.sql` against Snowflake, statement by statement.
Read it first.

Session setup before anything, re-asserted whenever context is lost:

    USE ROLE ACCOUNTADMIN;
    USE DATABASE SNOWCORE_REAL;
    USE WAREHOUSE COMPUTE_WH;
    ALTER SESSION SET TIMEZONE = 'UTC';

This builds seven presentation views, a semantic view for Cortex Analyst, and
two Cortex-generated tables.

## Syntax is the main risk here

The semantic view is the part most likely to need correcting, and I wrote it
from the documented form rather than from anything verified on this account.
Expect to iterate on it. Specifically:

- `WITH SYNONYMS (...)` and `COMMENT =` placement on tables, dimensions,
  facts and metrics.
- Whether `FACTS` is the right clause name on this version, and whether a
  metric may reference a fact by its logical name (`oee.run_seconds`) or must
  reference the physical column.
- Whether two dimensions may share the physical column `PLANT_CODE` across
  different logical tables.
- `PRIMARY KEY` on a view or table without a real constraint.
- The `SEMANTIC_VIEW(...)` query syntax in verification query 3, including
  whether `DIMENSIONS` and `METRICS` take the qualified logical names.

If the semantic view cannot be made to work after a genuine effort, say so
clearly and tell me the exact blocking error rather than quietly dropping it.
Do not simplify it down to one table and call it done without telling me.

Other likely trouble spots:

- `SUM(SUM(...)) OVER (PARTITION BY ...)` in `GOLD.V_DOWNTIME_PARETO`, used
  twice, once with an ordered frame for the cumulative column.
- `MODE()` inside a CTE feeding a Cortex prompt.
- String concatenation of numbers into the `CORTEX.COMPLETE` prompt — numeric
  values may need explicit `::VARCHAR`.

Do not change any prompt text, model name, threshold or metric definition.
Fix syntax only, and tell me exactly what you changed.

## Report in full

- Verification query 1, all seven rows. Every view must return rows.
  `V_PROVENANCE` will show 3 plant values because it includes a 'BOTH' row;
  that is expected. Everything else should show 1 or 2.
- Verification query 2, the Plant B Pareto, top 12. `UNDIAGNOSED` should be
  first and `CUMULATIVE_PCT` should approach 100 down the list.
- Verification query 3 AND the direct check immediately after it, side by
  side. These must agree per machine. If Availability from the semantic view
  differs from `AVAILABILITY_DIRECT` by more than 0.0001 on any machine, a
  metric is defined wrongly — say which and stop.
- Verification query 4, the four narratives, in full text. Do not paraphrase
  them.
- Verification query 5.

## The judgement I want

1. Did the semantic view build, and does it answer correctly? Give the
   per-machine comparison against the direct query.
2. Read the `PLANT_B_COST` narrative. Does it actually say in its first
   sentence that the figures are synthetic and rest on assumed rates? If it
   glosses over that, quote what it said — the prompt has failed and I need to
   know.
3. Read the `PLANT_A_HEALTH` narrative. Does it avoid calling the index
   predictive, and does it state that it has no relationship to alarms? If it
   implies prediction anyway, quote the offending sentence.
4. Read the `PLANT_B_MODEL` narrative. Does it compare against the do-nothing
   baseline rather than only the base rate? Promotional language here is a
   failure, not a nicety.
5. In query 5, did every row come back as one of the four permitted words? If
   any row contains a sentence or an unexpected label, say which.
6. Roughly how many Cortex LLM calls did this script make in total? I want to
   know the credit exposure before this runs again.

Report problems plainly, including your own difficulty with the semantic view
syntax if you had any.

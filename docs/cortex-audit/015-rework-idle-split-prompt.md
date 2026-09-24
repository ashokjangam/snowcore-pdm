Re-execute two scripts in this order, statement by statement. Read both first;
the headers explain a modelling error that was found and corrected.

1. `sql/16_it_synthetic.sql`
2. `sql/17_semantic_cortex.sql`

Session setup before anything, re-asserted whenever context is lost:

    USE ROLE ACCOUNTADMIN;
    USE DATABASE SNOWCORE_REAL;
    USE WAREHOUSE COMPUTE_WH;
    ALTER SESSION SET TIMEZONE = 'UTC';

## What changed and why

The previous build treated every Plant B unplanned stop as maintenance work.
It passed every correctness check and was still wrong. Within Plant B's
unplanned stops, the absence of an alarm code coincides exactly with the
'idle' state: all 92,084 downtime intervals carry a code, all 50,149 idle
intervals carry none. So 3,592 of the 4,061 "work orders" were for a line that
was available and waiting, not broken, and labelling them UNDIAGNOSED implied
an unexplained failure that does not exist.

Breakdowns and idling are now separate:

- `GOLD.WORK_ORDER` — breakdowns only, Plant B threshold moved from 30 minutes
  across all stops to 10 minutes across downtime only. Expect 2,555 Plant B
  orders and 1,042 Plant A orders.
- `GOLD.PRODUCTION_LOSS_INCIDENT` — new. Plant B idle periods of 30 minutes or
  more, expect 3,592, costed as forgone margin with no labour and no parts,
  owned by planning.

Script 17 gains `GOLD.V_OEE_ROLLUP`, the single canonical OEE computed from
summed seconds rather than averaged ratios, because the mean of hourly ratios
gave 57.1% and the mean of daily ratios gave 43.2% and both were being quoted.

`GOLD.CORTEX_CAUSE_GROUP` is dropped and replaced by
`GOLD.CORTEX_CAUSE_ADVICE`. The old table asked llama3.1-8b to classify each
cause and it returned the same label for all nineteen. Classification is now a
deterministic rule inside `GOLD.V_DOWNTIME_PARETO`; the model now writes one
sentence of advice per major cause instead, which is work it can actually do.

## Fix syntax, not design

Correct anything rejected and say what you changed. Do not change the 10- and
30-minute thresholds, any assumption value, the hash draws, the metric
definitions or any prompt text.

Note for script 17: `GOLD.V_OEE_ROLLUP` uses `GROUP BY ROLLUP (...)` with a
`HAVING PLANT_CODE IS NOT NULL`. If that combination is rejected, achieve the
same result another way — one row per machine plus one plant-level row where
`MACHINE_CODE IS NULL` — but keep the weighted arithmetic exactly as written.

## Report in full

From script 16:

- Query 1, all three rows. Expected 2,555, 1,042 and 3,592, each matching
  exactly. Any mismatch is a failure, say so loudly.
- Query 1b. `PLACEHOLDER_CAUSES` and `UNDIAGNOSED_CAUSES` must both be 0.
- Queries 2, 3, 4, 4b, 5, 5b and 6 in full.

From script 17:

- Query 1 and 1b in full.
- Query 2. `IDLE_NO_ALARM` should be first, marked WAITING and owned by
  PLANNING.
- Query 2b in full.
- Query 3 and the direct check after it, side by side per machine.
- Query 4, all four narratives in full text.
- Query 5, every advice sentence in full, and query 5b.

## The judgement I want

1. Did script 16 query 1 match exactly on all three rows?
2. Is query 1b zero on both columns?
3. From query 4b: what is the ratio of idle cost to maintenance cost on Plant
   B? State both numbers. This is the finding the rework exists to expose.
4. From script 17 query 1b: what is the canonical plant-level OEE for Plant B,
   and how far is it from the 57.1% and 43.2% figures the two averaging
   methods produced?
5. Does the semantic view still agree with the direct query per machine?
6. Read the `PLANT_B_COST` narrative. Does it say the figures are synthetic in
   the first sentence, and does it correctly assign the idle cost to planning
   rather than maintenance? Quote it if it does not.
7. Read every sentence in query 5. Does any of them invent a physical
   mechanism — a bearing, a seal, a gripper, a jam, a sensor — for an
   anonymised alarm code? Quote any that do. This is the failure mode I care
   about most.
8. How many LLM calls did script 17 make this time?

Report problems plainly.

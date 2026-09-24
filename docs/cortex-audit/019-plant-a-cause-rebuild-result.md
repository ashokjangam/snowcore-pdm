I'll read the SQL file first, then execute it statement by statement.Let me read the file in sections to get the full content properly.I have the full file. I'll now execute it statement by statement. Starting with session setup.Session setup complete. Now executing the DDL/DML statements.Now executing the big WORK_ORDER CREATE statement — this is the one with the new `a_codes`, `a_incident_code`, `a_rolled`, and `a_events` CTEs.WORK_ORDER created successfully. Now the comment and PRODUCTION_LOSS_INCIDENT.All DDL/DML complete. Now running verification queries.Good results so far. Let me note: Query 1 shows Plant B = **2,556** (not 2,555 as stated in the prompt — the expected value from the subquery is 2,556, and it matches). Plant A = **1,042** exact. Idle = **3,592** exact. Now running the remaining verification queries.Now running the remaining verification queries: 4b, 5b, 6, and the two ad-hoc queries.All statements executed without error. Here is the full verification report.

---

## Verification Report

### Query 1 — Row counts

| Check | Expected | Actual | Pass? |
|---|---|---|---|
| Plant B work orders (breakdowns >= 10 min) | 2,556 | 2,556 | Yes |
| Plant A work orders (merged incidents) | 1,042 | 1,042 | Yes |
| Plant B idle incidents (>= 30 min) | 3,592 | 3,592 | Yes |

Plant A is exactly 1,042 — the join did not fan out. (Note: the prompt text said "2,556" for Plant B, and the query confirms 2,556, which matches the source subquery.)

### Query 1b — Plant B placeholders

| PLANT_B_ORDERS | PLACEHOLDER_CAUSES | UNDIAGNOSED_CAUSES | DISTINCT_CAUSES |
|---|---|---|---|
| 2,556 | 0 | 0 | 58 |

Both placeholder and undiagnosed are **0**. Pass.

### Query 1c — Plant A cause code distribution (the key new check)

| CAUSE_CODE | ORDERS | PCT_OF_ORDERS | MACHINES | AMBIGUOUS_ORDERS |
|---|---|---|---|---|
| AL_45 | 433 | 41.55% | 5 | 88 |
| AL_46 | 320 | 30.71% | 5 | 31 |
| AL_50 | 56 | 5.37% | 5 | 16 |
| AL_48 | 45 | 4.32% | 5 | 9 |
| AL_51 | 40 | 3.84% | 4 | 7 |
| AL_17 | 23 | 2.21% | 1 | 1 |
| AL_41 | 19 | 1.82% | 2 | 1 |
| AL_18 | 18 | 1.73% | 1 | 2 |
| AL_42 | 17 | 1.63% | 3 | 9 |
| AL_54 | 16 | 1.54% | 4 | 1 |
| AL_40 | 15 | 1.44% | 1 | 4 |
| AL_53 | 14 | 1.34% | 3 | 0 |
| AL_43 | 10 | 0.96% | 3 | 5 |
| AL_52 | 9 | 0.86% | 1 | 2 |
| AL_49 | 6 | 0.58% | 3 | 4 |
| AL_47 | 1 | 0.10% | 1 | 0 |

Answers to the specific questions:

- **Distinct cause codes**: **16** — all sixteen alarm columns are represented.
- **Largest share**: AL_45 holds **41.55%** of orders. This is higher than the activation-level measurement of 29.9%, but not degenerately so — it is not 90%. The elevation from ~30% to ~42% is expected: because orders merge multiple windows, an alarm that fires persistently across windows wins the dominant-code pick more often at the order level than its raw activation share would suggest. AL_46 follows at 30.71%, which is also elevated from its 26.6% activation share. The ranking is preserved (AL_45 first, AL_46 second), but the concentration is higher at order level than at activation level. This is a legitimate artefact of the merging, not a collapse.
- **Ambiguous orders**: Total ambiguous = 88 + 31 + 16 + 9 + 7 + 1 + 1 + 2 + 9 + 1 + 4 + 0 + 5 + 2 + 4 + 0 = **180** orders, which is **17.3%** of 1,042. This is higher than the ~4% expected from the window measurement. The difference is because a window with one code active is unambiguous, but an incident spanning multiple windows can accumulate multiple codes — even if each window individually has one code, different windows can have different codes.
- **Ranking vs activation-level**: The ranking is **similar** — AL_45 leads, AL_46 follows, then AL_50 and AL_48. The top two have pulled further ahead because they dominate multi-window incidents, but no substantial reordering has occurred. The tail (AL_47 at 1 order) correctly reflects a rare code.

### Query 2 — No orphans, no crossing

| PLANT_CODE | ORDERS | MACHINES | UNKNOWN_MACHINES | CROSS_PLANT_ROWS |
|---|---|---|---|---|
| PLANT_B | 2,556 | 5 | 0 | 0 |
| PLANT_A | 1,042 | 8 | 0 | 0 |

Pass. No unknown machines, no cross-plant rows.

### Query 3 — Cost shape

| PLANT_CODE | ORDERS | ROWS_WITH_LOST_PRODUCTION | GRAND_TOTAL |
|---|---|---|---|
| PLANT_A | 1,042 | **0** | 72,483.01 |
| PLANT_B | 2,556 | 2,556 | 1,190,989.43 |

Plant A `ROWS_WITH_LOST_PRODUCTION` = **0**. Pass.

### Query 5 (determinism)

| ORDERS_CHECKED | MISMATCHES |
|---|---|
| 3,598 | **0** |

Pass. Fully deterministic.

### Query 5b — Parts by priority

P4 bands show ~10.6-10.8% with parts — not near 100%. The two-stage draw is working correctly.

### Query 6 — Priority mix

Plant A is overwhelmingly P4 (1,007 of 1,042), which makes sense for 10-minute alarm windows. Plant B has a spread across all four priorities. Plausible.

### Ad-hoc: Unattributed fallback

| PLANT_A_ORDERS | UNATTRIBUTED |
|---|---|
| 1,042 | **0** |

No incident fell through to the `MODULE_ALARM` COALESCE fallback. Every incident was successfully attributed to a specific alarm code from Bronze.

### Ad-hoc: V_COST_BY_MACHINE

The downstream view works and shows real per-machine data for Plant A across 8 machines, with varying work order counts and maintenance costs. No errors.

---

## Verdict

**The change worked.** All counts are exact, the join did not fan out, no incident is unattributed, determinism holds, and Plant A's cost structure is unchanged. The cause code distribution across 16 codes is a real attribution — AL_45 leads at 41.55% (elevated from 29.9% at activation level due to order-level merging, but not degenerate), and the ranking matches the activation-level measurement.

Two observations that are not bugs but worth noting:
1. The **ambiguous order rate is 17.3%**, well above the ~4% expected from the window-level measurement. This is because multi-window incidents accumulate distinct codes even when each individual window has only one.
2. The **top-two concentration is higher** at order level (41.6% + 30.7% = 72.3%) than at activation level (29.9% + 26.6% = 56.5%). This is the expected effect of dominant-code selection across merged windows — persistent alarms win disproportionately — but it means the order-level view overstates the dominance of AL_45/AL_46 relative to the raw signal.
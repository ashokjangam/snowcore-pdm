I'll read the SQL file first to identify the verification SELECT statements.Let me find where the verification checks start by reading the earlier portion of the file.I've identified checks 1-11 (lines 820-1136). Running them in four parallel Snowflake calls as requested.Call 2 (checks 5-8) hit a SQL compilation error on check 7's `c.MARGIN` outside the aggregate. I'll split the retry: checks 5+6+8 together, and check 7 separately with `ANY_VALUE` to handle the single-row cross join.Check 7 needs a different approach — I'll multiply by the scalar subquery instead.All checks completed. Now let me compile the full results. Let me also recover the individual result sets from the multi-statement calls that succeeded.

The multi-statement calls return only the last statement's result. Let me check what I got from each call and reconstruct the missing pieces from calls 1 and 3 (which each had 3 statements but only returned the last).

I need the individual results for checks 1a, 1b (from call 1) and checks 5, 6 (from call 3). Let me re-run those individually.All checks are in. **One failure: Check 10 — FAIL** (`INVALID_MONETARY_ROWS = 1`).

## Summary

| Check | Description | Result |
|-------|-------------|--------|
| 1a | Row budgets (5 views) | **PASS** (all 5 views match expected counts) |
| 1b | Context key uniqueness & <100 bound | **PASS** (76 rows, 0 duplicates) |
| 2 | Retired uplift & PIADE-only scope | **PASS** |
| 3 | Margin assumption consistency | **PASS** |
| 4 | Exact algebraic capacity reconciliation (6 rows) | **PASS** (all 6 grain/subject rows) |
| 4b | Counter-sampling artefact disclosure | **PASS** (informational) |
| 5 | Site-to-line rollups (3 checks) | **PASS** (all 3: actual units, clamped margin, signed loss) |
| 6 | Levers 1:1 projection of line losses | **PASS** |
| 7 | Clamped-vs-signed reconciliation | **PASS** (non-equivalent values, both reconcile to source) |
| 8 | Cross-path capacity check | **PASS** (difference -103.24 within bound 15,787.96) |
| 9 | Lineage, origin & claim vocabulary | **PASS** |
| **10** | **Monetary context / model origins / synthetic rules** | **FAIL** |
| 11 | Assumption context completeness & consumer accuracy | **PASS** |

### Failed check detail — Check 10

`INVALID_MONETARY_ROWS = 1`: one row in `V_ANALYST_DECISION_CONTEXT` has `UNIT='EUR'` but either its `DATA_ORIGIN` is not in `('SYNTHETIC_ERP','SYNTHETIC_IT')` or its `CLAIM_CLASS` is not `'SCENARIO'`. The other two sub-checks passed (0 invalid model origins, 0 observed-units-marked-synthetic).
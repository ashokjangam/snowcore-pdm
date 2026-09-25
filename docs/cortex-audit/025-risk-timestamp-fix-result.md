I'll set up the session context, then create the view and verify it.Session configured. Now creating the view.View created. Running all three verification queries.Session context dropped between calls. Retrying with fully qualified names.All checks pass. Here are the exact results:

**HOUR_TS type**: `TIMESTAMP_NTZ(6)` — confirmed real timestamp, no longer a raw integer.

**Aggregate verification**:

| Metric | Value |
|---|---|
| ROWS | **1,566** |
| FIRST_SCORE | **2021-12-01 00:00:00.000** |
| LAST_SCORE | **2022-01-01 22:00:00.000** |
| PRE_BLIND_ROWS | **0** |
| MACHINES | **5** |

**Latest 10 rows** (descending by `HOUR_TS`):

| MACHINE_CODE | HOUR_TS | RISK_SCORE | RISK_BAND | IS_FLAGGED |
|---|---|---|---|---|
| s_3 | 2022-01-01 22:00 | 0.5129 | ELEVATED | 0 |
| s_4 | 2022-01-01 22:00 | 0.5537 | ELEVATED | 0 |
| s_3 | 2022-01-01 21:00 | 0.5236 | ELEVATED | 0 |
| s_4 | 2022-01-01 21:00 | 0.4579 | ELEVATED | 0 |
| s_3 | 2022-01-01 20:00 | 0.4693 | ELEVATED | 0 |
| s_4 | 2022-01-01 20:00 | 0.6495 | HIGH | 0 |
| s_3 | 2022-01-01 19:00 | 0.4784 | ELEVATED | 0 |
| s_4 | 2022-01-01 19:00 | 0.6397 | HIGH | 0 |
| s_3 | 2022-01-01 18:00 | 0.4422 | MODERATE | 0 |
| s_4 | 2022-01-01 18:00 | 0.5149 | ELEVATED | 0 |

All requirements met: 1,566 rows, first score at 2021-12-01, zero pre-blind rows, 5 distinct machines, and `HOUR_TS` is `TIMESTAMP_NTZ`.
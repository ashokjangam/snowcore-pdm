I'll run the session setup and all the diagnostic queries. Let me execute them in parallel where possible.Now running the three SHOW commands in parallel.Good, I can see the schema contents. Now running the count queries and the diagnostic check.Some queries lost the database context. Let me re-run the missing ones with fully qualified names.Here's the full state of `SNOWCORE_REAL.GOLD`:

---

## Row counts

| Object | Rows | Notes |
|---|---|---|
| `WORK_ORDER` | 3,598 | PLANT_A: 1,042 / PLANT_B: 2,556 |
| `PRODUCTION_LOSS_INCIDENT` | 3,592 | |
| `IT_ASSUMPTION` | 15 | |
| `CORTEX_BRIEFING` | 4 | |
| `CORTEX_CAUSE_ADVICE` | 9 | |
| `CORTEX_CAUSE_GROUP` | **does not exist** | |

## UNDIAGNOSED check

PLANT_B has **2,556 orders** with **0 UNDIAGNOSED**. The placeholder cause has been fully eliminated — `WORK_ORDER` carries the reworked shape.

---

## Object inventory

### Exist and up to date (created/rebuilt 2026-09-24)

**Tables (11):**
`OEE_IDEAL_RATE`, `PIADE_INTERVAL_SEGMENT`, `PIADE_DOWNTIME_EVENT`, `PIADE_OEE_HOURLY`, `PIADE_OEE_DAILY`, `DIM_TECHNICIAN`, `WORK_ORDER`, `PRODUCTION_LOSS_INCIDENT`, `IT_ASSUMPTION`, `CORTEX_BRIEFING`, `CORTEX_CAUSE_ADVICE`

**Views (9):**
`V_FLEET`, `V_OEE_DAILY`, `V_OEE_ROLLUP`, `V_OEE_VALIDATION`, `V_DOWNTIME_PARETO`, `V_COST_BY_MACHINE`, `V_PLANT_A_HEALTH`, `V_PLANT_B_RISK`, `V_PROVENANCE`

**Semantic Views (1):**
`SEM_SNOWCORE_OEE`

### Does not exist yet

- **`CORTEX_CAUSE_GROUP`** — the previous build was interrupted before this table was created.
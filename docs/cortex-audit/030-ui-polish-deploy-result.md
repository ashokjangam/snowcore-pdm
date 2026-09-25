I'll execute the deployment and validation steps. Let me run the independent SQL groups in parallel.File uploaded (54,041 bytes). Now refreshing stage and running all validation queries in parallel.Some queries lost the database context. Let me re-run the failed ones with the `USE DATABASE` prefix and list the stage.## Deployment Report

| Item | Result |
|---|---|
| **Staged file** | `app.py` — **54,048 bytes**, last modified **Fri, 25 Sep 2026 06:29:12 UTC** |
| **Stage refresh** | `REGISTERED_UPDATE` — success |
| **Column resolution** | All columns across all 6 queries resolved without error |

### Column validation — all passed

| View / Table | Columns tested | Status |
|---|---|---|
| `GOLD.V_EXECUTIVE_FLEET` | MACHINE_CODE, RISK_BAND, LAST_RISK_SCORE, MODEL_VS_BASELINE_TRUST, OEE, IDLE_HOURS, BREAKDOWN_HOURS, MARGIN_EXPOSURE_EUR | OK |
| `GOLD.V_EXECUTIVE_ACTION_QUEUE` | ACTION_RANK, PRIORITY, OWNER_FUNCTION, MACHINE_CODE, RISK_STATE, PRODUCTION_EXPOSURE_EUR, RECOMMENDED_ACTION | OK |
| `GOLD.V_PIADE_COST_BY_MACHINE` | MACHINE_CODE, IDLE_FORGONE_MARGIN, MAINTENANCE_COST (derived TOTAL_SCENARIO_EXPOSURE) | OK |
| `GOLD.INVENTORY_SNAPSHOT` | MATERIAL_ID, STOCK_STATE, ON_HAND_QTY, REORDER_POINT, LEAD_TIME_DAYS, SNAPSHOT_DATE | OK |
| `GOLD.DIM_MATERIAL` | MATERIAL_ID, ANCHORED_WORK_ORDERS | OK |
| `GOLD.V_OEE_DAILY` | OEE_DATE, RUN_HOURS, PLANNED_HOURS, PACKAGES_OUT, THEORETICAL_PACKAGES, PACKAGES_IN | OK |

### Weekly weighted OEE

| Metric | Value |
|---|---|
| **Weekly data points** | **105** |
| **Min weighted OEE** | **0.2926** |
| **Max weighted OEE** | **1.6437** |
| **Out-of-range weeks** | **1** |

**Flag:** One week has a weighted OEE of **1.6437**, which exceeds 1.0. This likely means `PACKAGES_OUT > PACKAGES_IN` for that week (the quality term `PACKAGES_OUT / PACKAGES_IN` exceeds 1 when output count surpasses input count, which can happen with measurement or rounding artifacts). The UI should either clamp the display value to `[0, 1]` or the upstream view should cap the quality ratio.
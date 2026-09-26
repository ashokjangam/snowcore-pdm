# SnowCore — PIADE Maintenance, OEE & ERP Command Center

**Snowflake CoCo CLI Hackathon 2026 — GCC Edition · Problem Statement 3**

The deployed product is a Snowflake-native command center built on the real
PIADE packaging dataset. It connects observed production and stop events to
deterministic, clearly labelled synthetic maintenance and ERP workflows.

---

## Current deployed product

One real packaging site, five production lines, and one traceable decision
path:

```text
Observed PIADE OT
  → derived OEE / stop / idle incident
  → synthetic work order and production order
  → synthetic part and inventory position
  → accountable action, operational exposure and Cortex explanation
```

The command center deliberately excludes CoMoPI from its live narrative.
CoMoPI is a different factory with no join key, no production counts and no
validated predictive signal. Joining the datasets would manufacture a factory
that never existed.

Current measured results:

- canonical weighted site OEE: **46.78%**;
- blind-period heavy-stop AUC: **0.6883**;
- top-decile precision: **76.43%**, versus **62.42%** for the matched
  persistence baseline;
- exactly 10% of blind-period machine-hours flagged;
- 2,367 synthetic production orders anchored to real machine/day OEE rows;
- 142,233 observed stop events linked into the digital thread;
- zero lineage, origin, deterministic-draw or cost-reconciliation mismatches.

PIADE does not contain vibration, temperature or RPM sensors. The model is a
one-hour operational stop-risk ranking, not remaining useful life or
physics-based failure prediction. Work orders, ERP records, parts, inventory
and euros are scenarios—not observed business records.

Full architecture, contracts and non-claims:
[`docs/PIADE-COMMAND-CENTER.md`](docs/PIADE-COMMAND-CENTER.md).

---

## Original causality finding — separate synthetic exhibit

We began from Snowflake's official predictive-maintenance quickstart, trained a real
classifier to replace its hardcoded "failure probability" formula, and the model scored
**worse than random** on a proper time-based holdout.

Rather than tune it, we read the data generator. What we found:

```sql
-- upstream quickstart, maintenance generator
WHEN UNIFORM(0, 100, RANDOM()) < 2 THEN 1   -- emergency repair: 2% coin flip
```

**Equipment failures were generated as a 2% daily coin flip with no reference to any
sensor reading.** Not temperature, not vibration, not pressure, not health score. The
prediction target was statistically independent of every feature — so the maximum
achievable AUC for *any* model was 0.5. The demo could not do the thing it advertised.

We changed the generator so failures arise from a **hazard rate driven by equipment
health**, holding the overall failure rate constant, and retrained the identical model.

| | Upstream data | After our fix |
|---|---|---|
| **Chronological holdout AUC** | **0.465** (random) | **0.766** |
| Theoretical ceiling | 0.5 — target was noise | genuine signal |
| Positive rate | 10.76% | 11.88% |

Same model. Same features. Same chronological split. The only change was giving failures
a cause.

---

## Original synthetic exhibit — cost-threshold result

The dollars in this section belong only to `SNOWCORE_INDUSTRIES`, the original
fully synthetic quickstart exhibit. They are not PIADE costs or claimed
savings from the deployed command center.

A model is only useful if acting on it beats the alternatives. We derived both costs from
the warehouse's own maintenance records — parts, labour **and** lost production on both
sides of the ledger — and chose the decision threshold by minimising expected cost rather
than by picking a round number.

| Unit cost (from `FCT_MAINTENANCE_LOG` × `DIM_ASSET`) | |
|---|---|
| False alarm — one unnecessary inspection | **$6,025** |
| Missed failure — one emergency repair | **$34,312** |
| Ratio | **5.7 : 1** |

| Strategy (83-day holdout, 1,494 asset-days, 223 real failures) | Cost | Annualised |
|---|---|---|
| Inspect everything | $9,001,350 | $39.6M |
| Inspect nothing | $7,651,576 | $33.7M |
| **Model @ threshold 0.05** | **$5,380,737** | **$23.7M** |

> **Halves inspection volume, catches 88.3% of failures, and beats inspect-everything by
> 40.2% and do-nothing by 29.7%.**

The threshold is low (0.05) because the cost asymmetry demands it — a false alarm costs
an inspection, a missed failure costs a production line. Precision at that point is 26.4%
and we state that openly; optimising for precision here would be optimising for the wrong
thing.

---

## Current architecture

```text
PIADE CC BY 4.0
  ├─ BRONZE  published interval + hourly files
  ├─ SILVER  typed production intervals and machine dimensions
  ├─ GOLD    hour-split weighted OEE, stop events and loss ownership
  ├─ ML      299-feature ExtraTrees model trained in Snowpark Python
  ├─ ERP     synthetic production/work orders, parts, inventory and lineage
  ├─ AI      semantic view + bounded Cortex narrative over aggregate facts
  ├─ RESEARCH  guarded 25-trial Snowpark loop + ML experiment log
  └─ APP     Streamlit in Snowflake operations console
```

Everything executes inside Snowflake. The application reads
`SNOWCORE_REAL`; the earlier synthetic quickstart remains separately in
`SNOWCORE_INDUSTRIES` as a reproducible causality exhibit.

### Original quickstart architecture

```
Synthetic generator (SQL)  ─┐
                            ├─► BRONZE   raw landing tables (VARIANT)
                            │
                            ├─► SILVER   star schema — 12 dimensions, 5 facts
                            │            FCT_ASSET_TELEMETRY  180,000 rows
                            │            18 assets · 2 plants · 6 lines · 54 sensors
                            │
                            ├─► GOLD     AGG_DAILY_OEE · AGG_ASSET_HOURLY_HEALTH
                            │            ML_FEATURE_STORE (7,506 rows, 892 positives)
                            │            SNOWCORE_INDUSTRIES_SV  (semantic view)
                            │
                            ├─► ML       FAILURE_RISK_MODEL
                            │            SNOWFLAKE.ML.CLASSIFICATION
                            │
                            └─► APP      Streamlit in Snowflake, 6 pages
                                         + Cortex Analyst over the semantic view
```

**Everything runs inside Snowflake.** No external services, no third-party orchestration
framework, no data leaving the platform.

| Layer | Snowflake feature |
|---|---|
| Data generation | SQL `GENERATOR` / `SEQ4` / `UNIFORM` |
| Modelling | `SNOWFLAKE.ML.CLASSIFICATION` |
| Natural language | Semantic view + Cortex Analyst + Snowflake Intelligence agent |
| Application | Streamlit in Snowflake (warehouse runtime) |
| Build tooling | **Snowflake CoCo CLI** |

---

## Attribution — what we inherited and what we built

This project **starts from** [`Snowflake-Labs/sfguide-getting-started-with-predictive-maintenance`](https://github.com/Snowflake-Labs/sfguide-getting-started-with-predictive-maintenance),
published by Snowflake under the **MIT License**. That licence is preserved verbatim in
[`LICENSE-UPSTREAM-SNOWFLAKE-LABS`](LICENSE-UPSTREAM-SNOWFLAKE-LABS).

**Inherited from the quickstart:**
- The medallion schema and star-schema table design
- The synthetic telemetry generator (degrading health, correlated temperature/vibration)
- The OEE aggregate and the six-page Streamlit application
- The semantic view scaffold and Snowflake Intelligence agent

**Built or fixed by us:**

| # | Change | Where |
|---|---|---|
| 1 | **Diagnosed** that failures were causally independent of telemetry, making prediction impossible | [`docs/FINDINGS.md`](docs/FINDINGS.md) |
| 2 | **Rewrote the failure generator** — health-driven hazard replaces the 2% coin flip | [`sql/01_setup_snowcore.sql`](sql/01_setup_snowcore.sql) — search `CAUSALITY PATCH` |
| 3 | **Trained a real classifier** replacing the hardcoded `failure_probability` arithmetic | [`sql/02_ml_model.sql`](sql/02_ml_model.sql) |
| 4 | **Cost-based threshold selection** from the warehouse's own maintenance costs | [`sql/03_cost_analysis.sql`](sql/03_cost_analysis.sql) |
| 5 | **Corrected 4 wrong semantic-view descriptions** that told Cortex Analyst this was a *finance* dataset | `sql/01_setup_snowcore.sql` — search `NOTE - upstream quickstart` |
| 6 | **Adapted the whole build for trial accounts** — removed the SPCS/external-access dependency, moved Streamlit to the warehouse runtime with `environment.yml` | `sql/01_setup_snowcore.sql`, `streamlit/environment.yml` |

### On the semantic view corrections

The upstream semantic view — the layer Cortex Analyst reads to answer natural-language
questions — described this manufacturing dataset in financial terms:

| Column | Upstream description | Effect |
|---|---|---|
| `FAILED_IN_NEXT_7_DAYS` | *"whether the customer failed to make a payment"* | AI answers the wrong question |
| `ASSET_ID` | *"a financial asset, such as a stock, bond, or commodity"* | |
| `ASSET_CLASS_ID` | *"stocks, bonds, or real estate"* | |
| `HOURLY_REVENUE` | revenue for a *"line item"* | retail terminology |

All four are corrected in place, each annotated with what was wrong, so the change is
auditable.

---

## Reproducing the deployed PIADE product

**Prerequisites:** a Snowflake account with Cortex enabled, `ACCOUNTADMIN`, and
[CoCo CLI](https://docs.snowflake.com/en/user-guide/cortex-code/cortex-code-cli).

Run the real-data path in dependency order:

1. `sql/10_real_setup.sql`
2. `sql/11_bronze_load.sql`
3. `sql/12_silver.sql`
4. `sql/13_gold_oee.sql`
5. `sql/16_it_synthetic.sql`
6. `sql/15_plant_b_risk.sql`
7. `sql/18_piade_erp.sql`
8. `sql/19_decision_intelligence.sql`
9. `sql/20_piade_autoresearch.sql` then `CALL ML.RUN_PIADE_AUTORESEARCH(25)`
10. `sql/21_failure_warning.sql` (4-hour breakdown warning; trains and scores)
11. `sql/22_root_cause.sql` (root-cause card views)
12. `sql/23_risk_work_orders.sql` (automatic work orders; calls
    `GOLD.GENERATE_RISK_WORK_ORDERS(8, 'LINE')`)
13. `sql/17_semantic_cortex.sql`
14. upload `streamlit/app.py` to the existing Streamlit stage

Steps 10–12 need the 21 → 22 → 23 order; 21 and 23 contain procedures, so run
them with `PUT` plus `EXECUTE IMMEDIATE FROM` when the CLI cannot send a large
`$$` body.

`sql/20` does not overwrite the production ExtraTrees scores. A champion is
eligible only after the four validation gates; December 2021+ is a reused
holdout, not a search fold. Campaign `233717d9` passed those gates with a
~0.0001 mean-AUC lift (0.687942 → 0.688040) and was **not** applied to
production. The champion contract is `9e96f29e-4f98-41d3-a5eb-e08d5f3aa797`.

The execution/audit trail is under `docs/cortex-audit/`; prompt 024 is the
end-to-end deployment and verification record.

The separate original quickstart exhibit is reproduced with `sql/01`–`04`.

> **Trial accounts:** this build deliberately avoids Snowpark Container Services and
> external access integrations, which trials reject. Streamlit runs on the **warehouse
> runtime**, so dependencies live in `streamlit/environment.yml` (conda, Snowflake
> Anaconda Channel) — *not* `requirements.txt`, which that runtime ignores.

---

## Datasets and licences

| Dataset | Origin | Licence |
|---|---|---|
| PIADE production intervals and hourly aggregates | Real published packaging operations, DOI `10.5281/zenodo.7071747` | CC BY 4.0 |
| Live command-center work orders, production orders, technicians, materials, inventory and euros | Deterministic synthetic scenario records anchored to PIADE events | Project code MIT; records are generated demonstrations |
| Original `SNOWCORE_INDUSTRIES` telemetry, maintenance, production and financial exhibit | Synthetic, generated in-database from the Snowflake-Labs quickstart | Upstream MIT; modifications MIT |

No proprietary, personal or customer data is used.

---

## Licence

MIT. See [`LICENSE`](LICENSE). The upstream Snowflake-Labs copyright notice is preserved
in [`LICENSE-UPSTREAM-SNOWFLAKE-LABS`](LICENSE-UPSTREAM-SNOWFLAKE-LABS) as the MIT terms
require.

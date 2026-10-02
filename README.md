# TRIDENT OPS — Evidence-first Predictive Maintenance & OEE

**TRidents · Snowflake CoCo CLI Hackathon 2026 — GCC Edition · Problem Statement 3**

TRIDENT OPS is a standalone Streamlit-in-Snowflake command center over two real,
public evidence lanes:

- **PIADE:** two years of real packaging-line states, alarms and package counts.
  This is the operational spine: weighted OEE, loss ownership, next-hour risk,
  cited alarm-pattern investigation and persistent triage.
- **MetroPT:** real compressor pressure, motor current, temperature, load and
  reported failures. This is a separate sensor-evidence page. The detector is
  explicitly labelled post-onset detection and `NO_PROMOTION`.

The datasets come from unrelated assets and are **never joined**. One console does
not mean one fabricated plant.

## Live prototype

[Open TRIDENT OPS in Snowflake](https://app.snowflake.com/streamlit/FMXJOWH/BRC04642/#/apps/bd2ocwt4eblddojvzl7v)

The app uses `SYSTEM$WAREHOUSE_RUNTIME` with pinned Snowflake-channel packages:
Streamlit 1.52.2, Plotly 6.5.0, pandas 2.3.3 and Snowpark Python.

## Three working capabilities

1. **OEE and loss ownership:** site OEE is recomputed from summed observed seconds
   and packages, not averaged percentages. PIADE site OEE is 46.78%
   (A 64.32% × P 72.93% × Q 99.72%).
2. **Bounded RCA:** Cortex sees at most five deterministic alarm-pattern rows,
   cites anonymised alarm codes and must abstain from component claims.
3. **Persistent triage:** acknowledge, inspect and snooze call an idempotent
   Snowflake procedure. A repeat click returns the existing action id; it does not
   create another row.

## Truth contract

| Label | Meaning |
|---|---|
| Observed | Copied from a published source |
| Derived | Deterministic calculation from observed rows |
| Model | Evaluated output with a named split and baseline |
| Scenario | Generated ERP, maintenance history or money |
| Operator-entered | A real decision made in this prototype |

PIADE has no vibration, temperature or current channels. MetroPT has no production
counts or real ERP. TRIDENT OPS does not claim remaining useful life, measured OEE
lift or realised savings.

## Source map

| Path | Purpose |
|---|---|
| `sql/10_real_setup.sql` … `sql/23_risk_work_orders.sql` | Reproducible PIADE medallion, OEE, model, Cortex and replay |
| `pneumora/` | Isolated MetroPT ingest, evaluation and Streamlit app |
| `trident_ops/` | Standalone command center, action procedure and tests |
| `docs/prototype-brief.md` | Submission copy and demo workflow |
| `docs/project-a-to-z.html` | PIADE engineering guide |
| `docs/pneumora-a-to-z.html` | MetroPT engineering guide |

## Reproduce TRIDENT OPS

Run `trident_ops/sql/00_setup.sql`, then `01_triage_action.sql`. Upload
`trident_ops/app.py`, `environment.yml`, `.streamlit/config.toml` and `modules/`
to `@TRIDENT_OPS.APP.STREAMLIT_STAGE`, then run `02_deploy_app.sql`.

```powershell
.\pneumora\.venv-sis152\Scripts\python.exe -m pytest trident_ops\tests -q
cd pneumora
.\.venv\Scripts\python.exe -m pytest tests -q
```

## Honest model evidence

- PIADE rolling-validation champion AUC: 0.6880; baseline 0.6879. The automated
  search plateaued, so another algorithm is not the missing ingredient.
- PIADE blind top-decile precision: 76.4%; model status must be read beside its
  persistence baseline and per-line trust flag.
- MetroPT external air-leak detector: 2 of 3, at +72 and +86 minutes after onset,
  with one false alert in 167 healthy days. It is not a forecast.

---

## Retired synthetic prototype — audit history, not the submission

<details>
<summary>Expand the original Snowflake quickstart investigation</summary>

---

### The original finding

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

## What this is worth in money

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

## Architecture

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

## Reproducing this

**Prerequisites:** a Snowflake account with Cortex enabled, `ACCOUNTADMIN`, and
[CoCo CLI](https://docs.snowflake.com/en/user-guide/cortex-code/cortex-code-cli).

```bash
# 1. Build the warehouse, data, semantic view and agent  (~10 min)
#    Run in a Snowsight worksheet, or:  cortex exec "run sql/01_setup_snowcore.sql"

# 2. Train the model and evaluate on a chronological holdout
#    sql/02_ml_model.sql

# 3. Derive costs and select the operating threshold
#    sql/03_cost_analysis.sql

# 4. Deploy the app  (warehouse runtime — works on trial accounts)
#    see streamlit/ and the CREATE STREAMLIT in sql/04_deploy_app.sql
```

> **Trial accounts:** this build deliberately avoids Snowpark Container Services and
> external access integrations, which trials reject. Streamlit runs on the **warehouse
> runtime**, so dependencies live in `streamlit/environment.yml` (conda, Snowflake
> Anaconda Channel) — *not* `requirements.txt`, which that runtime ignores.

---

## Datasets and licences

| Dataset | Origin | Licence |
|---|---|---|
| All telemetry, maintenance, production and financial data | **Synthetic — generated in-database by SQL.** No external data was downloaded or imported. | Derived from the MIT-licensed Snowflake-Labs quickstart; our modifications released under MIT |

No real, proprietary, personal or customer data is used anywhere in this project.

---

## Licence

MIT. See [`LICENSE`](LICENSE). The upstream Snowflake-Labs copyright notice is preserved
in [`LICENSE-UPSTREAM-SNOWFLAKE-LABS`](LICENSE-UPSTREAM-SNOWFLAKE-LABS) as the MIT terms
require.

</details>

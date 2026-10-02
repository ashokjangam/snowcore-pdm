# PNEUMORA — early air-leak prediction on real compressor sensors

**TRidents · Snowflake CoCo CLI Hackathon 2026 — GCC Edition · Predictive Maintenance and OEE Command Center**

PNEUMORA is a Streamlit-in-Snowflake command center for one real asset: the air
production unit (compressor) of a Porto metro train. It reads the compressor's
real sensor streams, catches developing air leaks, explains each one with Cortex
using only observed facts, and records the crew's decision in Snowflake.

- **Real:** MetroPT pressure, motor current, oil temperature and compressor-load
  streams from three compressors, with nine documented failures
  (MetroPT-3 DOI `10.24432/C5VW3R`, MetroPT 2022 Zenodo `6854240`, MetroPT-2
  Zenodo `7766691`).
- **Synthetic, labelled:** work orders, parts, crew and an example-factory OEE
  scenario for the same asset. They are labelled on every screen and never used
  to score a model.

## Live prototype

[Open PNEUMORA in Snowflake](https://app.snowflake.com/streamlit/FMXJOWH/BRC04642/#/apps/df4d72ofa3zbhz6wswdh)

Warehouse runtime (`SYSTEM$WAREHOUSE_RUNTIME`) with Streamlit 1.52.2, Plotly 6.5.0,
pandas 2.3.3 and Snowpark Python.

## Three working capabilities

1. **Predict.** A physics leak predictor (the compressor stays loaded for about
   an hour) flagged 6 of 7 air leaks at least two hours before the train had to
   come out of service, a median 5.8 hours ahead, when tested on compressors it
   never saw. The existing low-pressure alarm managed 3 of 7, with nearly nine
   times the false alerts (0.49 against 0.056 per healthy day). Every pre-declared
   gate passed: `PROMOTED_CROSS_VALIDATED`. `SNOWFLAKE.ML.ANOMALY_DETECTION`
   caught 4 of 4 on a time split, at 0.34 false alerts per day.
2. **Explain.** Cortex `AI_COMPLETE` with a typed response receives only the
   observed facts for a failure, must quote the field behind every number, and
   may not name a component the failure report does not name.
3. **Act.** Acknowledge, inspect and dismiss call `PNEUMORA.OPS.RECORD_ACTION`, a
   MERGE on a hashed key. Repeating a decision returns the same action id.

## What "predict" means here

PNEUMORA predicts the breakdown, the point by which the train must come out of
service, which is the dataset owners' own definition of a predicted failure. It
does not predict the leak itself. We tested that directly, with gates fixed in
code and every arm held out by compressor: label-free cycle physics with drift,
EWMA and CUSUM, three gradient-boosted models, synthetic replay of real onsets,
and a rolling baseline. The best warned 1 of 9 failures before the leak began
(F04, about 80 minutes). The other leaks begin abruptly.

The promotion has one caveat the app states: protocol v2 was written after v1
failed only its false-alert budget, and all nine failures had been seen. No
untouched MetroPT data exists to test it again.

To test gradual leaks, which the data does not contain, leaks were injected
into real healthy compressor runs. A leak at twice normal air loss was caught
in 28 of 30 trials, against 7 of 30 with no leak. That is a sensitivity
specification, not validation.

## Reproduce

```powershell
cd pneumora
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest tests -q
```

Run `pneumora/sql/00_setup.sql` to `05_native_ml.sql` in order through a client
session (CoCo CLI, Snowflake CLI or SnowSQL). The full pipeline, studies and
limits are in [`pneumora/README.md`](pneumora/README.md) and
[`pneumora/docs/model-card.md`](pneumora/docs/model-card.md).

## Source map

| Path | Purpose |
|---|---|
| `pneumora/` | Ingest, studies, export, Snowflake SQL, Streamlit app and tests |
| `docs/prototype-brief.md` | Submission brief and video script |
| `docs/demo/` | CoCo CLI prompts used in the demo |
| `docs/submission/` | Deck (PPTX and PDF) |
| `docs/cortex-audit/` | Every CoCo CLI prompt and result used to build and deploy |
| `sql/10_*` … `sql/23_*` | Earlier PIADE packaging-line work, not part of this submission |

## Limits

PNEUMORA does not foresee a leak before it begins, catch oil leaks, estimate remaining useful life,
measure real factory OEE or claim avoided cost. MetroPT has no production counts
or real work orders; those views are labelled synthetic.

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

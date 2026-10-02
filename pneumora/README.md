# PNEUMORA

PNEUMORA is an isolated compressor-intelligence demonstrator built on the
official UCI MetroPT-3 dataset (DOI `10.24432/C5VW3R`).

## Truth contract

| Origin | Meaning |
| --- | --- |
| `OBSERVED_METROPT3` | Measurements and documented failure intervals from UCI |
| `DERIVED_FROM_OBSERVED` | Features, alerts and metrics computed from observed data |
| `SYNTHETIC_TRAINING_ONLY` | Physics-grounded generated rows used only for model fitting |
| `SYNTHETIC_MAINTENANCE` | Demonstration technicians, work orders, parts and outcomes |
| `SYNTHETIC_FACTORY_SCENARIO` | Demonstration production, quality, cost and OEE assumptions |

Generated failures never enter observed evaluation. Headline forecast evidence
is episode-level performance on four documented April–July air-leak intervals.

## Run

```powershell
cd pneumora
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts\ingest_metropt.py
.\.venv\Scripts\python.exe autoresearch\run_campaign.py
.\.venv\Scripts\python.exe scripts\export_training_report.py
.\.venv\Scripts\python.exe scripts\build_product.py
.\.venv\Scripts\python.exe -m uvicorn server.main:app --port 8520
```

Open `http://localhost:8520`. Simple mode is the operator view. Engineering
mode and the Training and Evidence pages expose the frozen split, physical
baselines, synthetic controls, data quality and provenance. Maintenance is
PNEUMORA's own CMMS: create, assign, start, wait for parts and complete work
orders. Those records are seeded for the demonstrator.

## Frozen result

No candidate passed promotion. The only arm to overlap observed failures was a
PCA residual detector: 2 of 4 episodes, but with 230 false alerts (1.50 per
test day) and 2.5 minutes median lead. The synthetic-trained model warned 0 of
4. The product therefore labels the predictive model `NO_PROMOTION` and uses
the existing LPS signal only as a reactive low-pressure alarm.

## Official-protocol study and external test

`autoresearch/official_study.py` develops detectors on MetroPT-3 under the
dataset owner's protocol: an alert must arrive at least two hours before the
reported end of the failure. `autoresearch/official_freeze.json` fixes the
recipe and gates. `autoresearch/external_test.py` then scores the frozen
detector once on MetroPT 2022 and MetroPT-2. Download both to
`data/raw/external/` first, as `metropt2022_train.csv` and `MetroPT2.csv`.

`scripts/build_units.py` then caches all three units, and
`autoresearch/louo_study.py` runs the leave-one-compressor-out study. Run both
before `scripts/build_product.py`, which turns the frozen detector into the
early air-leak detector: alerts on the Now page and draft work orders labelled
`CROSS_VALIDATED_NOT_PROMOTED`, running beside the existing alarm.

The physical detector, "compressor stays loaded about an hour", caught 2 of 3
external air leaks with 1 false alert in 167 healthy days. The existing alarm
caught the same 2, 15–20 minutes earlier, plus both oil leaks, with 57 false
alerts. The status stays `NO_PROMOTION`; see `docs/model-card.md`.

## Promoted predictor

`autoresearch/prediction_study.py` (protocol v2) asks whether the detector
predicts the in-service failure: an alert at least two hours before the train
must be taken out of service, the dataset owners' definition. Held out by
compressor, it predicted 6 of 7 air leaks a median 5.8 hours ahead, at 0.056
false alerts per healthy day; the existing alarm predicted 3 of 7 at 0.49. All
five pre-declared gates passed, so the status is `PROMOTED_CROSS_VALIDATED`. v2
was written after v1 failed on false alerts and every failure had been seen;
see `docs/model-card.md`.

## Before-onset study

`scripts/build_cycles.py` extracts compressor cycle physics from the raw data,
and `autoresearch/precursor_study.py` tests whether any label-free, supervised
or replay-augmented arm can warn before reported onset, held out by compressor.
None passed: the best warned 1 of 9 failures before onset. A leak-injection
curve on real healthy runs shows a gradual leak at twice normal air loss would
be flagged in 28 of 30 trials, against 7 of 30 with no leak. The app's
"Can it predict?" page shows both results.

## Snowflake

Run `sql/00_setup.sql` to `sql/05_native_ml.sql` in order through a client
session (Cortex Code CLI, Snowflake CLI or SnowSQL).

- `04_actions.sql` creates `OPS.ACTION_LOG` and `OPS.RECORD_ACTION`, the app's
  only write. Repeating the same acknowledgement returns the same action id.
- `05_native_ml.sql` trains `SNOWFLAKE.ML.ANOMALY_DETECTION` on February–March
  and scores April onward against the reported failures: 0 of 4 before onset,
  4 of 4 caught in time, 0.34 false alerts per healthy day.
- The app's RCA button calls Cortex `AI_COMPLETE` with a typed response and
  cites the evidence rows it was given.

## Limits

MetroPT-3 contains four reported leak intervals from one Air Production Unit.
It does not contain production counts, quality output, real work orders,
technician assignments, trip cancellations or repair costs. PNEUMORA therefore
does not claim validated component diagnosis, remaining useful life, measured
factory OEE, avoided cost, or transfer to another compressor.

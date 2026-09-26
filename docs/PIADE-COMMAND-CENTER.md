# PIADE Command Center — submission architecture

**Status:** deployed and verified in `SNOWCORE_REAL.APPS.SNOWCORE_PDM`  
**Primary dataset:** PIADE, DOI `10.5281/zenodo.7071747`, CC BY 4.0  
**Scope:** one real packaging site, five lines (`s_1`–`s_5`)

## Why the project uses one dataset

CoMoPI and PIADE describe different factories, machines and time periods. They
have no shared key. Joining them would invent a factory that never existed.
Keeping both as equal halves of the application also failed to demonstrate the
problem statement's core requirement: a traceable path from operational events
to maintenance and business decisions.

The submission therefore uses PIADE as its sole operational foundation.
CoMoPI remains in the warehouse as prior research but is not part of the
command center or its headline claims.

## The digital thread

Every business record starts from a published PIADE row:

```text
PIADE production interval / hourly aggregate
  -> derived downtime or idle incident
  -> synthetic ERP production order for the same line and day
  -> synthetic maintenance work order when the source recorded a fault
  -> synthetic material issue and inventory position
  -> derived production exposure and scenario cost
  -> ranked action with an owning function
```

The joins are inspectable:

- machine code and production date anchor a synthetic production order to
  observed PIADE production;
- source event start/end and alarm code anchor a work order to an observed
  breakdown;
- work-order ID anchors material usage;
- material ID anchors the scenario inventory position;
- every action retains its source key and provenance.

No synthetic record creates a new breakdown, idle period, package count or
alarm. Rerunning the generator with the same version produces the same rows.

## Provenance vocabulary

- `OBSERVED`: published directly by PIADE.
- `DERIVED_FROM_OBSERVED`: calculated only from published values.
- `SYNTHETIC_IT`: maintenance workflow added to an observed fault.
- `SYNTHETIC_ERP`: production orders, material master and inventory scenario
  added around observed production.

Synthetic means scenario data, not measured factory history. The application
must never describe a synthetic euro, technician, part or order as observed.

## Operational distinction that must remain visible

PIADE records two different forms of unplanned lost availability:

- `downtime`: the source records an alarm; this is a maintenance event;
- `idle`: the source records no alarm; this is waiting and belongs to
  production planning or material flow.

The source has 92,084 downtime intervals and every one carries an alarm. It has
50,149 idle intervals and none carries an alarm. Combining them would send the
maintenance team after the site's largest loss even though nothing was broken.

## OEE contract

OEE is recomputed from summed denominators:

```text
Availability = total run seconds / total planned seconds
Performance  = total packages out / total theoretical packages while running
Quality      = total packages out / total packages in
OEE          = Availability * Performance * Quality
```

The canonical site result is 46.78%. It is not the mean of hourly OEE (57.1%)
or the mean of daily OEE (43.2%). Those averages weight periods with different
production volumes equally.

The ideal rate is each line's best demonstrated observed speed, not a vendor
nameplate rate. Quality is throughput yield, not a laboratory quality measure.

### Counter-boundary cap

PIADE publishes cumulative counters sampled at interval boundaries, so an
output can be recorded in a later bucket than the input that produced it. Each
OEE term is therefore capped at 1.0 wherever it is computed, and
`GOLD.PIADE_OEE_DAILY.QUALITY_CLAMPED` records where the cap applied. Measured
scope of the effect:

- 107 of 2,367 machine-days are quality-clamped;
- 2 of 105 weeks hit the cap on at least one term;
- the application's weekly trend applies the same cap, so it ranges 29.26% to
  73.10% with no week above 100%.

The cap is a stated convention, not a correction: it bounds a sampling
artefact rather than removing real production.

## Predictive model contract

**Question:** will the next machine-hour lose more than 10% of its time to
unplanned downtime?

The operating point flags exactly the highest-risk 10% of scored hours.
Performance is always compared with the equal-workload persistence rule:
"current-hour downtime predicts next-hour downtime."

The original production model used a single chronological cutoff at
2021-08-01 and achieved approximately:

- AUC 0.659;
- top-decile precision 67.6%;
- persistence precision 55.7%.

The revised search does not tune against its final month:

- validation fold 1: train before 2021-04-01, validate April–July;
- validation fold 2: train before 2021-08-01, validate August–November;
- blind test: December 2021 onward.

`ML.RUN_PIADE_AUTORESEARCH` repeats that protocol inside Snowflake: Cortex
may propose allowlisted JSON configs; a frozen evaluator trains them; invalid
or duplicate proposals fall back to a deterministic candidate list. The
campaign is capped at 25 trials and 30 minutes. Forest sizes are capped for
the X-Small warehouse because a full-width RandomForest fit could not be
preempted and overran the budget. Promotion requires all of:
higher mean validation AUC than the ExtraTrees baseline, no worst-fold AUC
regression, no top-decile precision-lift regression versus persistence, and
no new per-line persistence failures. Failing any gate leaves production
tables unchanged.

Campaign `233717d9-b657-4d83-a030-e918e9849237` (25 trials, 22 minutes)
completed with `PROMOTION_ELIGIBLE=TRUE` and
`PRODUCTION_TABLES_MODIFIED=FALSE`. The production ExtraTrees
(700 trees, `max_features=0.4`, `min_samples_leaf=30`) remains the
scored model. The champion is ExtraTrees 600 / 0.7 / 45. Mean validation
AUC moved from 0.687942 to 0.688040. Reused-holdout fleet AUC was
0.688842 with top-decile precision 0.764331; those numbers were not used
for selection. The lift is ~0.0001 AUC. That is enough to pass the coded
gates and not enough to justify applying `sql/15`. Registry logging was
skipped (`snowflake-ml-python` version resolution). Contract
`9e96f29e-4f98-41d3-a5eb-e08d5f3aa797` is the refit recipe if promotion
is done later.

The selected production `ExtraTreesClassifier` was chosen by mean
validation AUC, with worst-fold AUC and fixed-workload precision as
tie-breakers. The Snowflake deployment reproduced the previously
observed final period at:

- 1,566 machine-hours;
- base rate 44.25%;
- AUC 0.6883;
- average precision 0.6419;
- top-decile precision 76.43%;
- persistence precision 62.42%;
- top-decile recall 17.32%.

This is a modest ranking model, not a failure oracle. It predicts production
state persistence and transition patterns; PIADE contains no vibration,
temperature or RPM sensor channels. It does not estimate remaining useful
life.

### 4-hour breakdown warning (`sql/21_failure_warning.sql`)

Target: a downtime interval of at least 10 minutes (the work-order rule)
starting in `[H+1h, H+5h)`. Same 299 features and ExtraTrees 700/0.4/30
configuration; training rows whose label window reaches 2021-12-01 are purged;
hours whose next four hours are under 90% covered by the interval log are
excluded (coverage comes from `SILVER.PIADE_INTERVAL`, because the published
hourly table omits many logged hours). Nothing was tuned on December.

December 2021 result (1,340 hours, base rate 25.0%, 134 flagged):

| Rule | Top-decile precision | AUC |
|---|---|---|
| 4-hour warning | 62.7% | 0.732 |
| Worst line first (training-period line rate) | 58.2% | 0.701 |
| Recent breakdowns (last 24 h) | 41.0% | 0.662 |
| Downtime continues (persistence) | 38.1% | 0.605 |

Fleet-wide the model is +4.5 points over the best rule, within noise. Within
each line it does not beat the best simple rule (ties s_1, loses s_2–s_5).
Line identity features dominate importance. This is recorded as a weak result,
not a win.

### Root-cause card (`sql/22_root_cause.sql`)

`GOLD.ROOT_CAUSE_EVENT` holds one row per long breakdown with precursor
short stops (same code, 60 minutes before), same-code repeat within 24 hours,
clock band and next state. `GOLD.V_ROOT_CAUSE_ALARM` aggregates per line and
code with a deterministic pattern label. Clock bands are dataset-time windows,
not the real shift rota, and are not normalised for when each line runs.

### Automatic work orders (`sql/23_risk_work_orders.sql`)

`GOLD.GENERATE_RISK_WORK_ORDERS(cooldown_hours, 'LINE'|'FLEET')` idempotently
replaces `GOLD.RISK_WORK_ORDER` rows (`SYNTHETIC_IT`) with one planned
inspection per risk episode, carrying score, recent-alarm and kit-stock
evidence, and a back-tested outcome. With the default per-line top-10% cut and
an 8-hour cooldown: 45 orders, 35.6% followed by a breakdown within 4 hours
against 28.2% for random hours on the same lines (1.26×), covering 23% of
December's 196 breakdowns. The fleet-wide cut looks better (64.5%) only
because 27 of 31 orders go to s_2. The cut-off comes from December's own score
distribution, and there is no scheduled Task because the data is not live.

Ashok's 0.766 AUC result is valid for the original Snowflake synthetic
quickstart after its failure generator was repaired. It is not comparable to
PIADE: the target, features, assets, horizon and data-generating process are
different.

## Application decisions

The primary screens are:

1. **Command Center** — site KPIs, five-line fleet ranking, loss bridge and
   owned action queue.
2. **Fleet Risk** — next-hour risk, measured model trust, recent operating
   history, feature drivers and the 4-hour breakdown warning against three
   simple rules.
3. **OEE Drill-Down** — weighted A/P/Q, weekly weighted trend, line comparison,
   fault Pareto and the per-line root-cause card with a bounded Cortex
   explanation.
4. **Work & Materials** — work orders, automatic risk work orders with
   outcomes, parts position and a visible event-to-ERP lineage.
5. **Financial Risk** — scenario exposure split between planning and
   maintenance.
6. **Analyst** — Operational Q&A over long-form bounded facts, plus a
   Decision Scenario mode that computes a throughput or contribution-margin
   gap in the app and only then asks Cortex to narrate those numbers.
7. **Research Lab** — 25-trial Snowflake-native search ledger. Selection
   uses two rolling-origin folds only. December 2021+ is reused-holdout
   confirmation after promotion gates, never a search signal. The latest
   completed campaign is `233717d9`; the scored production model is
   unchanged.

The visual system is an operations console: high information density,
restricted colour, risk colour used only for exceptions, no marketing hero,
and no unsupported sensor or RUL visualisations.

Tables are rendered through a single display contract rather than dumped as
raw warehouse output. Column names become short labels, the unit is carried in
the header, ratios render as percentages, euros render in the magnitude that
suits the grain, and warehouse enums read as prose. Values stay numeric, so
column sorting remains correct.

## What the submission demonstrates

- real manufacturing OT ingestion and OEE reconstruction;
- auditable separation of waiting from faulted downtime;
- leakage-controlled chronological predictive evaluation;
- an OT-to-maintenance-to-ERP digital thread;
- Snowflake-native transformation, Snowpark model training, semantic layer,
  Cortex narrative and Streamlit application;
- provenance attached to every non-observed business record.

## What it does not demonstrate

- a connection to a real ERP or CMMS;
- observed technician, work-order, inventory or financial records;
- causal proof that an intervention prevents a predicted stop;
- analog-sensor predictive maintenance;
- remaining useful life;
- actual euro savings;
- a live feed after the PIADE dataset's final timestamp.

The defensible description is:

> Real industrial OT drives a fully traceable simulated maintenance and ERP
> workflow inside Snowflake.

It must never be shortened to "real OT and ERP data were integrated."

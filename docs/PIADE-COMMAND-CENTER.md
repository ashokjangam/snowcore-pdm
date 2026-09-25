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

The selected `ExtraTreesClassifier` was chosen by mean validation AUC, with
worst-fold AUC and fixed-workload precision as tie-breakers. The Snowflake
deployment reproduced the untouched final period at:

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

Ashok's 0.766 AUC result is valid for the original Snowflake synthetic
quickstart after its failure generator was repaired. It is not comparable to
PIADE: the target, features, assets, horizon and data-generating process are
different.

## Application decisions

The primary screens are:

1. **Command Center** — site KPIs, five-line fleet ranking, loss bridge and
   owned action queue.
2. **Fleet Risk** — next-hour risk, measured model trust, recent operating
   history and feature drivers.
3. **OEE Drill-Down** — weighted A/P/Q, weekly weighted trend, line comparison
   and fault Pareto.
4. **Work & Materials** — work orders, parts position and a visible
   event-to-ERP lineage.
5. **Financial Risk** — scenario exposure split between planning and
   maintenance.
6. **Analyst** — Cortex narrative over bounded aggregate facts with an
   evidence/source list.

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

# Two-plant plan (plain English)

> **Superseded 25 September 2026.** This document is retained as the decision
> record for the two-dataset experiment. The submission now uses PIADE as one
> coherent factory so it can demonstrate an auditable OT → maintenance → ERP
> digital thread. See [`PIADE-COMMAND-CENTER.md`](PIADE-COMMAND-CENTER.md).

**Status:** historical; implemented, evaluated, then retired from the primary app.
**Problem:** Predictive Maintenance and OEE Command Center.

---

## What we decided

Use **two real manufacturing plants**, kept separate. Do not mix their rows into one fake factory.

| Plant | Dataset | Full name | Job in the app |
|---|---|---|---|
| Plant A | CoMoPI | Condition Monitoring for Packaging Industry | Predictive maintenance (sensors and fault alarms) |
| Plant B | PIADE | Packaging Industry Anomaly DEtection | Production and OEE-style numbers (run, stop, packages, speed) |

Both come from real industrial packaging machines (Galdi / Padova / Statwolf research). They are **cousins, not the same line**. Different years, different machine IDs, no published join key. We will never join them.

We will **not** load MetroPT (train, not a factory), beer bottling, brick OEE, PET bottles, Azure, or the Snowflake fake-factory generator as the foundation.

A third real dataset is **not** required. Extra files do not make CoMoPI or PIADE more real. They only add more screens and more chances to look like one blended plant.

---

## The hole we still have

A full command center wants four kinds of truth:

1. Machine health (sensors / alarms)
2. Production health (OEE: was it up, how fast, how much scrap)
3. Maintenance tickets (work orders, technicians)
4. Money (labour, parts, downtime cost)

No public dataset has all four.

- CoMoPI gives (1). It does **not** give (2), (3), or (4).
- PIADE gives a large part of (2), plus stop alarms. It does **not** give (3) or (4). It also does not give analog sensors.

So for **both** plants we still **build the office side (IT)**. That means work orders and costs. We generate them only from events that already exist in that plant’s machine data (OT). We label every generated row as synthetic. We do not invent extra breakdowns to make the ticket list look busy.

---

## Plant A — CoMoPI (PdM)

**What it is.** Eight real packaging machines. The sensors sit on the module that seals packages watertight. Published so researchers could predict component faults.

**What is in the files.**

- One row every 10 minutes per machine.
- Sensor averages with hidden names (`AE`, `BP`, and so on). We will not pretend we know they are “temperature” or “vibration.”
- Counts of alarms and warnings in that window.
- Two alarms, **AL_53** and **AL_54**, mean “this component is faulty.” That is the prediction target.

**What we will do.**

- Load it as Plant A OT.
- Train a model that tries to see fault alarms coming, in time order (not a random row split).
- Open a synthetic work order only when those fault alarms (or another alarm we write down in advance) actually fired.
- Optional fake scheduled inspections, clearly marked synthetic.

**What we will not do.**

- Invent OEE, package counts, or “the line was slow” for Plant A.
- Copy Plant A tickets onto Plant B.

**Licence / source.** CC BY 4.0. Zenodo: https://doi.org/10.5281/zenodo.7572501

---

## Plant B — PIADE (production / OEE)

**What it is.** Five real packaging machines. Published so researchers could detect odd production behaviour and forecast stop alarms.

**What is in the files.**

- Each row is a stretch of time in one state: running, idle, down, slow, or planned stop.
- Packages in, packages out, speed, how long the interval lasted, and which alarm caused a stop if there was one.
- About 429,000 intervals and 133 alarm types.
- A second file rolls that up to one-hour summaries.

**What we will do.**

- Load it as Plant B OT.
- Compute availability-like numbers from uptime vs downtime.
- Compute performance-like numbers from speed and “slow” intervals.
- Treat quality as the weak leg. Packages in vs packages out is **not** a quality lab. We will say that out loud in the app.
- Open a synthetic work order only from real downtime / stop-alarm intervals.

**What we will not do.**

- Claim a textbook Quality score we did not measure.
- Invent analog sensors for Plant B.
- Copy Plant B packages onto Plant A.

**Licence / source.** CC BY 4.0. Zenodo: https://doi.org/10.5281/zenodo.7071747

---

## How IT generation works (same rule both plants)

1. Look only at that plant’s real OT events.
2. Create a work order that points at those events.
3. Put assumed hours, parts, and dollars in one visible assumption list. Those numbers are a scenario, not a metro or Galdi invoice.
4. Stamp origin: observed vs published vs derived vs synthetic.
5. Regenerating with the same rules and seed must produce the same tickets.

That is “based on OT only.” Correct for both plants. PIADE does **not** spare us from building tickets. It spares us from inventing OEE.

---

## How this fits the existing app

The current Streamlit app is a **synthetic** six-page factory. We keep it until the two real plants load and reconcile. Then we add a real-data path with plant badges (Plant A vs Plant B, observed vs synthetic).

We do not silently replace fake OEE with CoMoPI. We do not drop the old schemas until the new ones check out.

Work in Snowflake goes through Cortex CLI (CoCo): show the prompt, generate SQL, review, then run. File upload uses Snowflake `PUT` / `COPY`, not the chat box as a file truck.

---

## Build order

1. Download CoMoPI and PIADE from Zenodo. Record checksums, row counts, date ranges, licences.
2. Read-only CoCo audit of current Snowflake objects. Propose tables. Do not create yet.
3. Write down the IT rules and get them approved (which alarms become tickets, which costs).
4. Load Bronze for Plant A and Plant B separately. Row counts must match the files.
5. Silver: clean types, derive PIADE availability/performance, attach origin flags.
6. Generate IT rows from the approved rules only.
7. Models: CoMoPI fault prediction in time order; PIADE stop/anomaly in time order.
8. Semantic layer and app: two plants, provenance on every number that is not observed.
9. Checks, cost/credit review, rollback notes for the new objects only.

Stop if row counts drift, if extra “observed” failures appear, or if a ticket is not traceable to an OT event.

---

## What this plan will not achieve

- One fused “smart factory.”
- Proof that a CoMoPI seal fault caused a PIADE stop. That link is not in the files.
- Real invoices or English technician notes.
- Perfect Nakajima OEE on Plant B (Quality is weak).
- Sensor PdM on Plant B.
- A huge fleet story (eight machines + five machines).

---

## Risks (say these before we build)

- Anonymized CoMoPI sensors make a “vibration dashboard” story false. Say “process measurements on a sealing module.”
- Remapping all six current pages onto two real plants is the schedule risk. Safer: a real-data validation surface first, then remap pages.
- If a judge wants a printed A × P × Q table with Quality already in the file, Heavy-clay would be stronger OEE and worse PdM. We are choosing packaging industry fit over that printed Quality column.

---

## One-line summary

Two real packaging plants, never blended: CoMoPI for “will it fail,” PIADE for “how did production run,” and synthetic tickets only where those plants already had a real event.

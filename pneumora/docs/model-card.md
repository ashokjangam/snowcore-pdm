# PNEUMORA model card

## Intended decision

Warn a non-technical operator when observed compressor behavior indicates an
air problem may begin within two hours. A warning prepares a human-reviewed
work order; it does not stop equipment or dispatch a technician.

## Data

- Official UCI MetroPT-3, DOI `10.24432/C5VW3R`.
- February fits features, physical parameters and models.
- March freezes alert thresholds and the false-alert workload.
- Four documented April–July air-leak intervals are scored once.
- The April event has day-level onset precision and must not be quoted with
  minute-level lead-time certainty.

## Synthetic training

The compressor-reservoir generator is identified on February only. It creates
downstream leaks, dryer-drain faults and reduced-delivery scenarios. Generated
rows are tagged `SYNTHETIC_TRAINING_ONLY`; calibration and test contain zero
generated rows. An observed-only comparison and wrong-physics control are
mandatory.

## Promotion

Promotion requires no more than one merged March alert per seven healthy days,
at least three of four observed episodes warned within two hours, positive lead
over the existing low-pressure alarm, improvement over the duty-cycle baseline,
improvement from synthetic augmentation, and failure of the wrong-physics
control. The frozen result is written to `autoresearch/champion.json`.

## Frozen observed result

`NO_PROMOTION`. The LPS alarm, duty-cycle rule, cycle/pressure rule, Isolation
Forest, compact autoencoder, synthetic-trained gradient booster, and
wrong-physics control warned 0 of 4 observed episodes inside the frozen
two-hour window. The PCA residual arm overlapped 2 of 4, but raised 232 merged
alerts (230 false alerts, 1.50 per test day) and its median lead was only 2.5
minutes; it failed the workload and three-of-four gates. Synthetic training
did not improve the real episodes. PNEUMORA therefore retains LPS only as a
reactive existing alarm and does not represent it as predictive maintenance.

## Second study: official protocol with untouched external data

Target changed to the dataset owner's protocol (Veloso et al., *Scientific
Data* 9:764, 2022): a failure is caught in time when a merged alert lands
between two hours before the reported start and two hours before the reported
end, which is the operator's stated removal need. This is detection of a
developing failure, not a forecast before it starts.

Alert counting was corrected: an alert episode now ends only once flags stop
for more than 30 minutes. The first campaign measured the gap from the episode
start, so one continuous condition counted as a new alert every 30 minutes and
inflated its false-alert figures.

Development on MetroPT-3 used all four episodes, so it is not a clean test.
The recipe learns each unit's normal behaviour from its first 21 days and sets
the threshold on the next 14 days against the false-alert budget, with no
failure labels. Generic anomaly scores (PCA, autoencoder, Isolation Forest,
corroboration; static and weekly-refit) reacted to changes in how the train was
operated, at 1.5–2 false alerts per day. The selected detector is physical: the
compressor stays loaded continuously for about an hour. Healthy loaded runs
have a median of 1.8 minutes. On development data it caught 4 of 4 in time,
including 4 of 4 in leave-one-failure-out, with 12 false alerts in 174 healthy
days. The existing low-pressure alarm caught 1 of 4 with 111 false alerts.

The recipe and gates were frozen in `autoresearch/official_freeze.json` and then
scored once on MetroPT 2022 (Zenodo 6854240) and MetroPT-2 (Zenodo 7766691),
which contain three air leaks and two oil leaks.

| Untouched 2022 data | PNEUMORA detector | Existing low-pressure alarm |
|---|---|---|
| Air leaks caught in time (3) | 2, at 72 and 86 min after start | 2, at 57 and 66 min after start |
| Oil leaks caught in time (2) | 0 | 2, at 57–66 h after start |
| False alerts in 167 healthy days | 1 | 57 |

Decision: `NO_PROMOTION`. The detector passed the air-leak, workload and
random-alerter gates (p = 0.003), but did not beat the existing alarm on air
leaks: it tied on count and was 15–20 minutes later. Five external events from
2022 support only a coarse conclusion. No untouched data remains for a
post-hoc redefinition, such as treating the detector as a quieter
confirmation of the existing alarm.

## Third study: leave-one-compressor-out

`autoresearch/louo_study.py` pools all three units, nine failures (seven air
leaks, two oil leaks). For each held-out unit, a configuration is chosen on the
other two units from loaded-run, leak-physics, LPS-while-loaded, oil-temperature
residual, adaptive PCA and their OR-fusions. The gates were declared in code
before the run. This is cross-validation, not an untouched test: the physics
families were designed on MetroPT-3, and the external failures had already been
scored once.

| Held-out, pooled | PNEUMORA | Existing low-pressure alarm |
|---|---|---|
| Failures caught in time | 6 of 9 | 5 of 9 |
| Air leaks caught in time | 6 of 7 | 3 of 7 |
| False alerts per healthy day | 0.167 | 0.492 |

Decision: `NO_PROMOTION`. Catches, air leaks and the random-alerter check
(p ≈ 2e-5) passed, but the false-alert budget of 0.143 per day failed. The
oil-temperature add-on was selected in two folds, never caught an oil leak,
and added false alerts on MetroPT-3. Dropping it after seeing this result would
be outcome-driven selection, so it was not done.

## Fourth study: synthetic-trained model on all three compressors

`autoresearch/synthetic_model_study.py` trains a gradient-boosted model only on
healthy fit-window rows and 1,200 physics-based synthetic leak episodes
(`SYNTHETIC_TRAINING_ONLY`), with no real failure labels. One configuration
and the gates were declared before scoring it once on the nine real failures.

| Nine real failures | Synthetic-trained | Wrong-physics control | Existing alarm |
|---|---|---|---|
| Caught in time | 5 | 6 | 5 |
| Air leaks | 5 of 7 | 6 of 7 | 3 of 7 |
| False alerts per healthy day | 0.556 | 0.067 | 0.492 |

Decision: `NO_PROMOTION`. The control was trained on deliberately wrong leak
physics, yet it did better. The models are separating "healthy" from
"unusual"; the synthetic failure shapes add nothing. This matches the first
campaign, where synthetic augmentation also gave no lift.

## Is hours-ahead forecasting possible on this data?

Each of the nine failures was ranked against the same unit's healthy periods,
using the window from six hours before onset to two hours after. The signals
were loaded-run length, duty, idle pressure drop, pressure gain while loaded,
oil temperature and motor current. Values are percentiles of healthy
behaviour; 50 is ordinary.

- **Six to two hours before onset:** ordinary in eight of nine events. The only
  exception is F04, where duty, idle drop, oil temperature and motor current
  were already at the 95th to 100th percentile.
- **Last two hours before onset:** a clear signal in F04, X1 (oil temperature
  at the 100th percentile) and X2 (oil temperature at the 99th). F02 and F03
  reach about the 95th percentile only because the loaded run began 12 to 16
  minutes before the reported start. Healthy data sits at the 95th percentile
  5% of the time, so that level cannot be alerted on without many false alerts.
- **First hour after onset:** at the 96th to 100th percentile for six of seven
  air leaks. The exception is E2, the 30-minute dryer leak. The E3 oil leak
  stays ordinary throughout.

Most of these air leaks are abrupt, such as a burst pipe or a stuck drain
valve. Nothing in the logged signals foreshadows them hours ahead, which is why
every attempt to alert before onset scored 0 of 4. On this data, predictive
maintenance means detecting a developing failure early enough to remove the
train before it becomes non-operational, as the operator's protocol defines it.

## Product truth

Observed telemetry supports pressure, current, temperature, compressor load,
runtime and stress displays. Work orders, technicians, parts and outcomes are
`SYNTHETIC_MAINTENANCE`. Production, quality, OEE and costs are
`SYNTHETIC_FACTORY_SCENARIO`.

## Unsupported claims

PNEUMORA does not establish component diagnosis, statistically validated
remaining useful life, measured factory OEE, avoided cost, or transfer to a
different compressor. Four failure episodes cannot provide a precise estimate
of future precision.

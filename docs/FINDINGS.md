# Finding: the reference dataset made failure prediction mathematically impossible

*Investigation log — 22 September 2026*

---

## Summary

Snowflake's predictive-maintenance quickstart generates equipment failures as a **2% daily
coin flip that is statistically independent of every sensor reading**. Because the
prediction target carries no information from the features, the maximum achievable AUC for
any model is **0.5**. We verified this empirically, traced it to the generator, fixed the
generator, and reproduced the experiment: AUC rose from **0.465 to 0.766** with no change
to the model.

---

## 1. How we found it

The quickstart does not train a model. Its `FAILURE_PROBABILITY` column is arithmetic:

```sql
-- setup.sql line 918
failure_probability = 0.01 + (100 - health_score) / 90.0 * 0.94

-- setup.sql line 924
rul_days = (health_score / 100 * 500) - (days_since_decay * 0.5) - UNIFORM(0, 20, RANDOM())
```

A formula on a column, plus noise. We replaced it with a genuine supervised classifier:

- **Target:** `FAILED_IN_NEXT_7_DAYS` from `GOLD.ML_FEATURE_STORE`
- **Model:** `SNOWFLAKE.ML.CLASSIFICATION`
- **Split:** chronological — earliest 80% train, latest 20% holdout, cutoff `20250930`
- **Features:** `ASSET_ID` plus the seven engineered features. `PRESSURE_TREND_7D` is NULL
  on two-thirds of rows (not every machine has a pressure sensor), so it is coalesced to 0
  with a `HAS_PRESSURE_SENSOR` indicator

Results:

| Evaluation | AUC |
|---|---|
| Model's built-in evaluation (**random** split) | 0.877 |
| Our **chronological** holdout | **0.465** |

A 0.41 gap between a random split and a time split is not a tuning problem. And 0.465 is
*below* chance.

## 2. Why we investigated instead of tuning

The obvious moves — rebalancing, feature engineering, another algorithm — all assume the
signal exists and the model is failing to capture it. Two things argued against that:

1. **The gap pattern.** A model that scores well on a random split and at chance on a time
   split is typically memorising something periodic that a random split leaks across.
2. **Feature importance.** `DAYS_SINCE_LAST_FAILURE` dominated at 0.283 — the model was
   leaning on a *maintenance calendar*, not equipment physics.

So we read the generator.

## 3. The root cause

`setup.sql`, lines 976–982 — the maintenance work-order generator:

```sql
CASE
  WHEN MOD(day_seq, 30) = MOD(asset_id, 30) THEN 3       -- Preventive, every 30 days
  WHEN MOD(day_seq, 15) = MOD(asset_id, 15) THEN 4       -- Inspection, every 15 days
  WHEN MOD(day_seq, 20) = MOD((asset_id*2), 20) THEN 2   -- Predictive, every 20 days
  WHEN UNIFORM(0, 100, RANDOM()) < 2 THEN 1              -- Emergency repair
  ELSE NULL
END as wo_type_id
```

**No reference to `health_score`, `temperature_c`, `vibration_mm_s` or `pressure_psi`
appears anywhere in this CTE.** Work orders are produced from calendar arithmetic and one
uniform random draw.

The label only counts emergencies — `setup.sql` line 1400:

```sql
MAX(CASE
      WHEN ml.FAILURE_FLAG = TRUE
       AND ml.COMPLETED_DATE >  do.observation_date
       AND ml.COMPLETED_DATE <= DATEADD(DAY, 7, do.observation_date)
      THEN TRUE ELSE FALSE
    END) as failed_in_next_7_days
```

and `FAILURE_FLAG` is set only for `wo_type_id = 1` — the 2% random draw.

### Consequences

| Observation | Implication |
|---|---|
| Failures are an i.i.d. 2% daily Bernoulli draw | The target is **noise** |
| Noise is independent of all features | **Max achievable AUC = 0.5** |
| Our chronological AUC was 0.465 | Not a poor model — **the correct answer** |
| Random-split AUC was 0.877 | **Leakage.** `MOD(day_seq, 30)` is perfectly periodic; a random split lets the model memorise each machine's calendar phase |

**Arithmetic check.** P(at least one emergency in 7 days) = 1 − 0.98⁷ ≈ **13.2%**. Observed
positive rate: **10.76%**. Consistent with the mechanism.

*Incidental:* the comment directly above that code reads *"Emergency repairs: Randomly, 5%
chance"* while the code uses 2%.

## 4. The fix

Failures should be **caused** by degradation. We replaced the flat draw with a hazard rate
derived from the asset's own daily health score. Scheduled work — preventive, inspection,
predictive — is untouched.

```sql
daily_health AS (
    SELECT ASSET_ID, DATE_SK, AVG(HEALTH_SCORE) AS health_score
    FROM SNOWCORE_INDUSTRIES.SILVER.FCT_ASSET_TELEMETRY
    GROUP BY ASSET_ID, DATE_SK
),
maintenance_events AS (
    SELECT b.asset_id, b.process_id, b.maint_date, b.date_sk, b.day_seq,
        CASE
            WHEN MOD(b.day_seq, 30) = MOD(b.asset_id, 30) THEN 3
            WHEN MOD(b.day_seq, 15) = MOD(b.asset_id, 15) THEN 4
            WHEN MOD(b.day_seq, 20) = MOD((b.asset_id * 2), 20) THEN 2
            -- Emergency repair: hazard rises super-linearly as health degrades
            WHEN UNIFORM(0, 10000, RANDOM()) <
                 GREATEST(5, POWER(GREATEST(0, 100 - COALESCE(h.health_score, 95)) / 10.0, 2.2) * 28)
              THEN 1
            ELSE NULL
        END as wo_type_id,
        MOD((b.asset_id + b.day_seq), 10) + 1 as technician_id
    FROM daily_asset_base b
    LEFT JOIN daily_health h
      ON h.ASSET_ID = b.asset_id AND h.DATE_SK = b.date_sk
),
```

Hazard behaviour:

| Health score | Daily failure probability | Over 7 days |
|---|---|---|
| 95 (healthy) | ~0.06% | ~0.4% |
| 75 | ~2.2% | ~14% |
| 50 (degraded) | ~9.9% | ~51% |

The `GREATEST(5, ...)` floor retains rare random failures on healthy equipment, which is
physically realistic.

### Controlled for difficulty

The overall positive rate moved only 10.76% → **11.88%**. The problem is the same
difficulty; only the *cause* changed. The AUC improvement therefore cannot be attributed to
an easier target.

## 5. Result

Identical model, features, split and cutoff:

| | Before | After |
|---|---|---|
| **Chronological holdout AUC** | **0.465** | **0.766** |
| Feature-store positives | 808 (10.76%) | 892 (11.88%) |
| Train / holdout | 6,012 / 1,494 | 6,012 / 1,494 |

Feature importance also moved in the direction physics predicts:

| Feature | Before | After |
|---|---|---|
| `DAYS_SINCE_LAST_FAILURE` | 0.283 | 0.223 |
| `AVG_TEMP_LAST_24H` | 0.186 | 0.201 |
| `DOWNTIME_IMPACT_RISK` | 0.181 | 0.208 |
| `ASSET_ID` | 0.101 | **0.062** |

The model now depends less on *which* machine it is looking at and more on *what condition
that machine is in*.

## 6. Limitations we are not hiding

- **Recall at the default 0.5 threshold is 3.6%.** AUC 0.766 means the ranking is sound,
  but the default cutoff is far too conservative for maintenance. Addressed by the
  cost-based threshold selection in [`../sql/03_cost_analysis.sql`](../sql/03_cost_analysis.sql),
  which selects 0.05 and reaches 88.3% recall at 26.4% precision.
- **AUC 0.766 is good, not excellent.** The hazard function is smooth and probabilistic, so
  some failures are genuinely unpredictable by design — as in reality.
- **This is synthetic data.** The finding is about the integrity of a published reference
  dataset, not about any real factory.
- **We did not re-examine every other generated column.** Four incorrect semantic-view
  descriptions were found and fixed; there may be more.

## 7. Why this matters beyond the hackathon

This quickstart is Snowflake's published reference for predictive maintenance. Anyone
following it to evaluate Snowflake's ML capability would train a model, observe poor
generalisation, and plausibly conclude the *platform* was at fault — when the defect is in
the sample data.

The general lesson is the reusable one: **when a model fails, check whether the label could
ever have been predictable before tuning the model.** A random train/test split would have
hidden this indefinitely.

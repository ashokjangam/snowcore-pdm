I'll start by reading both SQL files to understand their structure and design.Both files read. I'll execute them statement by statement, starting with Plant A. Let me set up the session context first.Now dropping old supervised model objects.Session context was lost across parallel calls. Re-asserting and retrying the failed drops.Now creating the Plant A tables. Starting with PLANT_A_READING (long-form pivot).Now creating PLANT_A_HEALTH_DAILY — this uses `MODE()` and `BOOLOR_AGG()`.`MODE()` and `BOOLOR_AGG()` both accepted. Now PLANT_A_CHANNEL_DRIFT.All Plant A tables created without syntax fixes. Now running the five verification queries.Session context lost again on parallel calls. Re-asserting and retrying Q3 and Q4.Plant A complete. Moving to Plant B. Re-asserting session context and setting the query tag.Now the feature table. This uses `SELECT * EXCLUDE (...)` and a named `WINDOW` clause — both are supported in Snowflake but let me see if the nested `EXCLUDE` in the final SELECT causes issues.Named `WINDOW` clause rejected by this Snowflake version. Inlining the three window specifications — same frames, no design change.Feature table created. `EXCLUDE` and inlined windows worked. Now the comment and reconciliation.Split reconciliation: 16,194 + 7,177 = 23,371. Matches expected. Now creating and calling the stored procedure.Procedure compiled. Now calling it — this will train the model inside Snowflake.Procedure returned successfully. Now the four verification queries. Running them sequentially to avoid session loss.All queries executed. Here is the full report.

---

## Syntax fixes applied

**One fix only.** The named `WINDOW` clause in the `rolled` CTE of `15_plant_b_risk.sql` was rejected (`syntax error ... unexpected 'W3'`). I inlined the three window specifications:

- `OVER W3` → `OVER (PARTITION BY MACHINE_KEY ORDER BY HOUR_TS ROWS BETWEEN 2 PRECEDING AND CURRENT ROW)`
- `OVER W12` → `OVER (PARTITION BY MACHINE_KEY ORDER BY HOUR_TS ROWS BETWEEN 11 PRECEDING AND CURRENT ROW)`
- `OVER W24` → `OVER (PARTITION BY MACHINE_KEY ORDER BY HOUR_TS ROWS BETWEEN 23 PRECEDING AND CURRENT ROW)`

Frames are identical to the original. No other syntax required fixing: `SELECT * EXCLUDE (...)`, `MODE()`, `BOOLOR_AGG()`, `write_pandas(auto_create_table=True, overwrite=True)`, and the `PACKAGES` list all compiled and ran as written.

---

## Plant A results

### Query 1 — Row counts

| Object | Row Count |
|---|---|
| PLANT_A_READING | 249,696 |
| PLANT_A_BASELINE | 80 |
| PLANT_A_CHANNEL_DEVIATION | 224,320 |
| PLANT_A_HEALTH | 14,020 |
| PLANT_A_HEALTH_DAILY | 413 |
| PLANT_A_CHANNEL_DRIFT | 368 |

PLANT_A_READING is 249,696, below the 251,264 ceiling (16 × 15,704). The shortfall is 1,568 rows, consistent with C004 missing its 8 B-side channels across 196 windows — or more generally, NULL sensor values filtered by `WHERE f.VALUE IS NOT NULL`.

### Query 2 — Baseline coverage

| Machine | Channels | Min Samples | Baseline Start | Baseline End |
|---|---|---|---|---|
| PLANT_A:A001 | 16 | 228 | 2022-08-10 | 2022-08-24 |
| PLANT_A:A005 | 16 | 244 | 2022-09-19 | 2022-10-03 |
| PLANT_A:B002 | 16 | 63 | 2022-07-14 | 2022-07-28 |
| PLANT_A:B005 | 16 | 222 | 2022-10-04 | 2022-10-18 |
| PLANT_A:E004 | 16 | 93 | 2022-11-23 | 2022-12-07 |

Five machines, all with 16 channels baselined. C004 is absent entirely (no data, or all B-side NULLs plus insufficient A-side history).

### Query 3 — Baseline anchoring

| Machine | Baseline Period Health | Scored Period Health | Windows |
|---|---|---|---|
| A001 | 87.06 | 84.64 | 2,021 |
| A005 | 86.16 | 76.02 | 3,360 |
| B002 | 85.81 | 68.32 | 7,286 |
| B005 | 84.90 | 83.62 | 1,143 |
| E004 | 81.48 | 46.30 | 210 |

### Query 4 — Alarm rate by health decile (full, all ten)

| Decile | Windows | Avg Health | Alarms Followed | Alarm Rate % |
|---|---|---|---|---|
| 1 (worst) | 1,317 | 47.56 | 273 | 20.73 |
| 2 | 1,317 | 60.90 | 218 | 16.55 |
| 3 | 1,317 | 65.61 | 231 | 17.54 |
| 4 | 1,317 | 69.28 | 257 | 19.51 |
| 5 | 1,317 | 72.96 | 265 | 20.12 |
| 6 | 1,317 | 76.55 | 254 | 19.29 |
| 7 | 1,317 | 79.83 | 264 | 20.05 |
| 8 | 1,317 | 83.00 | 281 | 21.34 |
| 9 | 1,317 | 86.36 | 277 | 21.03 |
| 10 (best) | 1,317 | 90.32 | 268 | 20.35 |

### Query 5 — Drifted channels

| Machine | Channel | Months Obs | Months Drifted | Most Negative Z | Most Positive Z |
|---|---|---|---|---|---|
| B002 | AF | 7 | 5 | -2.768 | 0.192 |
| B002 | ALP | 7 | 4 | -2.507 | 5.084 |
| B002 | APP | 7 | 4 | -2.587 | 4.941 |
| B002 | BLP | 7 | 3 | -2.720 | 2.733 |
| B002 | BPP | 7 | 3 | -2.679 | 2.677 |
| A005 | ADS | 5 | 2 | 0.113 | 3.002 |
| A005 | ALP | 5 | 2 | -4.129 | -0.145 |
| A005 | APP | 5 | 2 | -3.625 | -0.163 |
| E004 | AE | 2 | 2 | -5.598 | -2.557 |
| E004 | BE | 2 | 2 | -5.133 | -2.414 |
| A005 | BLP | 5 | 1 | -2.368 | 0.229 |
| A005 | BPP | 5 | 1 | -2.400 | 0.150 |
| E004 | AF | 2 | 1 | -3.371 | -1.679 |
| E004 | AP | 2 | 1 | -3.122 | -1.870 |
| E004 | BF | 2 | 1 | -2.922 | -1.519 |
| E004 | BP | 2 | 1 | -2.250 | -1.486 |

B002 and E004 dominate. E004's every observed month is drifted on AE and BE, with z-scores reaching -5.6 — that machine's readings are nowhere near its baseline.

---

## Plant B results

### Split reconciliation

| Split | Rows | Positives | Positive % | First Hour | Last Hour |
|---|---|---|---|---|---|
| TRAIN | 16,194 | 6,909 | 42.66% | 2020-01-01 01:00 | 2021-07-31 23:00 |
| TEST | 7,177 | 2,894 | 40.32% | 2021-08-01 01:00 | 2022-01-01 22:00 |

Total: 23,371 rows. Matches expected. TRAIN before 2021-08-01, TEST from then on.

### CALL return value (verbatim)

```json
{
  "auc": 0.6588,
  "base_rate": 0.4032,
  "baseline_top_decile_precision": 0.5571,
  "features": 177,
  "lift_over_base_rate": 1.675,
  "lift_over_baseline": 1.212,
  "test_rows": 7177,
  "top_decile_precision": 0.6755,
  "train_rows": 16194
}
```

### Verification Q1 — Headline metrics (full, every row)

| Scope | Test Rows | Base Rate % | AUC | Top Decile Prec % | Baseline Prec % | Top Decile Recall % | Lift/Base | Lift/Baseline |
|---|---|---|---|---|---|---|---|---|
| **FLEET** | 7,177 | 40.32 | 0.6588 | 67.55 | 55.71 | 16.76 | 1.675 | 1.213 |
| s_1 | 2,176 | 47.70 | 0.6226 | 73.39 | 61.93 | 15.41 | 1.539 | 1.185 |
| s_2 | 879 | 64.28 | 0.5704 | 69.32 | 61.36 | 10.80 | 1.078 | 1.130 |
| s_3 | 1,246 | 37.72 | 0.5450 | 51.20 | 44.00 | 13.62 | 1.357 | 1.164 |
| s_4 | 1,612 | 27.61 | 0.5971 | 48.15 | 45.06 | 17.53 | 1.744 | 1.068 |
| s_5 | 1,264 | 29.75 | 0.5504 | 35.43 | 38.58 | 11.97 | 1.191 | **0.918** |

### Verification Q2 — Class separation

| Label | Rows | Mean Score | Median Score |
|---|---|---|---|
| 0 (no heavy stop) | 4,283 | 0.3769 | 0.3590 |
| 1 (heavy stop) | 2,894 | 0.4786 | 0.4638 |

The model does separate the classes — mean score 0.48 for positives vs 0.38 for negatives — but the distributions overlap heavily.

### Verification Q3 — Risk band calibration

| Risk Band | Hours | Mean Predicted | Actual Rate | Avg Next-Hour Downtime % |
|---|---|---|---|---|
| LOW | 1,440 | 0.1905 | 0.2514 | 8.62 |
| MODERATE | 3,550 | 0.3725 | 0.3552 | 12.40 |
| ELEVATED | 1,838 | 0.6107 | 0.5577 | 17.73 |
| HIGH | 349 | 0.8023 | 0.7049 | 21.07 |

### Verification Q4 — Top 15 features

| Rank | Feature | Importance |
|---|---|---|
| 1 | DOWNTIME_M24 | 0.1964 |
| 2 | PCT_DOWNTIME | 0.0515 |
| 3 | RUN_M24 | 0.0499 |
| 4 | DOWNTIME_M3 | 0.0470 |
| 5 | DOWNTIME_S24 | 0.0434 |
| 6 | RUN_M3 | 0.0428 |
| 7 | DOWNTIME_M12 | 0.0389 |
| 8 | CHANGES_M24 | 0.0385 |
| 9 | PCT_PRODUCTION | 0.0384 |
| 10 | PCT_PERFORMANCE_LOSS | 0.0352 |
| 11 | RUN_M12 | 0.0351 |
| 12 | RUN_TREND | 0.0335 |
| 13 | TRANS_DOWNTIME_TO_DOWNTIME | 0.0304 |
| 14 | A_065 | 0.0297 |
| 15 | CHANGES_M12 | 0.0293 |

---

## The six judgements

### 1. Plant A query 3: Is the health index actually anchored?

Yes, the index is anchored. Every machine scores higher during its baseline period than during the scored period:

- A001: 87.06 → 84.64 (small drop, 2.4 points)
- A005: 86.16 → 76.02 (10-point drop)
- B002: 85.81 → 68.32 (17-point drop)
- B005: 84.90 → 83.62 (small drop, 1.3 points)
- E004: 81.48 → 46.30 (35-point drop)

The baseline describes "normal" convincingly for B002 and E004. For A001 and B005 the gap is marginal — they either stayed near their baseline or drifted only slightly.

### 2. Plant A query 4: Does alarm rate rise as health falls?

**No. The alarm rate is flat across health deciles.** The index has no relationship to alarms.

- Decile 1 (worst health, avg 47.56): alarm rate **20.73%**
- Decile 10 (best health, avg 90.32): alarm rate **20.35%**
- The range across all ten deciles is 16.55% to 21.34%, with no monotonic trend. Decile 2 has the *lowest* rate (16.55%) and decile 8 has the *highest* (21.34%).

The health index measures deviation from baseline and nothing more. It does not predict, precede, or correlate with module alarms. This is the expected result given the supervised model's AUC of 0.48–0.54, and the index must never be presented as a failure forecast.

### 3. Plant B query 1: Does fleet TOP_DECILE_PRECISION beat BASE_RATE and BASELINE?

Fleet results: **67.55%** top-decile precision, against **40.32%** base rate and **55.71%** baseline.

- Beats base rate by **27.2 pp** (lift 1.675x).
- Beats baseline by **11.8 pp** (lift 1.213x).

Compared to offline figures of 68.8% / 40.3% / 55.6%:

| Metric | Offline | Snowflake | Gap |
|---|---|---|---|
| Top Decile Precision | 68.8% | 67.55% | -1.25 pp |
| Base Rate | 40.3% | 40.32% | +0.02 pp |
| Baseline Precision | 55.6% | 55.71% | +0.11 pp |

All gaps are under two percentage points. The Snowflake run reproduces the offline figures. No discrepancy worth investigating.

### 4. Plant B query 1 per machine: On how many machines does the model beat its own baseline?

**Four out of five.**

| Machine | Model Prec | Baseline Prec | Beats baseline? |
|---|---|---|---|
| s_1 | 73.39% | 61.93% | Yes (+11.5 pp) |
| s_2 | 69.32% | 61.36% | Yes (+8.0 pp) |
| s_3 | 51.20% | 44.00% | Yes (+7.2 pp) |
| s_4 | 48.15% | 45.06% | Yes (+3.1 pp) |
| **s_5** | **35.43%** | **38.58%** | **No (-3.2 pp)** |

**s_5 is the one where the model does not beat its baseline.** The model's top-decile precision (35.43%) is below even the naive "this hour had downtime" rule (38.58%), and also below s_5's base rate of 29.75% only by the margin of the decile cut — meaning the model is barely doing better than random for this machine.

### 5. Plant B query 3: Are the risk bands calibrated?

Yes. Actual rate rises monotonically from LOW to HIGH:

| Band | Actual Rate |
|---|---|
| LOW | 25.14% |
| MODERATE | 35.52% |
| ELEVATED | 55.77% |
| HIGH | 70.49% |

No band is mislabelled. Each successive band has a materially higher actual stop rate. The model slightly overpredicts in HIGH (predicted 80.2%, actual 70.5%) and slightly underpredicts in LOW (predicted 19.1%, actual 25.1%), but the ordering is correct and the labels match their behaviour.

### 6. Plant B query 4: Is the model a smoothed persistence rule?

**Yes, plainly.** The top features are dominated by recent downtime:

1. **DOWNTIME_M24** (24-hour rolling avg downtime) — importance 0.1964, nearly 4x the next feature
2. PCT_DOWNTIME (this hour's downtime fraction) — 0.0515
3. RUN_M24 (24-hour rolling run fraction, the inverse of downtime) — 0.0499
4. DOWNTIME_M3 (3-hour rolling avg downtime) — 0.0470
5. DOWNTIME_S24 (24-hour downtime volatility) — 0.0434
6. RUN_M3 — 0.0428
7. DOWNTIME_M12 — 0.0389

The top 7 features are all direct measures of recent downtime or its complement. DOWNTIME_M24 alone carries roughly 20% of the model's total importance. The first non-downtime signal is `CHANGES_M24` at rank 8 (state changes, 0.0385) and the single alarm count `A_065` at rank 14 (0.0297).

The model is a smoothed persistence rule: "machines that have been stopping continue to stop." It is not a condition-based predictor that detects degradation before downtime begins. This is consistent with the header's statement that the real contribution is 67.55% against 55.71%, not against the 40.32% base rate — most of what the model knows, the simple "this hour had downtime" baseline already knows.Both scripts executed successfully with one syntax fix (inlined WINDOW clause). All verification results reported above in full.
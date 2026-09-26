I'll execute the SQL statements in order. Starting with the setup and file staging.Setup done. Now staging the SQL files.Both files uploaded. Now refreshing the stage and executing them.Both scripts executed successfully. Now running the check queries.Now running the work order generation and remaining checks.Error on `GENERATE_RISK_WORK_ORDERS(8, 'LINE')`:

> **Stored procedure execution error: Scoped transaction started in stored procedure is incomplete and it was rolled back.**

Stopping here as instructed. The FLEET-scope work orders succeeded, but the LINE-scope call failed with the above transaction error.

---

Here are all results collected so far:

### 1. Failure Label Splits

| SPLIT_PART | N_ROWS | COMPLETE_ROWS | COVERAGE_50 | POSITIVE_RATE |
|---|---|---|---|---|
| FINAL_BLIND_TEST | 1566 | 1340 | 1495 | 0.250000 |
| PURGED_BOUNDARY | 4 | 4 | 4 | 0.000000 |
| TRAIN | 21801 | 19093 | 21088 | 0.242497 |

### 2. Failure Metrics (with baselines)

| SCOPE | TEST_ROWS | BASE_RATE | MODEL_AUC | PERSISTENCE_AUC | RECENT_AUC | LINE_RATE_AUC | MODEL_TOP_DECILE_PRECISION | PERSISTENCE_TOP_DECILE_PRECISION | RECENT_TOP_DECILE_PRECISION | LINE_RATE_TOP_DECILE_PRECISION | MODEL_TOP_DECILE_RECALL | BEST_BASELINE | MODEL_ADVANTAGE_PTS | VERDICT | TRAIN_ROWS | EXCLUDED_INCOMPLETE_ROWS |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| FLEET | 1340 | 0.25 | 0.7322 | 0.6050 | 0.6616 | 0.7005 | 0.6269 | 0.3806 | 0.4104 | 0.5821 | 0.2507 | LINE_RATE | 4.48 | MODEL_BEATS_BEST_BASELINE | 19093 | 2934 |
| s_1 | 397 | 0.3149 | 0.5424 | 0.5411 | 0.5236 | 0.5411 | 0.425 | 0.425 | 0.225 | 0.425 | 0.136 | PERSISTENCE | 0 | MODEL_DOES_NOT_BEAT_BEST_BASELINE | 19093 | 2934 |
| s_2 | 156 | 0.5897 | 0.6437 | 0.4569 | 0.5820 | 0.4569 | 0.625 | 0.375 | 0.75 | 0.375 | 0.1087 | RECENT | -12.5 | MODEL_DOES_NOT_BEAT_BEST_BASELINE | 19093 | 2934 |
| s_3 | 205 | 0.2 | 0.5570 | 0.5756 | 0.4298 | 0.5756 | 0.2381 | 0.2857 | 0.1905 | 0.2857 | 0.1220 | PERSISTENCE | -4.76 | MODEL_DOES_NOT_BEAT_BEST_BASELINE | 19093 | 2934 |
| s_4 | 273 | 0.1136 | 0.6508 | 0.6514 | 0.5628 | 0.6514 | 0.25 | 0.2857 | 0.25 | 0.2857 | 0.2258 | PERSISTENCE | -3.57 | MODEL_DOES_NOT_BEAT_BEST_BASELINE | 19093 | 2934 |
| s_5 | 309 | 0.1489 | 0.7666 | 0.5744 | 0.7691 | 0.5744 | 0.4516 | 0.2903 | 0.4839 | 0.2903 | 0.3043 | RECENT | -3.23 | MODEL_DOES_NOT_BEAT_BEST_BASELINE | 19093 | 2934 |

### 3. Feature Importance (Top 10)

| FEATURE | IMPORTANCE |
|---|---|
| MACHINE_S_1 | 0.0772 |
| MACHINE_S_5 | 0.0709 |
| RUN_FRAC_MEAN_72 | 0.0411 |
| PCT_DOWNTIME_MEAN_72 | 0.0404 |
| MACHINE_S_2 | 0.0344 |
| RUN_FRAC_MEAN_24 | 0.0329 |
| MACHINE_S_4 | 0.0327 |
| PCT_DOWNTIME_MEAN_24 | 0.0243 |
| HOUR_SIN | 0.0159 |
| MACHINE_S_3 | 0.0155 |

### 4. Failure Scores

| SCORED | FLAGGED_FLEET | FLAGGED_LINE | NON_BLIND |
|---|---|---|---|
| 1340 | 134 | 136 | 0 |

### 5. Work Order Summary (FLEET scope)

| PLANT_CODE | SCOPE | AUTO_WORK_ORDERS | CONFIRMED_WITHIN_4H | HIT_RATE | RANDOM_HOUR_HIT_RATE | LIFT_VS_RANDOM | SCOPE_BASE_RATE | MEDIAN_LEAD_TIME_MIN | ORDERS_WITH_KIT_RISK | BREAKDOWNS_IN_PERIOD | BREAKDOWNS_COVERED | COVERAGE_RATE | DATA_ORIGIN |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| PLANT_B | FLEET | 31 | 20 | 0.6452 | 0.5543 | 1.1640 | 0.25 | 97.5 | 20 | 196 | 61 | 0.3112 | SYNTHETIC_IT orders; outcomes OBSERVED |
| PLANT_B | s_1 | 4 | 2 | 0.5000 | 0.3149 | 1.588 | 0.3149 | 117.5 | 2 | 69 | 8 | 0.1159 | SYNTHETIC_IT orders; outcomes OBSERVED |
| PLANT_B | s_2 | 27 | 18 | 0.6667 | 0.5897 | 1.1304 | 0.5897 | 86.0 | 18 | 59 | 53 | 0.8983 | SYNTHETIC_IT orders; outcomes OBSERVED |
| PLANT_B | s_3 | 0 | 0 | NULL | NULL | NULL | 0.2 | NULL | 0 | 30 | 0 | 0.0000 | SYNTHETIC_IT orders; outcomes OBSERVED |
| PLANT_B | s_4 | 0 | 0 | NULL | NULL | NULL | 0.1136 | NULL | 0 | 12 | 0 | 0.0000 | SYNTHETIC_IT orders; outcomes OBSERVED |
| PLANT_B | s_5 | 0 | 0 | NULL | NULL | NULL | 0.1489 | NULL | 0 | 26 | 0 | 0.0000 | SYNTHETIC_IT orders; outcomes OBSERVED |

### 6. LINE scope — ERROR

```
CALL SNOWCORE_REAL.GOLD.GENERATE_RISK_WORK_ORDERS(8, 'LINE')
```

**Error:** `Stored procedure execution error: Scoped transaction started in stored procedure is incomplete and it was rolled back.`
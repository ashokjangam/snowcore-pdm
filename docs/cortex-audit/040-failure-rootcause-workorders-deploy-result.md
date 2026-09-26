I'll execute these statements in order. Starting with the setup and PUT/EXECUTE commands.Now running the PUT commands.All 3 files uploaded. Now refreshing the stage and executing the scripts.All 3 scripts executed successfully. Now running the read-only checks.The failure label query failed because `ROWS` is a reserved keyword. Re-running with a quoted alias.All statements completed. Here are the full results:

---

### 1. PLANT_B_FAILURE_LABEL splits

| SPLIT_PART | ROWS | COMPLETE_ROWS | POSITIVE_RATE | FIRST_HOUR | LAST_HOUR |
|---|---|---|---|---|---|
| TRAIN | 21801 | 7309 | 0.296347 | 2020-01-01 01:00 | 2021-11-30 19:00 |
| PURGED_BOUNDARY | 4 | 1 | 0.000000 | 2021-11-30 20:00 | 2021-11-30 23:00 |
| FINAL_BLIND_TEST | 1566 | 482 | 0.311203 | 2021-12-01 00:00 | 2022-01-01 22:00 |

### 2. PLANT_B_FAILURE_METRICS

| SCOPE | TEST_ROWS | BASE_RATE | MODEL_AUC | PERSISTENCE_AUC | RECENT_AUC | MODEL_TOP_DECILE_PRECISION | PERSISTENCE_TOP_DECILE_PRECISION | RECENT_TOP_DECILE_PRECISION | MODEL_TOP_DECILE_RECALL | BEST_BASELINE | MODEL_ADVANTAGE_PTS | VERDICT | TRAIN_ROWS | EXCLUDED_INCOMPLETE_ROWS | FLAG_THRESHOLD_SCORE |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| FLEET | 482 | 0.3112 | 0.7487 | 0.6136 | 0.6978 | 0.7755 | 0.4694 | 0.5918 | 0.2533 | RECENT_BREAKDOWNS | 18.37 | MODEL_BEATS_BEST_BASELINE | 7309 | 15579 | 0.7427 |
| s_1 | 144 | 0.3611 | 0.5656 | 0.5725 | 0.5297 | 0.7333 | 0.6 | 0.5333 | 0.2115 | PERSISTENCE | 13.33 | MODEL_BEATS_BEST_BASELINE | 7309 | 15579 | 0.7427 |
| s_2 | 47 | 0.7660 | 0.6136 | 0.4823 | 0.7045 | 1.0 | 0.6 | 1.0 | 0.1389 | RECENT_BREAKDOWNS | 0 | MODEL_DOES_NOT_BEAT_BEST_BASELINE | 7309 | 15579 | 0.7427 |
| s_3 | 63 | 0.3175 | 0.3651 | 0.5477 | 0.3395 | 0 | 0.2857 | 0.1429 | 0 | PERSISTENCE | -28.57 | MODEL_DOES_NOT_BEAT_BEST_BASELINE | 7309 | 15579 | 0.7427 |
| s_4 | 137 | 0.1168 | 0.7903 | 0.7138 | 0.7020 | 0.4286 | 0.3571 | 0.4286 | 0.375 | RECENT_BREAKDOWNS | 0 | MODEL_DOES_NOT_BEAT_BEST_BASELINE | 7309 | 15579 | 0.7427 |
| s_5 | 91 | 0.2857 | 0.8728 | 0.5615 | 0.8089 | 0.7 | 0.6 | 0.4 | 0.2692 | PERSISTENCE | 10 | MODEL_BEATS_BEST_BASELINE | 7309 | 15579 | 0.7427 |

### 3. PLANT_B_FAILURE_IMPORTANCE (top 10)

| FEATURE | IMPORTANCE |
|---|---|
| MACHINE_S_1 | 0.1274 |
| MACHINE_S_4 | 0.0664 |
| MACHINE_S_2 | 0.0607 |
| MACHINE_S_5 | 0.0442 |
| RUN_FRAC_MEAN_72 | 0.0441 |
| PCT_DOWNTIME_MEAN_72 | 0.0432 |
| RUN_FRAC_MEAN_24 | 0.0312 |
| PCT_DOWNTIME_MEAN_24 | 0.0206 |
| RUN_FRAC_MEAN_12 | 0.0167 |
| DOW_SIN | 0.0144 |

### 4. PLANT_B_FAILURE_SCORE summary

| SCORED | NON_BLIND | FLAGGED | EXPECTED_FLAGGED |
|---|---|---|---|
| 482 | 0 | 49 | 49 |

### 5. Alignment check (long events vs hourly downtime)

| LONG_EVENTS | IN_HOUR_WITH_DOWNTIME |
|---|---|
| 2556 | 2556 |

100% alignment -- all 2556 long breakdown events fall in hours with non-zero PCT_DOWNTIME.

### 6. V_ROOT_CAUSE_ALARM by machine

| MACHINE_CODE | CODES | LONG_BREAKDOWNS | HOURS | TOP_CODE | TOP_SHARE_PCT | TOP_PATTERN |
|---|---|---|---|---|---|---|
| s_1 | 43 | 1305 | 492.3 | A_065 | 63.6 | REPEATS_WITHIN_A_DAY |
| s_2 | 16 | 605 | 234.9 | A_001 | 53.2 | CLOCK_BAND_CLUSTERED |
| s_3 | 12 | 268 | 207.4 | A_006 | 87.6 | CLOCK_BAND_CLUSTERED |
| s_4 | 19 | 158 | 86.3 | A_006 | 50.4 | CLOCK_BAND_CLUSTERED |
| s_5 | 10 | 220 | 60.4 | A_101 | 89.5 | SHORT_STOPS_COME_FIRST |

### 7. V_RISK_WORK_ORDER_SUMMARY

| PLANT_CODE | SCOPE | AUTO_WORK_ORDERS | CONFIRMED_WITHIN_4H | HIT_RATE | RANDOM_HOUR_HIT_RATE | MEDIAN_LEAD_TIME_MIN | ORDERS_WITH_KIT_RISK | BREAKDOWNS_IN_PERIOD | BREAKDOWNS_COVERED | COVERAGE_RATE | DATA_ORIGIN |
|---|---|---|---|---|---|---|---|---|---|---|---|
| PLANT_B | FLEET | 17 | 14 | 0.8235 | 0.3112 | 61.0 | 9 | 196 | 38 | 0.1939 | SYNTHETIC_IT orders; outcomes OBSERVED |
| PLANT_B | s_1 | 1 | 1 | 1.0000 | 0.3611 | 61.0 | 0 | 69 | 4 | 0.0580 | SYNTHETIC_IT orders; outcomes OBSERVED |
| PLANT_B | s_2 | 16 | 13 | 0.8125 | 0.7660 | 61.0 | 9 | 59 | 34 | 0.5763 | SYNTHETIC_IT orders; outcomes OBSERVED |
| PLANT_B | s_3 | 0 | 0 | NULL | 0.3175 | NULL | 0 | 30 | 0 | 0.0000 | SYNTHETIC_IT orders; outcomes OBSERVED |
| PLANT_B | s_4 | 0 | 0 | NULL | 0.1168 | NULL | 0 | 12 | 0 | 0.0000 | SYNTHETIC_IT orders; outcomes OBSERVED |
| PLANT_B | s_5 | 0 | 0 | NULL | 0.2857 | NULL | 0 | 26 | 0 | 0.0000 | SYNTHETIC_IT orders; outcomes OBSERVED |

### 8. RISK_WORK_ORDER (first 8)

| RISK_WORK_ORDER_ID | MACHINE_CODE | ISSUED_AT | PRIORITY | EPISODE_FLAGGED_HOURS | TOP_RECENT_ALARM | STOCK_STATE | OUTCOME | LEAD_TIME_MIN |
|---|---|---|---|---|---|---|---|---|
| RWO-B-s_2-2021120304 | s_2 | 2021-12-03 04:00 | P3 | 2 | A_020 | HEALTHY | NO_BREAKDOWN_WITHIN_4H | NULL |
| RWO-B-s_2-2021120604 | s_2 | 2021-12-06 04:00 | P2 | 2 | A_011 | STOCKOUT | NO_BREAKDOWN_WITHIN_4H | NULL |
| RWO-B-s_2-2021120704 | s_2 | 2021-12-07 04:00 | P2 | 2 | A_101 | REORDER | BREAKDOWN_WITHIN_4H | 41 |
| RWO-B-s_1-2021120710 | s_1 | 2021-12-07 10:00 | P3 | 5 | A_065 | HEALTHY | BREAKDOWN_WITHIN_4H | 61 |
| RWO-B-s_2-2021120813 | s_2 | 2021-12-08 13:00 | P3 | 1 | A_006 | HEALTHY | BREAKDOWN_WITHIN_4H | 66 |
| RWO-B-s_2-2021121004 | s_2 | 2021-12-10 04:00 | P3 | 3 | A_020 | HEALTHY | NO_BREAKDOWN_WITHIN_4H | NULL |
| RWO-B-s_2-2021121109 | s_2 | 2021-12-11 09:00 | P3 | 2 | A_101 | REORDER | BREAKDOWN_WITHIN_4H | 22 |
| RWO-B-s_2-2021121412 | s_2 | 2021-12-14 12:00 | P3 | 3 | A_011 | STOCKOUT | BREAKDOWN_WITHIN_4H | 18 |

### 9. PLANT_B_RISK_SCORE row count

| RISK_TABLE_ROWS |
|---|
| 1566 |

---

All statements succeeded. The only hiccup was the reserved keyword `ROWS` in the label query alias, which was resolved by quoting it.
Running all 10 queries now.## A. Interval states

| STATE_TYPE | INTERVALS | WITH_ALARM | HOURS |
|---|---|---|---|
| production | 146795 | 146795 | 19390.1 |
| idle | 50149 | 50149 | 10266 |
| scheduled_downtime | 21782 | 21782 | 6534.2 |
| performance_loss | 118584 | 118584 | 4792.8 |
| downtime | 92084 | 92084 | 3147.4 |

## B. Coverage window and line count

| FIRST_TS | LAST_TS | LINES | INTERVAL_ROWS |
|---|---|---|---|
| 2020-01-01 00:05:02.863 +0000 | 2022-01-01 23:41:35.677 +0000 | 5 | 429394 |

## C. Per line OEE and loss hours

| MACHINE_CODE | OEE | A | P | Q | BREAKDOWN_H | IDLE_H | PACKAGES_OUT | WORK_ORDER_COUNT | LAST_RISK | RISK_BAND | MODEL_VS_BASELINE_TRUST |
|---|---|---|---|---|---|---|---|---|---|---|---|
| s_1 | 0.5643 | 0.7765 | 0.7279 | 0.9984 | 1393.4 | 1267.1 | 33648657 | 1305 | 0.5206 | ELEVATED | MODEL_OUTPERFORMS_PERSISTENCE |
| s_2 | 0.2885 | 0.4131 | 0.703 | 0.9933 | 573.8 | 1869.8 | 7858499 | 605 | 0.6682 | HIGH | MODEL_OUTPERFORMS_PERSISTENCE |
| s_3 | 0.3617 | 0.4921 | 0.7368 | 0.9975 | 466.3 | 2967.0 | 11765356 | 268 | 0.5129 | ELEVATED | MODEL_OUTPERFORMS_PERSISTENCE |
| s_4 | 0.3745 | 0.6912 | 0.5439 | 0.9962 | 358.4 | 1534.9 | 14984301 | 158 | 0.5537 | ELEVATED | MODEL_OUTPERFORMS_PERSISTENCE |
| s_5 | 0.5712 | 0.6546 | 0.8748 | 0.9974 | 355.6 | 2627.1 | 32143109 | 220 | 0.2924 | LOW | MODEL_DOES_NOT_OUTPERFORM_PERSISTENCE |

## D. Site KPI

| OEE | A | P | Q | BREAKDOWN_H | IDLE_H | WORK_ORDER_COUNT | STOCK_RISK_COUNT | EXPOSURE_EUR |
|---|---|---|---|---|---|---|---|---|
| 0.4678 | 0.6432 | 0.7293 | 0.9972 | 3147.4 | 10266.0 | 2556 | 15 | 21387467 |

## E. Top 8 breakdown alarm codes by stop hours

| CAUSE_CODE | ORDERS | STOP_HOURS |
|---|---|---|
| A_065 | 805 | 313.2 |
| A_006 | 422 | 289.3 |
| A_001 | 478 | 183.6 |
| A_101 | 295 | 79.5 |
| A_066 | 137 | 52.5 |
| A_016 | 61 | 26 |
| A_005 | 44 | 17.5 |
| A_045 | 13 | 16.1 |

## F. Maintenance cost versus waiting cost

| KIND | EVENTS | HOURS | LABOUR_EUR | PARTS_EUR | FORGONE_EUR |
|---|---|---|---|---|---|
| BREAKDOWN | 2556 | 1081.2 | 36499 | 85852 | 1068641 |
| IDLE | 3592 | 8059.6 | 0 | 0 | 8368071 |

## G. Work-order priority mix

| PRIORITY | ORDERS |
|---|---|
| P1 | 21 |
| P2 | 23 |
| P3 | 68 |
| P4 | 2444 |

## H. Stock states

| STOCK_STATE | MATERIALS |
|---|---|
| HEALTHY | 13 |
| REORDER | 11 |
| STOCKOUT | 4 |

## I. Downtime event durations

| STOP_STATE | EVENTS | MEDIAN_MIN | P90_MIN | HOURS |
|---|---|---|---|---|
| downtime | 92084 | 0.89 | 4 | 3147.5 |
| idle | 50149 | 1.25 | 17.1 | 10266 |

## J. Hourly target base rate by month

| MONTH | HOURS | HEAVY_STOP_RATE |
|---|---|---|
| 2020-01 | 800 | 0.3838 |
| 2020-02 | 1008 | 0.3562 |
| 2020-03 | 837 | 0.3274 |
| 2020-04 | 732 | 0.3525 |
| 2020-05 | 692 | 0.3396 |
| 2020-06 | 719 | 0.3435 |
| 2020-07 | 753 | 0.4847 |
| 2020-08 | 769 | 0.3433 |
| 2020-09 | 616 | 0.4513 |
| 2020-10 | 893 | 0.4311 |
| 2020-11 | 705 | 0.5532 |
| 2020-12 | 704 | 0.5369 |
| 2021-01 | 522 | 0.5460 |
| 2021-02 | 375 | 0.5733 |
| 2021-03 | 553 | 0.4810 |
| 2021-04 | 1244 | 0.4124 |
| 2021-05 | 1469 | 0.4275 |
| 2021-06 | 1532 | 0.3975 |
| 2021-07 | 1271 | 0.5138 |
| 2021-08 | 1204 | 0.4302 |
| 2021-09 | 1360 | 0.3507 |
| 2021-10 | 1452 | 0.3843 |
| 2021-11 | 1595 | 0.4063 |
| 2021-12 | 1546 | 0.4431 |
| 2022-01 | 20 | 0.4000 |

All 10 queries returned successfully.
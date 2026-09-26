I'll run all four queries in parallel to get the data from these views.Here are the results:

---

### V_RISK_WORK_ORDER_SUMMARY

| SCOPE | AUTO_WORK_ORDERS | CONFIRMED_WITHIN_4H | HIT_RATE | RANDOM_RATE | LIFT | MEDIAN_LEAD_TIME_MIN | ORDERS_WITH_KIT_RISK | BREAKDOWNS_IN_PERIOD | BREAKDOWNS_COVERED | COVERAGE_RATE |
|-------|-----------------|---------------------|----------|-------------|------|---------------------|---------------------|---------------------|-------------------|--------------|
| FLEET | 45 | 16 | 0.3556 | 0.2816 | 1.263 | 97.000 | 28 | 196 | 45 | 0.2296 |
| s_1 | 12 | 6 | 0.5000 | 0.3149 | 1.588 | 23.000 | 3 | 69 | 16 | 0.2319 |
| s_2 | 8 | 5 | 0.6250 | 0.5897 | 1.06 | 172.000 | 4 | 59 | 11 | 0.1864 |
| s_3 | 13 | 3 | 0.2308 | 0.2 | 1.154 | 89.000 | 9 | 30 | 6 | 0.2000 |
| s_4 | 6 | 1 | 0.1667 | 0.1136 | 1.468 | 147.000 | 6 | 12 | 3 | 0.2500 |
| s_5 | 6 | 1 | 0.1667 | 0.1489 | 1.12 | 32.000 | 6 | 26 | 9 | 0.3462 |

---

### V_ROOT_CAUSE_ALARM (top 3 per machine)

| MACHINE_CODE | ALARM_CODE | LONG_BREAKDOWNS | HOURS | SHARE_PCT | MEDIAN_MIN | PRECURSOR_RATE | REPEAT_24H_RATE | EARLY | LATE | NIGHT | BACK_TO_RUN | WAITING_AFTER | ANOTHER_BD | PATTERN |
|-------------|-----------|----------------|-------|-----------|-----------|---------------|----------------|-------|------|-------|------------|--------------|-----------|---------|
| s_1 | A_065 | 805 | 313.2 | 63.6 | 16.4 | 0.738 | 0.714 | 0.462 | 0.287 | 0.251 | 0.954 | 0.017 | 0.002 | REPEATS_WITHIN_A_DAY |
| s_1 | A_066 | 134 | 51.9 | 10.5 | 15.6 | 0.754 | 0.209 | 0.306 | 0.328 | 0.366 | 0.373 | 0.590 | 0.007 | SHORT_STOPS_COME_FIRST |
| s_1 | A_001 | 134 | 40.5 | 8.2 | 13.1 | 0.045 | 0.194 | 0.276 | 0.164 | 0.560 | 0.933 | 0.030 | 0.000 | CLOCK_BAND_CLUSTERED |
| s_2 | A_001 | 286 | 124.8 | 53.2 | 16 | 0.434 | 0.444 | 0.710 | 0.042 | 0.248 | 0.297 | 0.696 | 0.000 | CLOCK_BAND_CLUSTERED |
| s_2 | A_006 | 176 | 64.1 | 27.3 | 14 | 0.477 | 0.341 | 0.727 | 0.045 | 0.227 | 0.267 | 0.722 | 0.000 | CLOCK_BAND_CLUSTERED |
| s_2 | A_101 | 54 | 14.5 | 6.2 | 13.3 | 0.685 | 0.093 | 0.722 | 0.074 | 0.204 | 0.870 | 0.130 | 0.000 | SHORT_STOPS_COME_FIRST |
| s_3 | A_006 | 176 | 181.7 | 87.6 | 15 | 0.222 | 0.398 | 0.159 | 0.631 | 0.210 | 0.216 | 0.665 | 0.102 | CLOCK_BAND_CLUSTERED |
| s_3 | A_101 | 40 | 10.9 | 5.3 | 13.5 | 0.600 | 0.125 | 0.550 | 0.450 | 0.000 | 0.900 | 0.075 | 0.000 | SHORT_STOPS_COME_FIRST |
| s_3 | A_001 | 31 | 8.7 | 4.2 | 12.3 | 0.226 | 0.032 | 0.839 | 0.161 | 0.000 | 0.613 | 0.387 | 0.000 | CLOCK_BAND_CLUSTERED |
| s_4 | A_006 | 70 | 43.5 | 50.4 | 31.2 | 0.257 | 0.143 | 0.129 | 0.514 | 0.357 | 0.629 | 0.371 | 0.000 | CLOCK_BAND_CLUSTERED |
| s_4 | A_045 | 12 | 15.8 | 18.3 | 16.2 | 0.000 | 0.250 | 0.000 | 0.417 | 0.583 | 0.583 | 0.333 | 0.000 | CLOCK_BAND_CLUSTERED |
| s_4 | A_001 | 27 | 9.6 | 11.2 | 14.8 | 0.370 | 0.185 | 0.074 | 0.444 | 0.481 | 0.778 | 0.185 | 0.000 | NO_DOMINANT_PATTERN |
| s_5 | A_101 | 201 | 54.0 | 89.5 | 13.3 | 0.706 | 0.498 | 0.333 | 0.348 | 0.318 | 0.930 | 0.070 | 0.000 | SHORT_STOPS_COME_FIRST |
| s_5 | A_005 | 6 | 2.4 | 4.0 | 22.7 | 0.333 | 0.000 | 0.167 | 0.167 | 0.667 | 0.333 | 0.667 | 0.000 | CLOCK_BAND_CLUSTERED |
| s_5 | A_010 | 3 | 1.1 | 1.8 | 22.8 | 0.667 | 0.000 | 0.333 | 0.000 | 0.667 | 0.667 | 0.333 | 0.000 | TOO_FEW_EVENTS |

---

### Pattern Summary

| PATTERN | CODES | BREAKDOWNS |
|---------|-------|------------|
| CLOCK_BAND_CLUSTERED | 19 | 1040 |
| REPEATS_WITHIN_A_DAY | 2 | 810 |
| SHORT_STOPS_COME_FIRST | 13 | 511 |
| TOO_FEW_EVENTS | 61 | 110 |
| NO_DOMINANT_PATTERN | 4 | 70 |
| LINE_WAITS_AFTER_REPAIR | 1 | 15 |

---

### RISK_WORK_ORDER by OUTCOME x STOCK_STATE

| OUTCOME | STOCK_STATE | N |
|---------|-------------|---|
| BREAKDOWN_WITHIN_4H | HEALTHY | 7 |
| BREAKDOWN_WITHIN_4H | REORDER | 8 |
| BREAKDOWN_WITHIN_4H | STOCKOUT | 1 |
| NO_BREAKDOWN_WITHIN_4H | HEALTHY | 10 |
| NO_BREAKDOWN_WITHIN_4H | REORDER | 12 |
| NO_BREAKDOWN_WITHIN_4H | STOCKOUT | 7 |
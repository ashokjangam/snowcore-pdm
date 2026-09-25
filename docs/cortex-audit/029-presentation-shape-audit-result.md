Running the diagnostic queries now.Two queries lost the database context. Re-running with fully qualified names.Here are the results.

---

### 1. Declared SQL types

| Column | Type |
|---|---|
| `OEE_DATE` | **DATE** |
| `OEE` | **FLOAT** |

### 2. Row / machine / date summary

| Metric | Value |
|---|---|
| Total rows | 2 367 |
| Distinct machines | 5 |
| Distinct dates | 730 |
| Min date | 2020-01-01 |
| Max date | 2022-01-02 |

### 3. OEE value check

| Check | Result |
|---|---|
| NULL OEE rows | **101** (out of 2 367) |
| Min OEE | 0 |
| Max OEE | 0.9612 |
| OEE > 1 | **0** (none) |

### 5 most recent rows

| MACHINE_CODE | OEE_DATE | OEE |
|---|---|---|
| s_5 | 2022-01-02 | NULL |
| s_3 | 2022-01-02 | 0.8238 |
| s_4 | 2022-01-02 | 0.8919 |
| s_3 | 2022-01-01 | 0.4772 |
| s_5 | 2022-01-01 | 0.7897 |

**Key observations:** `OEE_DATE` is a proper `DATE` and `OEE` is `FLOAT`. There are 101 NULL OEE values. No OEE exceeds 1. The date values in the raw output appear double-quoted (e.g. `"""2022-01-02"""`), which may indicate the dates were stored or cast through a string layer — worth checking if a charting layer is failing to parse them.
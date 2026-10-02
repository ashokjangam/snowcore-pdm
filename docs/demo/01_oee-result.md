I'll run both queries in parallel to get the PLANT_B site rollup and the top executive action queue items.Let me check the rollup view's columns.---

## PLANT_B Operator Briefing

### 1. OEE Arithmetic (site rollup, 2 367 days observed)

| Metric | Value |
|---|---|
| **Availability (A)** | 64.32 % |
| **Performance (P)** | 72.93 % |
| **Quality (Q)** | 99.72 % |
| **A x P x Q** | 0.6432 x 0.7293 x 0.9972 = **0.4678** |
| **Weighted OEE (reported)** | **46.78 %** |

The product matches the reported OEE to four decimal places: **confirmed**.

### 2. Top Loss Owner and Evidence

**#1 action: PLANNING — machine s_5, priority P1**

- **Risk state:** IDLE_DOMINANT
- **Evidence:** 2 627.1 idle hours; 355.6 breakdown hours
- **Production exposure:** €4 965 367
- **Recommended action:** Validate schedule, upstream supply and changeover constraints before assigning maintenance.

The top five actions are all P1. Four of five are owned by PLANNING (idle-dominant on s_5, s_4, s_3, s_2); the remaining one is owned by MAINTENANCE (s_2, blind-test risk score 0.668, 573.8 breakdown hours).

### 3. Provenance

- All OEE figures are derived from **PIADE observed operations** (source: `GOLD.PIADE_OEE_DAILY`).
- Euro exposure values are **scenario assumptions** (`DERIVED_FROM_OBSERVED + SYNTHETIC_ERP`), not actuals.
- No predictions, annualisations, or causal inferences have been applied.
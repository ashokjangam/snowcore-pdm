I'll run the setup commands first, then execute the four analytical queries in parallel.Need to check the column names and prefix each query with the database context. Let me fix both issues.The timestamp column is `TIME_UTC`. Now running all four queries.All four queries returned. Here are the results and the judgement.

---

## 1. Per-code frequency

| Code | Windows | Total Activations | Machines | % of Activations |
|------|---------|-------------------|----------|------------------|
| AL_45 | 588 | 979 | 5 | 29.89% |
| AL_46 | 528 | 872 | 6 | 26.63% |
| AL_51 | 86 | 254 | 4 | 7.76% |
| AL_50 | 81 | 254 | 5 | 7.76% |
| AL_48 | 66 | 209 | 5 | 6.38% |
| AL_42 | 39 | 118 | 3 | 3.60% |
| AL_40 | 29 | 116 | 1 | 3.54% |
| AL_41 | 32 | 96 | 2 | 2.93% |
| AL_49 | 29 | 85 | 3 | 2.60% |
| AL_52 | 23 | 77 | 1 | 2.35% |
| AL_17 | 31 | 51 | 1 | 1.56% |
| AL_43 | 20 | 49 | 3 | 1.50% |
| AL_18 | 24 | 42 | 1 | 1.28% |
| AL_53 | 23 | 35 | 3 | 1.07% |
| AL_54 | 18 | 34 | 4 | 1.04% |
| AL_47 | 1 | 4 | 1 | 0.12% |

All 16 codes fire. No code is dead.

## 2. Concentration

- **Top-1 code (AL_45):** 29.89% of activations
- **Top-3 codes (AL_45 + AL_46 + AL_51/AL_50):** 64.28%
- **Codes needed to reach 90%:** 9 of 16

This is a moderately concentrated but genuinely multi-modal distribution. If one code held 80%+ you'd call it degenerate — 30% for the leader with a close second at 27% is a real two-horse race plus a meaningful long tail.

## 3. Window ambiguity

| Bucket | Windows | % |
|--------|---------|---|
| Exactly 1 code | 1,493 | **96.01%** |
| Exactly 2 codes | 61 | 3.92% |
| 3 or more codes | 1 | 0.06% |

**96% of alarm windows have exactly one code active.** Attribution is unambiguous in the vast majority of cases. The 4% with two codes is small enough to handle with a simple "pick the highest-count code" rule or to label as multi-cause without materially degrading the breakdown.

## 4. Dominant code by machine

| Machine | Dominant Code | Activations | % of Machine |
|---------|--------------|-------------|--------------|
| A005 | AL_45 | 469 | 36.24% |
| B002 | AL_46 | 306 | 37.41% |
| A001 | AL_45 | 148 | 31.76% |
| B005 | AL_50 | 147 | 33.33% |
| E002 | AL_45 | 106 | 49.77% |
| E004 | AL_43 | 20 | 66.67% |
| C003 | AL_50 | 5 | 55.56% |
| C004 | AL_47 | 4 | 100.00% |

Different machines have different dominant codes. AL_45 leads on A-series and E002, AL_46 leads on B002, AL_50 leads on B005 and C003, AL_43 on E004, AL_47 on C004. The dominant code's share within a machine ranges from ~32% to 100%, meaning no single code explains everything even within a single machine. This is genuine per-machine variation, not a global constant.

---

## Judgement

**1. Is the distribution informative?**
Yes. The top code holds only 30% of volume, with a close runner-up at 27%. Nine codes are needed to cover 90%. A Pareto chart would show a real curve, not one bar. This is an informative distribution.

**2. What fraction of windows would have ambiguous attribution?**
4%. Ninety-six percent of windows have exactly one module alarm code active. Single-code attribution is honest in the overwhelming majority of cases.

**3. Is replacing the constant `MODULE_ALARM` with per-code attribution worth doing?**
Yes, it is worth doing. The data supports it on both axes that matter: the distribution is genuinely multi-modal (not dominated by one code), and the attribution is unambiguous in 96% of windows. Different machines also show different failure signatures, which means per-code detail would actually help diagnose machine-specific problems. Keeping the flat `MODULE_ALARM` constant is discarding real signal.
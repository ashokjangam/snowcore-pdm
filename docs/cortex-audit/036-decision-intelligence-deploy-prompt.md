# Cortex prompt 036 — decision intelligence deployment

Use connection `hackathon`. Read the current local
`sql/19_decision_intelligence.sql`. Execute its setup and five view definitions
in statement order, ending with
`DROP VIEW IF EXISTS GOLD.V_REVENUE_SCENARIO_BASE`. Do not execute the many
report queries that follow that drop; run only the focused verification below.
Do not edit repository files or change the SQL contract. Stop on any DDL error
rather than skipping a failed view.

After execution, report:

```sql
SELECT 'V_ASSUMPTIONS_ACTIVE' VIEW_NAME, COUNT(*) ROWS
FROM SNOWCORE_REAL.GOLD.V_ASSUMPTIONS_ACTIVE
UNION ALL SELECT 'V_MARGIN_SCENARIO_BASE', COUNT(*)
FROM SNOWCORE_REAL.GOLD.V_MARGIN_SCENARIO_BASE
UNION ALL SELECT 'V_OEE_LOSS_ATTRIBUTION', COUNT(*)
FROM SNOWCORE_REAL.GOLD.V_OEE_LOSS_ATTRIBUTION
UNION ALL SELECT 'V_IMPROVEMENT_LEVERS', COUNT(*)
FROM SNOWCORE_REAL.GOLD.V_IMPROVEMENT_LEVERS
UNION ALL SELECT 'V_ANALYST_DECISION_CONTEXT', COUNT(*)
FROM SNOWCORE_REAL.GOLD.V_ANALYST_DECISION_CONTEXT;
```

Verify all of these:

- no duplicate `CONTEXT_KEY`;
- no context row without value, source, origin, claim class or as-of timestamp;
- no unknown claim/origin vocabulary;
- no CoMoPI or non-PIADE line in the views;
- `ERP_TARGET_UPLIFT` is absent;
- site package/margin values reconcile to line sums;
- each subject's three loss buckets plus actual output reconcile to planned
  capacity within one package;
- lever rows do not fan out and retain one unique rank and ID each;
- all euro values are labelled synthetic and no observed hours/packages are
  labelled synthetic.

Return exact result sets for failed checks and a concise PASS/FAIL summary.

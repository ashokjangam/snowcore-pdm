# Cortex prompt 036d — decision intelligence verification

Use connection `hackathon`. Read `sql/19_decision_intelligence.sql`.

Run only the verification `SELECT` statements after the obsolete-view drop,
in four Snowflake calls:

1. row budgets, context bound/uniqueness, PIADE-only boundary;
2. margin consistency and exact capacity reconciliation;
3. site/line, lever and clamped-vs-signed reconciliation;
4. lineage, origin, monetary claim and assumption-consumer checks.

Prefix each call with `USE DATABASE SNOWCORE_REAL` in the same request because
session context is not retained. Do not run report queries, edit files, or
repair data. Return every check whose `RESULT` is not `PASS`, plus a compact
table of all PASS/FAIL outcomes.

# Cortex prompt 036c — bounded decision context

Use connection `hackathon`. Read `sql/19_decision_intelligence.sql`.
Snowflake tool calls do not retain session context. Submit the view SQL in one
multi-statement call prefixed with `USE DATABASE SNOWCORE_REAL;`, or fully
qualify every referenced object.

Execute only:

1. its `USE` / session setup statements;
2. `CREATE OR REPLACE VIEW GOLD.V_ANALYST_DECISION_CONTEXT`;
3. its `COMMENT ON VIEW`;
4. `DROP VIEW IF EXISTS GOLD.V_REVENUE_SCENARIO_BASE`.

Do not execute other views, gates or reports. Do not edit files. Stop and
return the exact Snowflake error if a statement fails. Otherwise return the
context row count, distinct context-key count, topic counts and claim-class
counts.

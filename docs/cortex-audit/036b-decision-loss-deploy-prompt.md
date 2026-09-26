# Cortex prompt 036b — decision loss and lever views

Use connection `hackathon`. Read `sql/19_decision_intelligence.sql`.
Snowflake tool calls do not retain session context. Submit each view's SQL in
one multi-statement call prefixed with `USE DATABASE SNOWCORE_REAL;`, or fully
qualify every referenced object. Do not spend turns retrying bare `GOLD.*`
names without a database context.

Execute only:

1. its `USE` / session setup statements;
2. `CREATE OR REPLACE VIEW GOLD.V_OEE_LOSS_ATTRIBUTION`;
3. `CREATE OR REPLACE VIEW GOLD.V_IMPROVEMENT_LEVERS`;
4. the two corresponding `COMMENT ON VIEW` statements.

Do not execute other views, gates or reports. Do not edit files. Stop and
return the exact Snowflake error if a statement fails. Otherwise return row
counts for both views.

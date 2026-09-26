# Cortex prompt 036a — decision foundation views

Use connection `hackathon`. Read `sql/19_decision_intelligence.sql`.

Execute only:

1. its `USE` / session setup statements;
2. `CREATE OR REPLACE VIEW GOLD.V_ASSUMPTIONS_ACTIVE`;
3. `CREATE OR REPLACE VIEW GOLD.V_MARGIN_SCENARIO_BASE`;
4. the two corresponding `COMMENT ON VIEW` statements.

Do not execute later views, gates or reports. Do not edit files. Stop and
return the exact Snowflake error if a statement fails. Otherwise return row
counts for both views.

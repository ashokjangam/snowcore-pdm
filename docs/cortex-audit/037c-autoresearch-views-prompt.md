# Cortex prompt 037c — research views

Use connection `hackathon`. Read `sql/20_piade_autoresearch.sql`.

Execute only the `CREATE OR REPLACE VIEW` statements for
`ML.V_PIADE_RESEARCH_TRIALS` and `ML.V_PIADE_RESEARCH_CHAMPION`, fully
qualified under `SNOWCORE_REAL`, each as its own Snowflake call if
multi-statement calls fail.

Do not CALL the procedure. Return `DESC VIEW` column lists or the exact error.

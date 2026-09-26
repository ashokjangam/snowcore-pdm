# Cortex prompt 037a — autoresearch tables and additive migration

Use connection `hackathon`. Read `sql/20_piade_autoresearch.sql`.

Execute only, in order, against `SNOWCORE_REAL`, fully qualifying objects or
prefixing `USE DATABASE SNOWCORE_REAL;` in the same call:

1. session `USE` statements;
2. every `CREATE TABLE IF NOT EXISTS` through `ML.PIADE_CHAMPION_CONTRACT`;
3. every `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`;
4. the `EXECUTE IMMEDIATE` block that drops `TRIAL_NUMBER NOT NULL` when needed.

Do not create the procedure or views. Do not call the procedure. Do not edit
files. If `EXECUTE IMMEDIATE` dollar-quoting fails, run the equivalent
`ALTER TABLE ML.PIADE_RESEARCH_RUN ALTER COLUMN TRIAL_NUMBER DROP NOT NULL`
once and continue.

Return: table names created/altered and any exact Snowflake error.

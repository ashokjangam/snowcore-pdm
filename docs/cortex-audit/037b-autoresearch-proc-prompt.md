# Cortex prompt 037b — create RUN_PIADE_AUTORESEARCH

Use connection `hackathon`. Read `sql/20_piade_autoresearch.sql`.

Execute exactly one Snowflake statement: the full
`CREATE OR REPLACE PROCEDURE ML.RUN_PIADE_AUTORESEARCH...` through its
closing `$$;` handler block. Prefix is not needed if the procedure is
created as `SNOWCORE_REAL.ML.RUN_PIADE_AUTORESEARCH`. If the account
rejects `snowflake-ml-python==2.1.0`, retry the same CREATE with
unpinned `'snowflake-ml-python'` and report that change. If it rejects
`DEFAULT 25`, omit the default and keep `MAX_TRIALS INTEGER`.

Do not CALL the procedure. Do not edit files. Return the exact error or
`SHOW PROCEDURES LIKE 'RUN_PIADE_AUTORESEARCH' IN SCHEMA SNOWCORE_REAL.ML`.

I'll run these SQL statements in order.PUT succeeded (81638 bytes uploaded). Now refreshing the stage and running EXECUTE IMMEDIATE FROM.EXECUTE IMMEDIATE FROM completed successfully. Now checking the procedure.All steps completed successfully:

1. **PUT** - Uploaded `20_piade_autoresearch_runtime.sql` (81,638 bytes) to `@SNOWCORE_REAL.APPS.STREAMLIT_STAGE/sql/`.
2. **Stage refresh** - File registered (updated) successfully.
3. **EXECUTE IMMEDIATE FROM** - Ran without error; last object created was view `V_PIADE_RESEARCH_CHAMPION`.
4. **SHOW PROCEDURES** - `RUN_PIADE_AUTORESEARCH(DEFAULT NUMBER) RETURN VARIANT` exists in `SNOWCORE_REAL.ML`, created at `2026-09-25 12:48:10`.
# Cortex prompt 037f1 — cancel zombies and replace procedure only

Use connection `hackathon`. Do not CALL RUN_PIADE_AUTORESEARCH.

1. Cancel any running warehouse query whose text starts with `CALL` and
   contains `RUN_PIADE_AUTORESEARCH`.
2. Run the two UPDATEs in `docs/cortex-audit/037f-cancel-cap-rerun-prompt.md`
   that mark RUNNING campaigns/runs as canceled overruns.
3. PUT and `EXECUTE IMMEDIATE FROM` 
   `sql/20_piade_autoresearch_runtime.sql` on
   `@SNOWCORE_REAL.APPS.STREAMLIT_STAGE/sql/`.
4. SHOW PROCEDURES LIKE 'RUN_PIADE_AUTORESEARCH' IN SCHEMA SNOWCORE_REAL.ML.

Do not edit files. Return cancel query ids, update row counts, and procedure
created timestamp.

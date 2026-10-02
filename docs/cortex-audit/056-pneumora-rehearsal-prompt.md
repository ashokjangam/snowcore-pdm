# PNEUMORA: app sync and second demo rehearsal

Scope only the `PNEUMORA` database with role `PNEUMORA_ROLE` and warehouse
`PNEUMORA_WH`. Do not touch `SNOWCORE_REAL`, `TRIDENT_OPS` or any other database.
Do not edit local files. Never print credentials.

If any statement fails, report it and the error verbatim and stop.

## 1. Sync the app source

```sql
USE ROLE PNEUMORA_ROLE;
USE WAREHOUSE PNEUMORA_WH;
PUT 'file://C:/Users/C306242/Phoenix/sainathch45/snowcore-pdm/pneumora/sis/app.py' @PNEUMORA.APP.STREAMLIT_STAGE AUTO_COMPRESS = FALSE OVERWRITE = TRUE;
ALTER STAGE PNEUMORA.APP.STREAMLIT_STAGE REFRESH;
```

Report `LIST @PNEUMORA.APP.STREAMLIT_STAGE PATTERN = '.*app[.]py';` (name, size).

## 2. Rehearse the demo prompts

Follow `docs/demo/01_detect.txt` exactly, then `docs/demo/02_rca.txt` exactly. Both are
read only. Call `AI_COMPLETE` once only; do not retry or rewrite the prompt to improve
the answer. Report the final answers and the structured Cortex output verbatim.
Do not run `docs/demo/03_action.txt`.

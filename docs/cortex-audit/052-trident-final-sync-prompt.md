# Final TRIDENT OPS app sync

Scope only `TRIDENT_OPS.APP.TRIDENT_OPS`. Do not change source data or any
object in `SNOWCORE_REAL` or `PNEUMORA`.

Upload these local files to `@TRIDENT_OPS.APP.STREAMLIT_STAGE` with
`AUTO_COMPRESS=FALSE` and `OVERWRITE=TRUE`, preserving paths:

- `trident_ops/app.py` -> `app.py`
- `trident_ops/environment.yml` -> `environment.yml`
- `trident_ops/.streamlit/config.toml` -> `.streamlit/config.toml`
- `trident_ops/modules/__init__.py` -> `modules/__init__.py`
- `trident_ops/modules/contracts.py` -> `modules/contracts.py`

Then execute exactly:

```sql
USE ROLE TRIDENT_OPS_ROLE;
USE WAREHOUSE TRIDENT_OPS_WH;
ALTER STAGE TRIDENT_OPS.APP.STREAMLIT_STAGE REFRESH;
CREATE OR REPLACE STREAMLIT TRIDENT_OPS.APP.TRIDENT_OPS
  FROM '@TRIDENT_OPS.APP.STREAMLIT_STAGE'
  MAIN_FILE = 'app.py'
  QUERY_WAREHOUSE = 'TRIDENT_OPS_WH'
  RUNTIME_NAME = 'SYSTEM$WAREHOUSE_RUNTIME'
  TITLE = 'TRIDENT OPS · Evidence-first OEE and maintenance'
  COMMENT = 'PIADE operations and MetroPT sensor evidence remain isolated; operator triage is persisted';
LIST @TRIDENT_OPS.APP.STREAMLIT_STAGE;
DESCRIBE STREAMLIT TRIDENT_OPS.APP.TRIDENT_OPS;
SHOW STREAMLITS LIKE 'TRIDENT_OPS' IN SCHEMA TRIDENT_OPS.APP;
```

Report errors verbatim. Confirm all five stage files and their byte sizes.
From `DESCRIBE`, report `runtime_name`, `user_packages`, `main_file`, and
`query_warehouse`. Runtime must be `SYSTEM$WAREHOUSE_RUNTIME`; packages must
match environment.yml and contain no `python` entry. Report the `url_id`.

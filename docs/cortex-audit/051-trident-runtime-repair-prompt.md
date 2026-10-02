# Repair TRIDENT OPS runtime after shell expansion

Scope only `TRIDENT_OPS.APP.TRIDENT_OPS`. Do not edit local files and do not
touch `SNOWCORE_REAL` or `PNEUMORA`.

Execute exactly:

```sql
USE ROLE TRIDENT_OPS_ROLE;
USE WAREHOUSE TRIDENT_OPS_WH;
CREATE OR REPLACE STREAMLIT TRIDENT_OPS.APP.TRIDENT_OPS
  FROM '@TRIDENT_OPS.APP.STREAMLIT_STAGE'
  MAIN_FILE = 'app.py'
  QUERY_WAREHOUSE = 'TRIDENT_OPS_WH'
  RUNTIME_NAME = 'SYSTEM$WAREHOUSE_RUNTIME'
  TITLE = 'TRIDENT OPS · Evidence-first OEE and maintenance'
  COMMENT = 'PIADE operations and MetroPT sensor evidence remain isolated; operator triage is persisted';
DESCRIBE STREAMLIT TRIDENT_OPS.APP.TRIDENT_OPS;
SHOW STREAMLITS LIKE 'TRIDENT_OPS' IN SCHEMA TRIDENT_OPS.APP;
```

Report errors verbatim. From DESCRIBE report `runtime_name`, `user_packages`,
`main_file`, and `query_warehouse`. Runtime must be
`SYSTEM$WAREHOUSE_RUNTIME`; packages must be the four pinned entries from
environment.yml with no `python` entry. Report `url_id`.

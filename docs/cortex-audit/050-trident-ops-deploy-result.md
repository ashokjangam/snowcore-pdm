# TRIDENT OPS deployment result

Verified on Snowflake connection `hackathon` on 2026-10-01.

## Deployment

- Role: `TRIDENT_OPS_ROLE`
- Warehouse: `TRIDENT_OPS_WH` (X-Small, 60-second auto-suspend)
- Database: `TRIDENT_OPS`
- Schemas: `OPS`, `APP`
- Stage: `TRIDENT_OPS.APP.STREAMLIT_STAGE`
- Streamlit: `TRIDENT_OPS.APP.TRIDENT_OPS`
- URL id: `bd2ocwt4eblddojvzl7v`
- Runtime: `SYSTEM$WAREHOUSE_RUNTIME`
- User packages: `streamlit==1.52.2`, `plotly==6.5.0`,
  `pandas==2.3.3`, `snowflake-snowpark-python`
- `pyproject.toml`: absent

Viewer URL:

`https://app.snowflake.com/streamlit/FMXJOWH/BRC04642/#/apps/bd2ocwt4eblddojvzl7v`

## Stage files

| File | Bytes |
|---|---:|
| `.streamlit/config.toml` | 192 |
| `app.py` | 21,408 |
| `environment.yml` | 144 |
| `modules/__init__.py` | 80 |
| `modules/contracts.py` | 3,776 |

## Source-grant smoke test

Executed as `TRIDENT_OPS_ROLE`:

| Object | Rows |
|---|---:|
| `SNOWCORE_REAL.GOLD.V_EXECUTIVE_KPI` | 1 |
| `SNOWCORE_REAL.GOLD.V_ROOT_CAUSE_ALARM` | 100 |
| `PNEUMORA.CORE.FAILURES` | 4 |
| `PNEUMORA.ML.ALERTS` | 132 |

## Idempotency smoke test

The same `RECORD_TRIAGE_ACTION` call was run twice.

- First call: action id `TRI-7e602f0d633bece5df74`,
  `deduplicated=false`.
- Second call: same action id, `deduplicated=true`.
- Exactly one row existed for the smoke source key.
- The smoke row was deleted; zero remained.

The demo action `DEMO_VIDEO|s_2` was then created separately and deliberately
left in the flight recorder for the recorded workflow.

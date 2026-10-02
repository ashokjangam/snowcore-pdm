I'll upload the five files to the stage and then recreate the Streamlit app. Let me start by reading the local files and uploading them.All five files found. Now uploading them to the stage.All five files uploaded. Now executing the stage refresh and Streamlit recreation.All done. Here is the summary:

---

**Stage files (5/5 confirmed):**

| File | Size (bytes) |
|---|---|
| `app.py` | 22,512 |
| `environment.yml` | 144 |
| `.streamlit/config.toml` | 192 |
| `modules/__init__.py` | 80 |
| `modules/contracts.py` | 4,016 |

**DESCRIBE STREAMLIT results:**

| Property | Value |
|---|---|
| `runtime_name` | `SYSTEM$WAREHOUSE_RUNTIME` |
| `user_packages` | `streamlit==1.52.2,plotly==6.5.0,pandas==2.3.3,snowflake-snowpark-python` |
| `main_file` | `app.py` |
| `query_warehouse` | `TRIDENT_OPS_WH` |
| `url_id` | `bd2ocwt4eblddojvzl7v` |

Runtime is `SYSTEM$WAREHOUSE_RUNTIME` as required. Packages match `environment.yml` and contain no bare `python` entry (the `python==3.11.*` in `default_packages` is Snowflake's system default, not a user package). No errors encountered.
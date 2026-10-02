I'll execute the SQL statements in order to recreate the PNEUMORA Streamlit app on the warehouse runtime.All statements succeeded. Now verifying.## Report

1. **Failed statements**: None. All 6 statements executed successfully.

2. **Runtime**: `SYSTEM$WAREHOUSE_RUNTIME` — confirmed via DESCRIBE output. The app is on the warehouse runtime, not the container runtime.

3. **`environment.yml` location**: Yes, it is at the stage root (`streamlit_stage/environment.yml`), alongside `app.py` (`streamlit_stage/app.py`).

4. **Viewer URL**:
   `https://app.snowflake.com/streamlit/FMXJOWH/BRC04642/#/apps/df4d72ofa3zbhz6wswdh`
# Cortex prompt 034 — exact Streamlit viewer URL

Read-only. Run:

```sql
USE ROLE ACCOUNTADMIN;
SELECT CURRENT_ORGANIZATION_NAME() AS ORGANIZATION_NAME,
       CURRENT_ACCOUNT_NAME() AS ACCOUNT_NAME,
       CURRENT_ACCOUNT() AS ACCOUNT_LOCATOR;

DESCRIBE STREAMLIT SNOWCORE_REAL.APPS.SNOWCORE_PDM;
```

Using Snowflake's documented pattern:

```text
https://app.snowflake.com/streamlit/<organization_name>/<account_name>/#/apps/<url_id>
```

report the exact app-viewer URL. Do not alter anything.

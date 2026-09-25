# Cortex prompt 032 — Streamlit sharing audit

Read-only diagnosis. Do not grant, revoke, create, alter, or drop anything.
The user can open and edit `SNOWCORE_REAL.APPS.SNOWCORE_PDM`, but clicking the
Snowsight **Share** button shows the toolbar message "Something went wrong."

Use `ACCOUNTADMIN` and report the exact ownership/access state:

```sql
USE ROLE ACCOUNTADMIN;
USE DATABASE SNOWCORE_REAL;
USE WAREHOUSE COMPUTE_WH;

SHOW STREAMLITS LIKE 'SNOWCORE_PDM' IN SCHEMA SNOWCORE_REAL.APPS;
SHOW GRANTS ON STREAMLIT SNOWCORE_REAL.APPS.SNOWCORE_PDM;
SHOW GRANTS ON SCHEMA SNOWCORE_REAL.APPS;
SHOW GRANTS ON DATABASE SNOWCORE_REAL;
SHOW PARAMETERS IN STREAMLIT SNOWCORE_REAL.APPS.SNOWCORE_PDM;
```

Also report:

1. App owner role.
2. Schema owner role and whether the schema is managed access.
3. Whether the app has a query warehouse and what it is.
4. Which roles currently have `USAGE` on the app.
5. Whether `ACCOUNTADMIN` or the app-owner role has enough privilege to share.
6. The app-viewer URL if Snowflake exposes it in `SHOW STREAMLITS`.
7. Any property/state in `SHOW STREAMLITS` that indicates the object is
   suspended, unavailable, or malformed.

If a query syntax differs on this account, use the equivalent read-only
`SHOW`/`DESCRIBE` command. Do not fix anything. Separate:

- verified object/privilege facts;
- likely Snowsight UI/transient causes that cannot be proved from SQL;
- the exact minimal SQL needed **after a recipient role is known**.

Do not invent or choose a recipient role.

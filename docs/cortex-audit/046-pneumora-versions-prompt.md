Read-only query. Do not create, alter, drop or upload anything.

Run exactly this SQL and report the full result table verbatim (every row):

```sql
SELECT PACKAGE_NAME, VERSION
FROM SNOWFLAKE.INFORMATION_SCHEMA.PACKAGES
WHERE LANGUAGE = 'python'
  AND PACKAGE_NAME IN ('pandas', 'plotly', 'numpy')
  AND (VERSION LIKE '2.%' OR VERSION LIKE '3.%' OR VERSION LIKE '5.%' OR VERSION LIKE '6.%' OR VERSION LIKE '1.26%')
GROUP BY PACKAGE_NAME, VERSION
ORDER BY PACKAGE_NAME, VERSION;
```

Then report the result of:

```sql
SELECT DISTINCT RUNTIME_VERSION FROM SNOWFLAKE.INFORMATION_SCHEMA.PACKAGES
WHERE LANGUAGE = 'python' AND PACKAGE_NAME = 'streamlit' AND VERSION = '1.52.2';
```

Report errors verbatim if any.

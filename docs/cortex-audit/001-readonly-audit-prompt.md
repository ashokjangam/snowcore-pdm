# Cortex prompt 001 — read-only account audit

Run with `CORTEX_CLIENT_READ_ONLY=true`, so the session rejects DDL and DML.

```text
READ-ONLY audit of this Snowflake account. Use the Snowflake SQL tool only.

Run these and report the actual returned values:
1. SELECT CURRENT_ACCOUNT(), CURRENT_USER(), CURRENT_ROLE(), CURRENT_REGION(), CURRENT_WAREHOUSE();
2. SHOW DATABASES;
3. SHOW WAREHOUSES;
4. SELECT SNOWFLAKE.CORTEX.COMPLETE('claude-3-5-sonnet', 'reply with OK');

Then state plainly:
- which databases already exist and whether any belong to a prior SnowCore build,
- which warehouse is usable and its size and auto-suspend,
- whether Cortex LLM functions work for this role.

Do not create, alter, or drop anything. Do not propose SQL yet.
```

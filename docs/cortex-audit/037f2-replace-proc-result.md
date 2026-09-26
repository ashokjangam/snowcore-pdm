Running the 5 SQL statements sequentially.File uploaded. Now refreshing the stage.Stage refreshed. Now executing the SQL file.Executed successfully. Now running the remaining two queries.All 5 statements completed. Summary:

1. **PUT** - Uploaded `20_piade_autoresearch_runtime.sql` (81,955 bytes) successfully.
2. **ALTER STAGE REFRESH** - File registered (updated) successfully.
3. **EXECUTE IMMEDIATE** - Succeeded. Last object created: `V_PIADE_RESEARCH_CHAMPION` view.
4. **SHOW PROCEDURES** - `RUN_PIADE_AUTORESEARCH(NUMBER) RETURN VARIANT` exists in `SNOWCORE_REAL.ML`, created `2026-09-26 11:13:24`.
5. **Campaign status** - 3 campaigns, all `FAILED`:

| CAMPAIGN_ID | STATUS | STOP_REASON |
|---|---|---|
| `fab15153-...` | FAILED | CANCELED_NATIVE_FIT_OVERRUN |
| `bcb558bd-...` | FAILED | ERROR |
| `8931bc94-...` | FAILED | CANCELED_NATIVE_FIT_OVERRUN |
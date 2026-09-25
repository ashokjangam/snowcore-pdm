I'll run the diagnostic queries to audit the Streamlit sharing state.Here is the full audit.

---

## Verified Object / Privilege Facts

### 1. App owner role
**`ACCOUNTADMIN`** owns the Streamlit object `SNOWCORE_REAL.APPS.SNOWCORE_PDM`.

### 2. Schema owner & managed-access status
- **Schema owner**: `ACCOUNTADMIN`
- **Managed access**: **No** — the `options` column in `SHOW SCHEMAS` is empty (no `MANAGED ACCESS`).

### 3. Query warehouse
**`COMPUTE_WH`** is assigned as the query warehouse.

### 4. Roles with USAGE on the app
| Role | Privilege | Grant option |
|---|---|---|
| `ACCOUNTADMIN` | OWNERSHIP | yes |
| `SYSADMIN` | USAGE | yes |

Only `SYSADMIN` has an explicit `USAGE` grant. No other roles have access.

The full access chain for `SYSADMIN`:
- `USAGE` on `DATABASE SNOWCORE_REAL` — granted
- `USAGE` on `SCHEMA SNOWCORE_REAL.APPS` — granted
- `USAGE` on `STREAMLIT SNOWCORE_REAL.APPS.SNOWCORE_PDM` — granted

### 5. Can ACCOUNTADMIN / owner share?
Yes — `ACCOUNTADMIN` owns the object, the schema, and the database. It has full authority to grant `USAGE` on the Streamlit to any role.

### 6. App-viewer URL
The `url_id` from `SHOW STREAMLITS` is **`qeu3mlcqzavjz7odztyk`**. The Snowsight URL follows the pattern:
```
https://<account>.snowflakecomputing.app/streamlit-apps/qeu3mlcqzavjz7odztyk
```

### 7. Object health / state
No evidence of suspension, unavailability, or malformation:
- The object was created `2026-09-24 12:36:36` and is present in metadata.
- `root_location` points to `@SNOWCORE_REAL.APPS.STREAMLIT_STAGE/snowcore_pdm` with `main_file = app.py`.
- A query warehouse is assigned.
- `idle_auto_shutdown_time_seconds` is `NULL` (default behaviour).
- `title` is `None` — the app has no display title set, but this is cosmetic and should not cause a Share dialog failure.

---

## Likely Snowsight UI / Transient Causes (cannot be proved from SQL)

1. **Snowsight Share dialog bug with ACCOUNTADMIN-owned Streamlits.** The Share button in Snowsight sometimes fails when the Streamlit is owned by `ACCOUNTADMIN` because the UI may attempt an internal metadata call that behaves differently for this built-in role. This is a known transient UI issue, not a privilege gap.

2. **Missing `title` property.** The `title` column is `None`. Some Snowsight UI flows rely on the title being set; its absence could trip a front-end null-reference in the Share modal. This cannot be confirmed from SQL alone.

3. **Browser cache / Snowsight version.** Stale Snowsight JS bundles can cause toolbar actions to fail silently. A hard refresh or incognito window rules this out.

---

## Minimal SQL to Share (once a recipient role is chosen)

Replace `<RECIPIENT_ROLE>` with the actual role name:

```sql
-- 1. Grant access to the database
GRANT USAGE ON DATABASE SNOWCORE_REAL TO ROLE <RECIPIENT_ROLE>;

-- 2. Grant access to the schema
GRANT USAGE ON SCHEMA SNOWCORE_REAL.APPS TO ROLE <RECIPIENT_ROLE>;

-- 3. Grant usage on the Streamlit app
GRANT USAGE ON STREAMLIT SNOWCORE_REAL.APPS.SNOWCORE_PDM TO ROLE <RECIPIENT_ROLE>;
```

If the app queries tables in other schemas (likely, given it's a PdM command centre), the recipient role will also need `USAGE` on those schemas and `SELECT` on the underlying tables — but those grants are data-access concerns, not sharing-mechanism concerns.
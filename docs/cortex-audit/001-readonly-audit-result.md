I'll run these four queries to audit the account.The model name may differ. Let me retry with a valid model.Here is the audit summary:

---

**Session Context**

| Field | Value |
|---|---|
| Account | `OEC18361` |
| User | `SAINATHCH45` |
| Role | `ACCOUNTADMIN` |
| Region | `AWS_US_EAST_1` |
| Warehouse | `COMPUTE_WH` |

**Databases (5)**

| Database | Kind | Notes |
|---|---|---|
| `SNOWFLAKE` | Application | System metadata (ACCOUNT_USAGE, etc.) |
| `SNOWFLAKE_LEARNING_DB` | Standard | Provisioned by Snowflake at account creation |
| `SNOWFLAKE_PUBLIC_DATA_FREE` | Imported | Cybersyn marketplace free data |
| `SNOWFLAKE_SAMPLE_DATA` | Imported | Standard TPC-H sample data |
| `USER$SAINATHCH45` | Personal | User personal database |

**None of these belong to a prior SnowCore build.** The account is clean — no project-specific databases exist yet.

**Warehouses (3)**

| Warehouse | Size | Auto-Suspend | State | Notes |
|---|---|---|---|---|
| `COMPUTE_WH` | X-Small | 300s (5 min) | Suspended | Default, Gen 2, usable |
| `SNOWFLAKE_LEARNING_WH` | X-Small | 300s | Suspended | Provisioning default |
| `SYSTEM$STREAMLIT_NOTEBOOK_WH` | X-Small | 60s | Suspended | System WH for notebooks |

`COMPUTE_WH` is the current/default warehouse and is usable for queries.

**Cortex LLM Functions**

- `claude-3-5-sonnet` — **not available** (unknown model error)
- `llama3.1-8b` — **works** (returned "OK")

Cortex LLM functions are operational for this role, but the available model catalog may not include all Anthropic models. Llama and likely other Snowflake-hosted models are accessible.
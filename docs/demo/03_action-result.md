I'll call the stored procedure and then query the resulting row.Now let me verify idempotency by calling it a second time.Here are the results:

**Triage action recorded:**

| Field | Value |
|---|---|
| **Action ID** | `TRI-c03d7a37f56937e773f2` |
| **Deduplicated (1st call)** | `false` — new row inserted |
| **Deduplicated (2nd call)** | `true` — no duplicate created |
| **Actor** | `SAINATHCH45` |
| **Created At** | 2026-10-01 11:55:01.885 -0700 |
| **Status** | `OPEN` |
| **Source Key** | `DEMO_VIDEO|s_2` |

A second run cannot create a duplicate because the procedure computes a deterministic **idempotency key** (the SHA-256 hash `c03d7a3...38547`) from the combination of plant code, machine code, source key, and action type. On insert it performs a MERGE (or equivalent upsert) keyed on that hash — if a matching row already exists, it only updates `LAST_SEEN_AT` and returns `deduplicated: true` instead of inserting a new row.
I'll set up the session, upload the app, and modify the procedure's execution mode. Let me start by reading the procedure DDL file and running the session setup.Session is set up. Let me read the full procedure DDL and upload the app in parallel.App uploaded (38,447 bytes). Now let me refresh the stage, list files, and attempt the ALTER PROCEDURE.Session lost the database context. Let me re-set it and retry the ALTER.ALTER succeeded. Now let me verify the execution mode and check grants.Let me also check the `execute_as` field which SHOW PROCEDURES should include, and verify no USAGE grants exist for PUBLIC or other roles.All done. Here is the report:

---

**1. Staged app bytes**

| File | Size (bytes) |
|------|-------------|
| `snowcore_pdm/app.py` | 38,448 |
| `snowcore_pdm/environment.yml` | 144 |

**2. Procedure `execute as` mode**

`CALLER` — confirmed via `DESCRIBE PROCEDURE`. The `ALTER PROCEDURE ML.TRAIN_PLANT_B_RISK() EXECUTE AS CALLER` succeeded, so recreation was not needed.

**3. Roles with USAGE on the procedure**

Only one grant exists:

| Privilege | Grantee | Grant Option |
|-----------|---------|-------------|
| OWNERSHIP | ACCOUNTADMIN | true |

No USAGE grants to any role.

**4. Can PUBLIC or any application-facing role call it?**

**No.** There are no USAGE grants on the procedure. Only ACCOUNTADMIN holds OWNERSHIP. Neither PUBLIC nor any other role has been granted the ability to call `TRAIN_PLANT_B_RISK()`. The procedure now runs as CALLER, so even if USAGE were granted later, it would execute with the caller's privileges rather than the owner's ACCOUNTADMIN rights.
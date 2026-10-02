I'll execute this deployment step by step. Starting with the role/warehouse setup and file uploads.Role and warehouse set. Now uploading data files to the load stage.Both data files uploaded. Now truncating tables and loading data.Data loaded (6 evidence rows, 41 work orders). Now uploading Streamlit files and updating the app.All deployment statements succeeded. Running verification queries now.All statements succeeded. Here is the verification report:

---

**Row counts**

| Table | Expected | Actual |
|---|---|---|
| `PNEUMORA.ML.EVIDENCE` | 6 | **6** |
| `PNEUMORA.OPS.WORK_ORDERS` | 41 | **41** |

**EVIDENCE docs (DOC_KEY / STATUS)**

| DOC_KEY | STATUS |
|---|---|
| copilot_contract | PROMOTED_CROSS_VALIDATED |
| evidence | (null) |
| model_status | (null) |
| precursor | (null) |
| prediction | PROMOTED_CROSS_VALIDATED |
| track_summary | PROMOTED_CROSS_VALIDATED |

**held_out_pooled (prediction row)**

```json
{"air_caught":6,"caught":6,"events":9,"false_alerts":19,"false_per_day":0.0556,"median_margin":350}
```

**STREAMLIT_STAGE files**

| Name | Size |
|---|---|
| .streamlit/config.toml | 144 |
| app.py | 48,864 |
| assets/pneumora-logo-reversed.svg | 1,472 |
| environment.yml | 144 |
| status_rules.py | 6,320 |

**Streamlit app**

| Name | Title | URL ID |
|---|---|---|
| PNEUMORA_COPILOT | PNEUMORA early air-leak predictor | df4d72ofa3zbhz6wswdh |
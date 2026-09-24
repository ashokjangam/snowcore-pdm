I'll work through all four steps sequentially.

**Step 1: Confirm the corrected query runs.**Query runs successfully — 15 rows returned. Now reading `app.py` from disk and uploading.Upload confirmed — `app.py` is now **25,200 bytes** (up from 24,960). Now confirming the Streamlit object still resolves.Streamlit object confirmed: `ROOT_LOCATION = @SNOWCORE_REAL.APPS.STREAMLIT_STAGE/snowcore_pdm`, `MAIN_FILE = app.py`. Now the final sweep on the two most-referenced views.## Report

| Check | Result |
|---|---|
| **Assumption query** | Runs successfully — 15 rows returned with columns `PLANT_SCOPE, NAME, VALUE, UNIT, IS_MEASURED, BASIS`. |
| **New file size** | **25,200 bytes** (up from 24,960 — 240 bytes larger, as expected from the column-name corrections). |
| **Streamlit object** | Still exists, still points at `@SNOWCORE_REAL.APPS.STREAMLIT_STAGE/snowcore_pdm` with `MAIN_FILE = 'app.py'`. |
| **V_COST_BY_MACHINE columns** | All 8 app-referenced columns (`MACHINE_CODE`, `WORK_ORDERS`, `BREAKDOWN_HOURS`, `MAINTENANCE_COST`, `IDLE_INCIDENTS`, `IDLE_HOURS`, `IDLE_FORGONE_MARGIN`, `PCT_COST_FROM_IDLING`) exist. **No mismatch.** |
| **V_PLANT_A_HEALTH columns** | All 7 app-referenced columns (`MACHINE_CODE`, `HEALTH_DATE`, `HEALTH_INDEX_AVG`, `HEALTH_INDEX_WORST`, `CHANNEL_EXCURSIONS`, `DOMINANT_CHANNEL`, `ANY_SCORED_PERIOD`) exist. **No mismatch.** |

No further column mismatches found. The fix is complete.
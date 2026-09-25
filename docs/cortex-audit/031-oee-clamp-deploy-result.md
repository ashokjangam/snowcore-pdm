I'll upload the app and run the validation queries. Let me start by reading the current app.py to confirm the clamped definition, then execute everything.The app already uses `.clip(upper=1.0)` on each OEE term (lines 802-804), so the weekly trend is clamped to [0, 1]. Now I'll upload and run the validation queries.Now running the validation queries.## Deploy & validation summary

| Metric | Value |
|---|---|
| **Staged file** | `streamlit_stage/snowcore_pdm/app.py` |
| **Staged bytes** | 54 512 |
| **Staged timestamp** | Fri, 25 Sep 2026 06:32:55 GMT |
| **Weeks** | 105 |
| **Out-of-range weeks** | **0** |
| **Min weekly OEE** | 0.2926 |
| **Max weekly OEE** | 0.7310 |
| **Weeks capped** (at least one term hit the 1.0 cap) | 2 |
| **Days clamped** (`QUALITY_CLAMPED` in view) | 107 / 2 367 |

The clamped weekly OEE definition stays strictly within [0, 1] -- zero weeks out of range. Only 2 of 105 weeks had any component exceed its denominator (triggering the cap), and at the daily level 107 of 2 367 days were quality-clamped.
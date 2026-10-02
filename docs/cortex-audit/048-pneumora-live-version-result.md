I'll work through this step by step. Let me start with Step 1.No live version found. The DESCRIBE shows `live_version_location_uri` is `None` — the app uses VERSION$1 as its default. Let me list that version instead.The file is compressed on the stage. Let me try a different approach to read it.Got the environment.yml from the source stage. Now let me also read the one from the deployed version.Reading the snow:// environment.yml directly fails with a domain error. The DESCRIBE output already shows `user_packages`: `python==3.11,streamlit==1.52.2,plotly,pandas,numpy,snowflake-snowpark-python`. Step 1 is complete.Now running Step 2 — the package probe.Probe succeeded. All packages resolve and import correctly.Step 3 — attempting COPY FILES first.COPY FILES failed — no live version exists. Falling back to CREATE OR REPLACE.Streamlit recreated. Now verifying the live version.No pyproject.toml — it was dropped during the CREATE OR REPLACE. Now reading the deployed environment.yml and getting DESCRIBE/SHOW.---

## Report

### 1. Step 1 — Live file list and environment.yml BEFORE sync

There was **no live version** (`live_version_location_uri` = None). The app was running from **VERSION\$1**, which contained:

| File | Size |
|---|---|
| `.streamlit/config.toml` | 144 |
| `app.py` | 29,840 |
| `assets/pneumora-logo-reversed.svg` | 1,472 |
| `environment.yml` | 160 |
| **`pyproject.toml`** | **896** |
| `status_rules.py` | 6,304 |

DESCRIBE showed `user_packages`: `python==3.11,streamlit==1.52.2,plotly,pandas,numpy,snowflake-snowpark-python`
(Note: plotly/pandas had **no pinned versions**, and **numpy** was present — differing from the stage environment.yml.)

**Source stage environment.yml** content:
```yaml
name: sf_env
channels:
  - snowflake
dependencies:
  - streamlit=1.52.2
  - plotly=6.5.0
  - pandas=2.3.3
  - snowflake-snowpark-python
```

Reading the snow:// environment.yml directly failed: `Domain 'STREAMLIT' is not supported by SnowURL in infer_schema.`

### 2. Step 2 — Probe result

```
python 3.11.16 streamlit 1.52.2 plotly 6.5.0 pandas 2.3.3
```

All packages resolved and imported successfully, including `plotly.graph_objects` and `plotly.subplots`.

### 3. Step 3 — Sync method

- **COPY FILES failed**: `Live version is not found.`
- **CREATE OR REPLACE STREAMLIT** was used (fallback). Succeeded.

### 4. Live file list and environment.yml AFTER sync

VERSION\$1 files after recreation (no pyproject.toml):

| File | Size |
|---|---|
| `.streamlit/config.toml` | 144 |
| `app.py` | 29,920 |
| `assets/pneumora-logo-reversed.svg` | 1,472 |
| `environment.yml` | 144 |
| `status_rules.py` | 6,304 |

**pyproject.toml**: **Not present** — eliminated by CREATE OR REPLACE.

DESCRIBE now shows `user_packages`: `streamlit==1.52.2,plotly==6.5.0,pandas==2.3.3,snowflake-snowpark-python` (versions pinned correctly, no stray numpy).

### 5. Runtime and URL

- **runtime_name**: `SYSTEM$WAREHOUSE_RUNTIME`
- **url_id**: `df4d72ofa3zbhz6wswdh`All three steps completed successfully. The key fix: the old deployment had a stray `pyproject.toml` and unpinned plotly/pandas versions with an extra numpy dependency — the CREATE OR REPLACE cleaned all of that up and the environment.yml now drives the correct pinned package set.
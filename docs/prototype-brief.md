# PNEUMORA — submission pack

## Prototype/MVP Brief

Paste the paragraph below into the form. It is under the 1,024-character limit.

> PNEUMORA is a predictive-maintenance command center for a real train air compressor, built on Snowflake. Real MetroPT sensor streams (pressure, motor current, oil temperature, load) from three compressors and nine documented failures sit beside labelled synthetic work orders, parts, crew and an example-factory OEE view. Tested on compressors it never saw, its physics leak predictor flagged 6 of 7 air leaks at least 2 h before the train had to leave service, a median 5.8 h ahead, at 0.056 false alerts/day (existing alarm: 3 of 7, 0.49/day). All pre-declared gates passed. It predicts the breakdown, not the leak: only 1 of 9 alerts preceded leak onset. SNOWFLAKE.ML.ANOMALY_DETECTION caught 4 of 4 on a time split. Gradual leaks injected into real data are caught 28 of 30 times at twice normal air loss. Cortex AI_COMPLETE explains each failure citing only observed facts, and a Snowflake procedure records idempotent maintenance decisions.

## Links

- GitHub branch: `https://github.com/ashokjangam/snowcore-pdm/tree/feat/pneumora-metropt`
- Deployed prototype: `https://app.snowflake.com/streamlit/FMXJOWH/BRC04642/#/apps/df4d72ofa3zbhz6wswdh`
- Team page: [TRidents on Hack2skill](https://hack2skill.com/event/cococlihack-gccedition/dashboard/team-management?utm_source=hack2skill&utm_medium=homepage)
- Team leader: [Ashok Jangam](https://www.linkedin.com/in/jangam-ashok-53a95812b/)
- Demo video: add the final uploaded URL after recording.

## What to show in the 3–5 minute video

Target duration: **4:20**. Record at 1080p. A CoCo CLI prompt proves the
processing in Snowflake; the Streamlit page proves the operator experience.

### 0:00–0:25 — The problem, in one asset

On screen: title slide, then the app's **What needs attention** page.

> A metro train's air compressor feeds its brakes and doors. When it leaks, the
> train has to come out of service. PNEUMORA watches the real sensor streams from
> that compressor and turns them into a decision a maintenance crew can act on.

### 0:25–1:25 — Capability 1: predict the breakdown

In CoCo CLI run `docs/demo/01_detect.txt`. It reads `PNEUMORA.CORE.FAILURES`,
`PNEUMORA.ML.ALERTS` and `PNEUMORA.ML.NATIVE_ANOMALY_SUMMARY`.

Then open **Can it predict?** (top section):

1. Held out by compressor: 6 of 7 air leaks flagged at least 2 h before the
   train had to leave service, a median 5.8 h ahead, at 0.056 false alerts per
   day. The existing alarm: 3 of 7 at 0.49.
2. Status `PROMOTED_CROSS_VALIDATED`; point to the five gates under the table.
3. Say the caveat out loud: this is version 2 of the protocol, written after
   version 1 failed on false alerts, and no untouched data remains.

### 1:25–2:20 — Can it see the leak before it starts? We tried everything

Scroll to the second section of **Can it predict?**

1. The arms table: label-free physics, three supervised models, synthetic
   replay, rolling baseline. The best warned 1 of 9 before the leak began.
2. The heatmap: only F04 turns red before 0 h.
3. The injection chart: a gradual leak at 2× normal air loss is caught 28 of 30
   times, against 7 of 30 with no leak.
4. Native Snowflake ML: 4 of 4 caught in time, 0 before onset.

> These leaks start abruptly, so PNEUMORA predicts the breakdown, not the leak.
> That still gives the crew hours to pull the train before it fails in service.

### 2:20–3:15 — Capability 2: root cause in plain words

In CoCo CLI run `docs/demo/02_rca.txt`, or in the app open **Leak alerts vs real
failures**, choose F04 and click **Explain F04 with Cortex**.

> Cortex receives only these observed facts. It must quote the field behind every
> number, may not name a component the report does not name, and ends with one
> physical check for the next inspection.

### 3:15–3:55 — Capability 3: record the decision

In CoCo CLI run `docs/demo/03_action.txt`. The first call returns
`deduplicated: false`, the second the same action id with `deduplicated: true`.
Open **What needs attention** and show the same row in the decision log.

### 3:55–4:20 — Close

> Real sensors, nine real failures, three compressors. A promoted predictor that
> warns hours before the train must leave service, a study that shows exactly
> where prediction stops, cited root cause and an auditable decision log, all
> inside Snowflake.

## Recording checklist

- Log into Snowflake before recording; pre-open the app and the CoCo terminal.
- Do not rehearse `03_action.txt` on `DEMO_VIDEO|F04`, or the first call will
  already show `deduplicated: true`. If you must, delete that row afterwards:
  `DELETE FROM PNEUMORA.OPS.ACTION_LOG WHERE SOURCE_KEY = 'DEMO_VIDEO|F04';`
- Say "synthetic" whenever work orders, parts, crew or OEE are on screen.
- Zoom the browser to 110–125%; hide notifications.
- End with the GitHub URL, prototype URL and deck title on screen for three seconds.

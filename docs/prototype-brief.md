# TRIDENT OPS — submission pack

## Prototype/MVP Brief

Paste the paragraph below into the form. It is under the 1,024-character limit.

> TRIDENT OPS is an evidence-first Predictive Maintenance and OEE Command Center built on Snowflake. It uses two real public datasets without fabricating a join: PIADE provides two years of packaging-line states, alarms and production counts for weighted OEE, loss ownership and next-hour risk; MetroPT provides compressor sensor and failure evidence on a separate page. Three modular capabilities run end to end: (1) OEE and risk views from governed Snowflake tables, (2) bounded Cortex root-cause narration that cites anonymised alarm-pattern rows and abstains beyond evidence, and (3) an idempotent triage procedure that persists acknowledge, inspect and snooze actions. Every figure is labelled Observed, Derived, Model, Scenario or Operator-entered. The app states its limits: MetroPT is post-onset detection, PIADE has no condition sensors, synthetic ERP is not fact, and no measured OEE lift or realised savings is claimed.

## Links

- GitHub branch: `https://github.com/ashokjangam/snowcore-pdm/tree/feat/tridents-ops`
- Deployed prototype: `https://app.snowflake.com/streamlit/FMXJOWH/BRC04642/#/apps/bd2ocwt4eblddojvzl7v`
- Team page: [TRidents on Hack2skill](https://hack2skill.com/event/cococlihack-gccedition/dashboard/team-management?utm_source=hack2skill&utm_medium=homepage)
- Team leader: [Ashok Jangam](https://www.linkedin.com/in/jangam-ashok-53a95812b/)
- Demo video: add the final uploaded URL after recording.

## What to show in the 3–5 minute video

Target duration: **4:15**. Record at 1080p. Use a split narrative: a CoCo CLI
command proves the processing; the Streamlit page proves the output. Do not tour
every page.

### 0:00–0:20 — Cold open: the rule of the demo

On screen: title slide, then TRIDENT OPS sidebar.

Say:

> Manufacturing data usually gives us either operations or condition sensors,
> not a perfect joined dataset. We refused to fake that join. TRIDENT OPS keeps
> two real plants separate and turns evidence into an auditable decision.

### 0:20–1:25 — Capability 1: OEE and ownership

In CoCo CLI, run the saved prompt in `docs/demo/01_oee.txt`. It queries
`SNOWCORE_REAL.GOLD.V_OEE_ROLLUP` and the action queue.

Then open **Command Center**:

1. Point to weighted OEE 46.78%.
2. Say it is recomputed from summed seconds and packages, not averaged across lines.
3. Point to waiting/idle. Explain that planning owns idle; maintenance owns faults.
4. Point to the Evidence Passport and `DERIVED_FROM_OBSERVED`.

### 1:25–2:25 — Capability 2: cited root-cause investigation

Open **Triage + cited RCA**, choose `s_1` and show the top anonymised alarm.
Click **Narrate these five rows with Cortex**.

Say:

> Cortex receives only these five rows. It may describe recurrence and timing,
> but it cannot invent a component because the publisher anonymised the alarm.

Point to the cited alarm code, precursor rate, repeat rate and caveat.

### 2:25–3:20 — Capability 3: persistent action

In CoCo CLI, run `docs/demo/03_action.txt` twice. The workflow writes the stable
source key `DEMO_VIDEO|s_2`, selects that exact row, and reports whether the
second call was deduplicated.

Open **Flight Recorder** and show the same `DEMO_VIDEO|s_2` row and action id.

Say:

> This is not a toast. It is an idempotent Snowflake row with actor, evidence key,
> timestamp and status, and it survives a reload.

### 3:20–3:55 — Sensor evidence, without overclaiming

Open **Sensor Evidence**. Point to the zero line and signed minutes versus onset.

Say:

> MetroPT gives us real compressor sensors, but the frozen detector usually fires
> after the leak begins. We label it detection and NO PROMOTION. It is a separate
> asset and is never joined to packaging OEE.

### 3:55–4:15 — Close

Return to **Command Center**.

> Three capabilities: compute, explain, act. Two real evidence lanes. Zero
> fabricated joins. TRIDENT OPS makes the limits visible so a plant can trust the
> decision path.

## Recording checklist

- Log into Snowflake before recording; pre-open the app and CoCo terminal.
- Use a clean browser profile and hide account notifications.
- Run the action once in rehearsal, then delete the rehearsal row.
- Keep the mouse still while speaking; zoom the browser to 110–125%.
- Do not show `Financial Risk`, synthetic euro totals, the retired SNOWCORE app,
  or the PNEUMORA factory-scenario OEE.
- End with the GitHub URL, prototype URL and deck title on screen for three seconds.

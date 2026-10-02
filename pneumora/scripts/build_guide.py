"""Build docs/pneumora-a-to-z.html from the frozen study results and product files."""

from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
OUT = REPO / "docs" / "pneumora-a-to-z.html"
RESEARCH = ROOT / "autoresearch"
APP_URL = "https://app.snowflake.com/streamlit/FMXJOWH/BRC04642/#/apps/df4d72ofa3zbhz6wswdh"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


TRACK = load(ROOT / "data" / "product" / "copilot_track.json")
OFFICIAL = load(RESEARCH / "official_study.json")
EXTERNAL = load(RESEARCH / "external_result.json")
LOUO = load(RESEARCH / "louo_study.json")
SYNTH = load(RESEARCH / "synthetic_model_study.json")
FREEZE = load(RESEARCH / "official_freeze.json")
MANIFEST = load(ROOT / "data" / "snowflake" / "manifest.json")
PROFILE = load(ROOT / "data" / "processed" / "data_profile.json")
e = html.escape


def ts(text: str) -> datetime:
    return datetime.fromisoformat(str(text).replace(" ", "T")[:19])


def span(minutes: float) -> str:
    return f"{minutes / 60:.1f} h" if abs(minutes) >= 120 else f"{abs(minutes):.0f} min"


def badge(kind: str) -> str:
    label = {"obs": "OBSERVED", "der": "DERIVED", "syn": "SYNTHETIC", "cho": "CHOICE", "mod": "MODEL", "drop": "DROPPED"}[kind]
    return f"<span class='badge b-{kind}'>{label}</span>"


def table(headers: list[str], rows: list[list], numeric: set[int] = frozenset()) -> str:
    head = "".join(f"<th class='{'num' if i in numeric else ''}'>{e(h)}</th>" for i, h in enumerate(headers))
    body = "".join(
        "<tr>" + "".join(f"<td class='{'num' if i in numeric else ''}'>{c}</td>" for i, c in enumerate(row)) + "</tr>" for row in rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def timeline_svg() -> str:
    width, left, right = 1100, 200, 20
    t0, t1 = ts(TRACK["window"][0]), ts(TRACK["window"][1])
    total = (t1 - t0).total_seconds()

    def x(t) -> float:
        return left + (ts(t) - t0).total_seconds() / total * (width - left - right)

    parts = []
    for name, y in (("Reported failures", 40), ("Co-pilot alerts", 95), ("Existing low-pressure alarm", 150)):
        parts.append(f"<text x='0' y='{y + 4}' fill='#8b9bb0' font-size='12'>{name}</text>"
                     f"<line x1='{left}' x2='{width - right}' y1='{y}' y2='{y}' stroke='#243044'/>")
    month = datetime(t0.year, t0.month, 1)
    while month <= t1:
        if month >= t0:
            px = x(month.isoformat())
            parts.append(f"<line x1='{px:.1f}' x2='{px:.1f}' y1='18' y2='165' stroke='#1a2433'/>"
                         f"<text x='{px + 3:.1f}' y='182' fill='#8b9bb0' font-size='11'>{month:%b}</text>")
        month = datetime(month.year + (month.month == 12), month.month % 12 + 1, 1)
    for f in TRACK["failures"]:
        x0, x1 = x(f["start"]), x(f["end"])
        parts.append(f"<g><title>{e(f['id'])} · {e(f['report'])}</title><rect x='{x0 - 2:.1f}' y='28' width='{max(5, x1 - x0 + 4):.1f}' height='24' rx='4' fill='#f06a6a'/>"
                     f"<text x='{x0:.1f}' y='22' fill='#f06a6a' font-size='11'>{e(f['id'])}</text>"
                     f"<line x1='{x0:.1f}' x2='{x0:.1f}' y1='52' y2='160' stroke='#f06a6a' stroke-dasharray='3 3' opacity='.5'/></g>")
    for r in TRACK["copilot"]:
        fill = "#f5b942" if r["outcome"] == "caught_in_time" else "#111823"
        parts.append(f"<g><title>{e(r['alert_id'])} · {e(r['raised_at'])} · {e(r['outcome'])}</title>"
                     f"<circle cx='{x(r['raised_at']):.1f}' cy='95' r='7' fill='{fill}' stroke='#f5b942' stroke-width='2'/></g>")
    for r in TRACK["low_pressure_alarm"]:
        hit = r["outcome"] == "caught_in_time"
        parts.append(f"<rect x='{x(r['raised_at']) - 1:.1f}' y='140' width='{4 if hit else 2}' height='20' fill='{'#dfe7f1' if hit else '#5d6d84'}'/>")
    return f"<svg viewBox='0 0 {width} 190' width='100%' role='img' aria-label='Co-pilot and alarm alerts against reported failures'>{''.join(parts)}</svg>"


def zoom_svg(failure_id: str) -> str:
    f = next(item for item in TRACK["failures"] if item["id"] == failure_id)
    points = f["series"]
    width, height, left, right, top, bottom = 1100, 300, 50, 50, 24, 36
    t0, t1 = ts(points[0]["t"]), ts(points[-1]["t"])
    total = (t1 - t0).total_seconds()

    def x(t) -> float:
        return left + (ts(t) - t0).total_seconds() / total * (width - left - right)

    peak = max(10.0, max(p["loaded"] for p in points))

    def yl(v: float) -> float:
        return top + (1 - (max(v, 0) / peak) ** 0.5) * (height - top - bottom)

    pressures = [p["reservoirs"] for p in points if p["reservoirs"] is not None]
    pmin, pmax = min(6.5, *pressures), max(10.0, *pressures)

    def yp(v: float) -> float:
        return top + (pmax - v) / (pmax - pmin) * (height - top - bottom)

    area = f"M{x(points[0]['t']):.1f},{yl(0):.1f} " + " ".join(f"L{x(p['t']):.1f},{yl(p['loaded']):.1f}" for p in points) + f" L{x(points[-1]['t']):.1f},{yl(0):.1f} Z"
    line = " ".join(f"{'L' if i else 'M'}{x(p['t']):.1f},{yp(p['reservoirs']):.1f}" for i, p in enumerate(p for p in points if p["reservoirs"] is not None))
    parts = [
        f"<rect x='{x(f['start']):.1f}' y='{top}' width='{max(2, x(min(f['end'], points[-1]['t'])) - x(f['start'])):.1f}' height='{height - top - bottom}' fill='#f06a6a' opacity='.08'/>",
        f"<path d='{area}' fill='#f5b942' opacity='.25' stroke='#f5b942'/>",
        f"<line x1='{left}' x2='{width - right}' y1='{yl(TRACK['threshold_minutes']):.1f}' y2='{yl(TRACK['threshold_minutes']):.1f}' stroke='#f5b942' stroke-dasharray='2 3'/>",
        f"<text x='{left + 4}' y='{yl(TRACK['threshold_minutes']) - 5:.1f}' fill='#f5b942' font-size='11'>Co-pilot threshold {TRACK['threshold_minutes']:.2f} min, held {TRACK['persistence_minutes']} min</text>",
        f"<path d='{line}' fill='none' stroke='#5aa9ff' stroke-width='2.5'/>",
        f"<line x1='{left}' x2='{width - right}' y1='{yp(7):.1f}' y2='{yp(7):.1f}' stroke='#5aa9ff' stroke-dasharray='4 4' opacity='.6'/>",
        f"<text x='{width - right - 4}' y='{yp(7) - 5:.1f}' fill='#5aa9ff' font-size='11' text-anchor='end'>7 bar low-air point</text>",
    ]
    for v in (2, 10, 30, 60, 120):
        if v <= peak:
            parts.append(f"<text x='6' y='{yl(v) + 4:.1f}' fill='#f5b942' font-size='11'>{v}</text>")
    for v in (7, 8, 9, 10):
        if pmin <= v <= pmax:
            parts.append(f"<text x='{width - 36}' y='{yp(v) + 4:.1f}' fill='#5aa9ff' font-size='11'>{v}</text>")
    markers = [(f["start"], "#f06a6a", "Failure reported"), (f["copilot_first"], "#f5b942", "Co-pilot alert"),
               (f["lps_first"], "#dfe7f1", "Low-pressure alarm"), (f["removal_deadline"], "#a78bfa", "Last moment to act")]
    for row, (moment, color, label) in enumerate(markers):
        if moment and t0 <= ts(moment) <= t1:
            px = x(moment)
            parts.append(f"<line x1='{px:.1f}' x2='{px:.1f}' y1='{top}' y2='{height - bottom}' stroke='{color}' stroke-width='2'/>"
                         f"<text x='{px + 4:.1f}' y='{top + 12 + row * 14}' fill='{color}' font-size='11'>{label}</text>")
    for k in range(7):
        seconds = total * k / 6
        moment = datetime.fromtimestamp(t0.timestamp() + seconds)
        parts.append(f"<text x='{left + seconds / total * (width - left - right):.1f}' y='{height - 12}' fill='#8b9bb0' font-size='11' text-anchor='middle'>{moment:%d %b %H:%M}</text>")
    return f"<svg viewBox='0 0 {width} {height}' width='100%' role='img' aria-label='Signals around {e(failure_id)}'>{''.join(parts)}</svg>"


def failure_rows() -> list[list]:
    rows = []
    for f in TRACK["failures"]:
        co = f["copilot_minutes_after_start"]
        co_text = "missed" if co is None else (f"{span(-co)} before onset" if co < 0 else f"{span(co)} after onset")
        lps = f["lps_minutes_after_start"]
        rows.append([
            e(f["id"]), e(f["report"]), f"{ts(f['start']):%d %b %H:%M} – {ts(f['end']):%d %b %H:%M}",
            e(f["onset_precision"]), co_text,
            "—" if f["copilot_minutes_before_end"] is None else span(f["copilot_minutes_before_end"] - 120),
            "did not fire in time" if lps is None else f"{span(lps)} after onset",
        ])
    return rows


def event_rows(unit_key: str) -> list[list]:
    unit = EXTERNAL["units"][unit_key]
    rows = []
    for det, lps in zip(unit["detector"]["events"], unit["lps_existing_alarm"]["events"]):
        rows.append([
            e(det["event_id"]), e(det["kind"].replace("_", " ")), f"{e(det['start'])} – {e(det['end'])}",
            f"{det['minutes_after_start']:.0f} min after start" if det["caught_in_time"] else "missed",
            f"{lps['minutes_after_start']:.0f} min after start" if lps["caught_in_time"] else "missed",
        ])
    return rows


def louo_rows() -> list[list]:
    rows = []
    for fold in LOUO["folds"]:
        held, lps = fold["held_out_stats"], fold["lps_held_out_stats"]
        rows.append([e(fold["held_out"]), f"<code>{e(fold['chosen'])}</code>", f"{held['caught']} of {held['events']}",
                     f"{held['false_per_day']:.3f}", f"{lps['caught']} of {lps['events']}", f"{lps['false_per_day']:.3f}"])
    return rows


def gate_list(gates: dict) -> str:
    return "".join(f"<li>{'✅' if ok else '❌'} {e(name.replace('_', ' '))}</li>" for name, ok in gates.items())


def snowflake_rows() -> list[list]:
    schema = {"TELEMETRY_5M": "CORE", "FAILURES": "CORE", "DAILY_KPIS": "CORE", "FAILURE_ZOOM": "ML", "ALERTS": "ML",
              "EVIDENCE": "ML", "WORK_ORDERS": "OPS", "PARTS": "OPS", "TECHNICIANS": "OPS", "FACTORY_SCENARIO": "OPS"}
    origin = {"CORE": badge("obs"), "ML": badge("der"), "OPS": badge("syn")}
    return [[f"<code>PNEUMORA.{schema[name]}.{name}</code>", origin[schema[name]], f"{item['rows']:,}", e(", ".join(item["columns"]))]
            for name, item in MANIFEST.items()]


def build() -> str:
    tally = TRACK["tally"]
    louo_model, louo_lps = LOUO["held_out_pooled"], LOUO["lps_pooled_same_events"]
    final = OFFICIAL["final_result"]
    pooled = EXTERNAL["pooled"]
    synth_model = SYNTH["model"]
    control = SYNTH["wrong_physics_control"]
    nav = [
        ("summary", "0 · One-page summary"), ("doing", "1 · How the co-pilot is doing"), ("problem", "2 · The problem"),
        ("journey", "3 · What we tried"), ("data", "4 · The three datasets"), ("signal", "5 · The signal"),
        ("detector", "6 · The co-pilot detector"), ("protocol", "7 · How it is judged"), ("results", "8 · Every study result"),
        ("forecast", "9 · Why no hours-ahead forecast"), ("track", "10 · Track record"), ("product", "11 · The product"),
        ("why", "12 · Every status has a reason"), ("snowflake", "13 · Snowflake deployment"), ("truth", "14 · Data truth labels"),
        ("not", "15 · What it does NOT do"), ("runbook", "16 · Runbook and file map"), ("glossary", "17 · Glossary"),
    ]
    sections = f"""
<section id="summary">
<h1>PNEUMORA: the complete A to Z guide</h1>
<p class="lede">An early air-leak co-pilot for a Porto metro train's air production unit (APU), built on the public MetroPT datasets.
It watches one physical signal, how long the compressor works without resting, and alerts when an air leak is probably developing.
It runs beside the train's existing low-pressure alarm and never replaces it.</p>
<div class="grid g4">
  <div class="tile"><div class="k">Model status</div><div class="v" style="color:var(--amber)">Not promoted</div><div class="n">Four pre-declared studies, all <code>NO_PROMOTION</code>. Shipped as a labelled co-pilot.</div></div>
  <div class="tile"><div class="k">Held-out failures caught</div><div class="v">{louo_model['caught']} of {louo_model['events']}</div><div class="n">Existing alarm: {louo_lps['caught']} of {louo_lps['events']}. Air leaks {louo_model['air_caught']} of 7 vs {louo_lps['air_caught']} of 7.</div></div>
  <div class="tile"><div class="k">False alerts per healthy day</div><div class="v">{louo_model['false_per_day']:.3f}</div><div class="n">Budget 0.143 (one per week). Existing alarm {louo_lps['false_per_day']:.3f}. This is the gate that failed.</div></div>
  <div class="tile"><div class="k">Deployed</div><div class="v" style="color:var(--teal)">Snowflake</div><div class="n"><a href="{APP_URL}">PNEUMORA_COPILOT</a> in database <code>PNEUMORA</code>, warehouse <code>PNEUMORA_WH</code>.</div></div>
</div>
<div class="plain"><b class="t">In one sentence.</b> On the nine real failures we have, the co-pilot catches more air leaks in time than the existing alarm with about a third of its false alerts, but it still raises slightly more than one false alert a week, so it is shown as an assistant, not a promoted prediction model.</div>
</section>

<section id="doing">
<h2>1 · How the co-pilot is doing</h2>
<div class="grid g2">
<div class="card"><h3>What is working</h3><ul>
<li>On the four MetroPT-3 leaks it alerted on all four in time. The existing alarm caught {tally['low_pressure_alarm']['caught_in_time']}. On F04 it alerted <b>80 minutes before</b> the reported start, because the compressor's runs had already stretched to 3–5 minutes (normal is about 2).</li>
<li>Held out across three compressors it caught {louo_model['air_caught']} of 7 air leaks; the alarm caught {louo_lps['air_caught']}.</li>
<li>It is quiet: {louo_model['false_alerts']} false alerts in the held-out data against {louo_lps['false_alerts']} for the alarm.</li>
<li>Better than chance: random-alerter test p ≈ 2×10⁻⁵ (cross-validation) and p = {pooled['random_alerter_p_at_least_observed']:.3f} (untouched 2022 data).</li>
</ul></div>
<div class="card"><h3>What is not</h3><ul>
<li>False alerts are {louo_model['false_per_day']:.3f} per healthy day against a budget of 0.143. That one gate keeps it unpromoted.</li>
<li>On the untouched 2022 data it <b>tied</b> the alarm on air leaks (2 of 3 each) and fired 15–20 minutes later.</li>
<li>It catches no oil leaks (0 of 2). The alarm caught both, but only 57–66 hours after they began.</li>
<li>It is early <b>detection</b> (about an hour after onset), not a forecast hours ahead. Section 9 shows why the data does not allow that.</li>
<li>Nine failures in total is a small sample. Treat every rate here as coarse.</li>
</ul></div>
</div>
<div class="warn"><b class="t">Honest verdict.</b> As a leak co-pilot it adds real value: earlier and quieter than the alarm on air leaks. As a promoted predictive-maintenance model it is not there, and more tuning on the same nine failures would be fitting to the test. The next real step is more labelled failures, not more modelling.</div>
</section>

<section id="problem">
<h2>2 · The problem</h2>
<p>The APU feeds compressed air to a metro train's brakes, suspension and doors. When a pipe, coupling or dryer valve leaks, the compressor works harder to hold pressure until it cannot, and the train has to be withdrawn. The operator's need, published with the dataset, is to know <b>at least two hours before</b> the train becomes non-operational so it can be removed in a controlled way.</p>
<p>The train already has a low-pressure switch (LPS). It fires when air is already low, which is often too late and very noisy: it fired {tally['low_pressure_alarm']['alerts']} times in the MetroPT-3 test period, and {tally['low_pressure_alarm']['no_reported_failure']} of those matched no reported failure.</p>
</section>

<section id="journey">
<h2>3 · What we tried and what happened</h2>
<div class="timeline">
<div class="ev drop"><b>First campaign: forecast before onset</b> {badge('drop')}<br>Seven approaches (LPS, duty-cycle rule, cycle/pressure rule, Isolation Forest, autoencoder, synthetic-trained booster, wrong-physics control) warned <b>0 of 4</b> leaks inside a two-hour forecast window. PCA overlapped 2 of 4 with 230 false alerts. <code>NO_PROMOTION</code>.</div>
<div class="ev keep"><b>Second study: the dataset owner's protocol</b> {badge('cho')}<br>Switched to Veloso et al. (Scientific Data, 2022): caught in time means an alert between two hours before the reported start and two hours before the reported end. A physical detector, the compressor staying loaded for about an hour, caught 4 of 4 in development with {final['false_alerts']} false alerts in {final['healthy_days']:.0f} healthy days.</div>
<div class="ev drop"><b>Frozen, then tested once on untouched 2022 data</b><br>MetroPT 2022 and MetroPT-2: air leaks 2 of 3 (tie with the alarm, 15–20 min later), 1 false alert in {pooled['healthy_days']:.0f} healthy days. <code>{EXTERNAL['status']}</code>, because it did not beat the alarm.</div>
<div class="ev drop"><b>Third study: leave one compressor out</b><br>Pooled 9 failures across 3 compressors: {louo_model['caught']} of 9 caught vs {louo_lps['caught']} of 9; false alerts {louo_model['false_per_day']:.3f}/day vs budget 0.143. <code>{LOUO['status']}</code>.</div>
<div class="ev drop"><b>Fourth study: synthetic-trained model</b> {badge('syn')}<br>Trained only on healthy data plus 1,200 physics-based synthetic leaks. Caught {synth_model['caught']} of 9 with {synth_model['false_alerts']} false alerts; a control trained on deliberately wrong physics did better ({control['caught']} of 9, {control['false_alerts']} false alerts). <code>{SYNTH['status']}</code>. Synthetic data was never used to validate or score anything.</div>
<div class="ev keep"><b>Shipped: the co-pilot</b><br>The frozen detector runs beside the alarm, labelled <code>CROSS_VALIDATED_NOT_PROMOTED</code>, and drafts work orders for a person to review.</div>
</div>
</section>

<section id="data">
<h2>4 · The three datasets</h2>
{table(["Unit", "Source", "Cadence", "Period", "Failures used", "Role"], [
    ["MetroPT-3", f"UCI 791, DOI <code>{e(PROFILE['source_doi'])}</code>", f"{PROFILE['median_cadence_seconds']} s", f"{e(PROFILE['started_at'][:10])} to {e(PROFILE['ended_at'][:10])}", "F01–F04, four air leaks", "Development (designed on it)"],
    ["MetroPT 2022", "Zenodo 6854240", "1 s", "2022-01-01 to 2022-06-02", "E1, E2 air leaks; E3 oil leak", "Untouched test, then cross-validation"],
    ["MetroPT-2", "Zenodo 7766691", "1 s", "2022-04-28 to 2022-07-28", "X1 air leak; X2 oil leak", "Untouched test, then cross-validation"],
])}
<p>{badge('obs')} Signals used: reservoir and panel pressure (<code>Reservoirs</code>, <code>TP3</code>), motor current, oil temperature, the compressor's load state (<code>COMP == 0</code> means loaded) and the low-pressure switch (<code>LPS</code>). Everything is resampled to five-minute bins. MetroPT-3 has {PROFILE['rows']:,} raw rows.</p>
<div class="warn"><b class="t">Precision caveat.</b> F01's log gives only the date, so "minutes after onset" for F01 means minutes after midnight.</div>
</section>

<section id="signal">
<h2>5 · The signal: how long the compressor works without resting</h2>
<p>A healthy compressor loads, fills the reservoir and rests; healthy loaded runs have a median of about <b>1.8 minutes</b>. During an air leak it cannot catch up, so it works non-stop, sometimes for hours, while pressure barely rises. That one physical fact is the whole detector. Generic anomaly scores (PCA, autoencoder, Isolation Forest) reacted to changes in how the train was operated and gave 1.5–2 false alerts a day, so they were dropped.</p>
<h3>F04: the clearest case</h3>
{zoom_svg('F04')}
<p class="legend-row"><span style="color:var(--amber)">■ Non-stop run length (minutes, square-root scale)</span><span style="color:var(--blue)">— Reservoir pressure (bar)</span><span style="color:var(--red)">■ Reported failure period</span></p>
<p>From noon the runs stretch to 3–5 minutes, above the 2.15-minute threshold, and stay there for an hour, so the co-pilot alerts at 13:10, 80 minutes before the reported 14:30 start. The alarm never fires in time.</p>
</section>

<section id="detector">
<h2>6 · The co-pilot detector, exactly</h2>
<div class="card">
<p><b>Frozen configuration:</b> <code>{e(FREEZE['detector'])}</code></p>
<p>{e(FREEZE['detector_plain'])}</p>
{table(["Step", "Rule"], [[e(k.replace('_', ' ')), e(str(v))] for k, v in FREEZE['recipe'].items()])}
</div>
<div class="plain"><b class="t">No failure labels used to fit or calibrate.</b> Each compressor learns its own normal from its first 21 days, then sets the threshold on the next 14 days so it raises at most one alert per week there. On MetroPT-3 that gives {TRACK['threshold_minutes']:.2f} minutes.</div>
</section>

<section id="protocol">
<h2>7 · How it is judged</h2>
<p><b>Target:</b> {e(FREEZE['target'])}.</p>
<p><b>Gates declared before scoring (untouched test):</b></p>
{table(["Gate", "Requirement"], [[e(k.replace('_', ' ')), e(v)] for k, v in FREEZE['promotion_gates_external'].items()])}
<ul>{''.join(f'<li>{e(rule)}</li>' for rule in FREEZE['rules'])}</ul>
<div class="warn"><b class="t">Bug found and disclosed.</b> The first campaign measured the alert-merge gap from the episode start, so one long condition counted as a new alert every 30 minutes and inflated false-alert counts. Fixed in the second study; the episode now ends only once flags stop for more than 30 minutes.</div>
</section>

<section id="results">
<h2>8 · Every study result</h2>
<h3>Development, MetroPT-3 (not a clean test)</h3>
{table(["Failure", "Report", "Window", "Onset precision", "Co-pilot", "Time to act", "Existing alarm"], failure_rows())}
<h3>Untouched 2022 data, scored once · <code>{EXTERNAL['status']}</code></h3>
{table(["Event", "Kind", "Window", "Co-pilot", "Existing alarm"], event_rows('METROPT_2022_ZENODO_6854240') + event_rows('METROPT2_ZENODO_7766691'))}
<ul>{gate_list(EXTERNAL['gates'])}</ul>
<h3>Leave one compressor out · <code>{LOUO['status']}</code></h3>
{table(["Held-out unit", "Chosen on the other two", "Caught", "False/day", "Alarm caught", "Alarm false/day"], louo_rows())}
<p>Pooled: co-pilot {louo_model['caught']} of 9 ({louo_model['air_caught']} of 7 air leaks), {louo_model['false_alerts']} false alerts; alarm {louo_lps['caught']} of 9 ({louo_lps['air_caught']} of 7), {louo_lps['false_alerts']} false alerts.</p>
<ul>{gate_list(LOUO['gates'])}</ul>
<h3>Synthetic-trained model · <code>{SYNTH['status']}</code></h3>
{table(["Nine real failures", "Synthetic-trained", "Wrong-physics control"], [
    ["Caught in time", f"{synth_model['caught']}", f"{control['caught']}"],
    ["Air leaks", f"{synth_model['air_caught']} of 7", f"{control['air_caught']} of 7"],
    ["False alerts per healthy day", f"{synth_model['false_per_day']:.3f}", f"{control['false_per_day']:.3f}"],
])}
<ul>{gate_list(SYNTH['gates'])}</ul>
<p>The control was trained on deliberately wrong leak physics yet did better, which shows the synthetic leak shapes add nothing the healthy baseline does not already give.</p>
</section>

<section id="forecast">
<h2>9 · Why there is no hours-ahead forecast</h2>
<p>Each failure was ranked against the same compressor's healthy periods from six hours before onset to two hours after.</p>
<ul>
<li><b>Six to two hours before onset:</b> ordinary in eight of nine events. Only F04 shows anything (95th–100th percentile).</li>
<li><b>Last two hours before onset:</b> clear only in F04, X1 and X2 (oil temperature).</li>
<li><b>First hour after onset:</b> 96th–100th percentile for six of seven air leaks.</li>
</ul>
<div class="bad"><b class="t">What this means.</b> These leaks are abrupt: a burst pipe or a stuck drain valve. Nothing logged foreshadows them hours ahead, so every attempt to alert before onset scored 0 of 4. On this data, predictive maintenance means detecting a developing failure early enough to remove the train before it becomes non-operational, which is how the operator's protocol defines it.</div>
</section>

<section id="track">
<h2>10 · Track record: every prediction against what happened</h2>
{timeline_svg()}
<p class="legend-row"><span style="color:var(--red)">■ Reported failure</span><span style="color:var(--amber)">● Co-pilot alert on a failure</span><span style="color:var(--amber)">○ Co-pilot alert, no reported failure</span><span>| Low-pressure alarm</span></p>
<div class="grid g4">
<div class="tile"><div class="k">Co-pilot alerts</div><div class="v">{tally['copilot']['alerts']}</div><div class="n">{tally['copilot']['caught_in_time']} of {tally['failures']} failures caught in time</div></div>
<div class="tile"><div class="k">Co-pilot, no reported failure</div><div class="v">{tally['copilot']['no_reported_failure']}</div><div class="n">Not proven false; may be unlogged faults. Counted against it anyway.</div></div>
<div class="tile"><div class="k">Alarm alerts</div><div class="v">{tally['low_pressure_alarm']['alerts']}</div><div class="n">{tally['low_pressure_alarm']['caught_in_time']} of {tally['failures']} failures caught in time</div></div>
<div class="tile"><div class="k">Alarm, no reported failure</div><div class="v">{tally['low_pressure_alarm']['no_reported_failure']}</div><div class="n">The noise the co-pilot avoids</div></div>
</div>
<div class="warn"><b class="t">Read with care.</b> These are the four failures the detector was designed on. The honest numbers are the cross-validated and untouched results in section 8.</div>
</section>

<section id="product">
<h2>11 · The product</h2>
<div class="grid g2">
<div class="card"><h3>Local app (FastAPI + SQLite maintenance system)</h3><ul>
<li><b>What needs attention:</b> status headline, a "Why?" panel, next action, time-to-low-air projection, last four hours of pressure.</li>
<li><b>Co-pilot track record:</b> the timeline above, a per-failure zoom (F01–F04) and every prediction with its outcome. Each alert has a Replay button.</li>
<li><b>Maintenance:</b> a working board (start, parts, done), parts stock and crew. Co-pilot alerts open <code>PN-CO-</code> draft orders.</li>
<li><b>Performance, Training studio, Engineering evidence.</b></li>
<li><b>Replay:</b> a calendar with red dots for failure days and amber dots for co-pilot alert days, a time slider with failure and alert bands drawn on its track, and "‹ Alert / Alert ›" buttons that jump to the previous or next event.</li>
</ul></div>
<div class="card"><h3>Snowflake app (Streamlit in Snowflake, read-only)</h3><ul>
<li>Same five views, reading the <code>PNEUMORA</code> tables through the Snowpark session.</li>
<li>Same replay: event jump list, previous/next alert, day picker with a dotted month calendar, time slider and a day strip.</li>
<li>Status rules live in <code>sis/status_rules.py</code>. A test checks they match the local server at 40 random moments and at every co-pilot alert.</li>
<li>Work orders are a read-only copy; editing happens in the local maintenance system.</li>
</ul></div>
</div>
<div class="plain"><b class="t">Dragging the slider.</b> Every replay moment is re-evaluated from the readings up to that time, so dragging anywhere shows what the dashboard would have said then. To land on an alert without hunting, use the jump buttons or the marked days.</div>
</section>

<section id="why">
<h2>12 · Every status has a reason</h2>
<p>Click the headline or the "Why?" button. Checks run top to bottom, and the first one that fires sets the status:</p>
{table(["Order", "Check", "Fires when", "Status shown", "Source"], [
    ["1", "Existing low-pressure alarm", "Reservoir below 7 bar, or switch on more than 20% of the last 5 min", "Air may run low soon", badge('obs')],
    ["2", "Early air-leak co-pilot", f"Non-stop run above {TRACK['threshold_minutes']:.2f} min held for {TRACK['persistence_minutes']} min (flag in the last 10 min)", "Possible air leak", badge('mod')],
    ["3", "Open work order", "An order opened in the last 3 hours is not done", "Needs attention", badge('syn')],
    ["—", "Air trend", "Shown for context only", "—", badge('der')],
    ["—", "Latest reading", "Shown for context only; gaps mean the train was off", "—", badge('obs')],
])}
<p>"Needs attention" therefore always names the work order, how long ago it opened, and the reason it was opened.</p>
</section>

<section id="snowflake">
<h2>13 · Snowflake deployment</h2>
<div class="card">
<p><b>App:</b> <a href="{APP_URL}">PNEUMORA.APP.PNEUMORA_COPILOT</a>. You need to be signed in to account <code>FMXJOWH-BRC04642</code> with a role that inherits <code>PNEUMORA_ROLE</code> (SYSADMIN and ACCOUNTADMIN do).</p>
<p><b>Objects:</b> role <code>PNEUMORA_ROLE</code>, warehouse <code>PNEUMORA_WH</code> (X-Small, 60 s auto-suspend), database <code>PNEUMORA</code> with schemas CORE, ML, OPS, APP. No SNOWCORE or AXISGUARD references.</p>
<p><b>Runtime:</b> warehouse Streamlit, Streamlit 1.52.2 from <code>sis/environment.yml</code>.</p>
</div>
{table(["Table", "Origin", "Rows", "Columns"], snowflake_rows(), {2})}
<div class="warn"><b class="t">Known quirk.</b> The Streamlit object reports owner ACCOUNTADMIN rather than PNEUMORA_ROLE. Access works; to tidy it, run <code>GRANT OWNERSHIP ON STREAMLIT PNEUMORA.APP.PNEUMORA_COPILOT TO ROLE PNEUMORA_ROLE COPY CURRENT GRANTS</code>.</div>
</section>

<section id="truth">
<h2>14 · Data truth labels</h2>
{table(["Label", "Meaning", "Examples"], [
    [badge('obs'), "Measured by the train", "Pressures, current, oil temperature, load state, low-pressure switch, reported failures"],
    [badge('der'), "Computed from observed data", "Five-minute means, non-stop run length, daily load share, alert outcomes"],
    [badge('mod'), "Output of the frozen detector", "Co-pilot flag and alerts"],
    [badge('syn'), "Made up for the demo, always labelled", "Work orders, technicians, parts, costs, example factory OEE; synthetic leak episodes used only for training"],
])}
</section>

<section id="not">
<h2>15 · What PNEUMORA does NOT do</h2>
<ul>
<li>It is not a promoted prediction model. It failed the false-alert budget.</li>
<li>It does not forecast leaks hours ahead; it detects them about an hour after onset.</li>
<li>It does not detect oil leaks.</li>
<li>It does not diagnose which component failed.</li>
<li>Time-to-low-air is a live pressure projection, not a validated remaining-useful-life model.</li>
<li>Work orders, costs and factory OEE are demonstration records, not this train's real data.</li>
<li>Nine failures cannot give a precise estimate of future precision or transfer to other compressors.</li>
</ul>
</section>

<section id="runbook">
<h2>16 · Runbook and file map</h2>
<pre>cd pneumora
.\\.venv\\Scripts\\python.exe scripts\\build_product.py       # product files + copilot_track.json
.\\.venv\\Scripts\\python.exe -m uvicorn server.main:app --port 8522   # local app
.\\.venv\\Scripts\\python.exe -m pytest -q tests             # 26 tests
.\\.venv\\Scripts\\python.exe scripts\\export_snowflake.py    # data/snowflake/*.csv.gz
cortex exec --file docs/cortex-audit/043-pneumora-deploy-prompt.md -c hackathon --bypass   # deploy
.\\.venv\\Scripts\\python.exe scripts\\build_guide.py          # this page</pre>
{table(["Path", "What it is"], [
    ["<code>autoresearch/official_study.py</code>", "Official-protocol development study and detector families"],
    ["<code>autoresearch/official_freeze.json</code>", "Detector, recipe and gates frozen before external data"],
    ["<code>autoresearch/external_test.py</code>", "One-shot untouched test on 2022 data"],
    ["<code>autoresearch/louo_study.py</code>", "Leave-one-compressor-out cross-validation"],
    ["<code>autoresearch/synthetic_model_study.py</code>", "Synthetic-trained model and wrong-physics control"],
    ["<code>scripts/build_product.py</code>", "Warnings, work orders, co-pilot alerts, track record"],
    ["<code>server/main.py</code>", "Local API, maintenance system, status reasons"],
    ["<code>web/</code>", "Local UI: calendar, replay, Why panel, track record"],
    ["<code>sis/app.py</code>, <code>sis/status_rules.py</code>", "Streamlit-in-Snowflake app"],
    ["<code>sql/00–03</code>", "Snowflake setup, tables, load, app"],
    ["<code>docs/model-card.md</code>", "Model card with every study"],
])}
</section>

<section id="glossary">
<h2>17 · Glossary</h2>
{table(["Term", "Meaning"], [
    ["APU", "Air production unit: compressor, dryer and reservoirs"],
    ["Loaded", "Compressor actively pumping air (<code>COMP == 0</code>)"],
    ["Non-stop run", "How long the compressor has stayed loaded without resting"],
    ["LPS", "The train's low-pressure switch, the existing alarm"],
    ["Caught in time", "An alert between two hours before the reported start and two hours before the reported end"],
    ["Healthy day", "A day outside every reported failure window"],
    ["LOUO", "Leave one unit out: choose on two compressors, score on the third"],
    ["Random-alerter null", "How often alerts placed at random would catch as many failures"],
    ["NO_PROMOTION", "At least one pre-declared gate failed"],
    ["Co-pilot", "Runs beside the existing alarm, opens draft orders for human review, never replaces the alarm"],
])}
<p class="n" style="color:var(--muted)">Generated {datetime.now():%Y-%m-%d %H:%M} by <code>pneumora/scripts/build_guide.py</code> from the frozen study files.</p>
</section>
"""
    links = "".join(f"<a href='#{anchor}'>{e(label)}</a>" for anchor, label in nav)
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>PNEUMORA · early air-leak co-pilot — the A to Z guide</title>
<style>
:root{{--bg:#0a0e14;--panel:#111823;--panel2:#162030;--line:#243044;--text:#dfe7f1;--muted:#8b9bb0;--teal:#2dd4bf;--amber:#f5b942;--red:#f06a6a;--blue:#5aa9ff;--violet:#a78bfa;--mono:'Cascadia Code','Consolas',monospace}}
*{{box-sizing:border-box}} html{{scroll-behavior:smooth}}
body{{margin:0;background:var(--bg);color:var(--text);font:15px/1.6 'Segoe UI',system-ui,sans-serif}}
a{{color:var(--blue)}} code,pre{{font-family:var(--mono)}}
code{{background:#1a2433;padding:1px 5px;border-radius:4px;font-size:.88em;color:#cfe3ff}}
pre{{background:#0d131c;border:1px solid var(--line);border-radius:8px;padding:12px 14px;overflow:auto;font-size:12.5px;color:#cfe3ff}}
.layout{{display:grid;grid-template-columns:260px 1fr;min-height:100vh}}
nav{{position:sticky;top:0;height:100vh;overflow:auto;background:#0c121b;border-right:1px solid var(--line);padding:18px 14px}}
nav .brand{{font-weight:700;letter-spacing:.04em;font-size:13px;color:var(--amber);text-transform:uppercase}}
nav .sub{{color:var(--muted);font-size:12px;margin-bottom:14px}}
nav a{{display:block;color:var(--muted);text-decoration:none;font-size:13px;padding:4px 8px;border-radius:6px}}
nav a:hover{{background:var(--panel2);color:var(--text)}}
main{{padding:28px 44px 80px;max-width:1280px}}
h1{{font-size:30px;margin:0 0 6px}} h2{{font-size:23px;margin:0 0 4px;border-bottom:1px solid var(--line);padding-bottom:8px}}
h3{{font-size:17px;margin:22px 0 8px}} .lede{{color:var(--muted);font-size:16px;max-width:900px}}
section{{padding:34px 0 10px}} .grid{{display:grid;gap:14px}} .g2{{grid-template-columns:repeat(2,minmax(0,1fr))}} .g4{{grid-template-columns:repeat(4,minmax(0,1fr))}}
@media(max-width:1100px){{.g4{{grid-template-columns:repeat(2,minmax(0,1fr))}}.layout{{grid-template-columns:1fr}}nav{{display:none}}}}
.card,.tile{{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 16px}}
.tile .k{{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}} .tile .v{{font-size:26px;font-weight:700}} .tile .n{{font-size:12.5px;color:var(--muted)}}
.plain,.warn,.bad{{padding:10px 14px;border-radius:0 8px 8px 0;margin:10px 0}}
.plain{{border-left:3px solid var(--teal);background:#0f1b1c}} .plain b.t{{color:var(--teal)}}
.warn{{border-left:3px solid var(--amber);background:#1d170b}} .warn b.t{{color:var(--amber)}}
.bad{{border-left:3px solid var(--red);background:#1e1012}} .bad b.t{{color:var(--red)}}
.badge{{display:inline-block;font-size:10.5px;font-weight:700;letter-spacing:.06em;padding:2px 7px;border-radius:999px;margin-right:4px}}
.b-obs{{background:#0f3a33;color:var(--teal)}} .b-der{{background:#10263f;color:var(--blue)}} .b-syn{{background:#3a2a0c;color:var(--amber)}}
.b-cho{{background:#2b1d45;color:var(--violet)}} .b-mod{{background:#3a1518;color:var(--red)}} .b-drop{{background:#2a2f38;color:#aab4c3}}
table{{border-collapse:collapse;width:100%;font-size:13px;margin:8px 0}}
th,td{{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}}
th{{color:var(--muted);font-weight:600;font-size:12px;text-transform:uppercase;background:#0e1520}} .num{{text-align:right}}
.legend-row{{display:flex;flex-wrap:wrap;gap:10px 18px;font-size:13px;color:var(--muted)}}
.timeline{{margin:14px 0 4px 10px;padding-left:22px;border-left:2px solid var(--line)}}
.timeline .ev{{position:relative;margin:0 0 16px}}
.timeline .ev::before{{content:'';position:absolute;left:-30px;top:6px;width:12px;height:12px;border-radius:50%;background:#7c8ba1;border:2px solid var(--bg)}}
.timeline .ev.drop::before{{background:var(--red)}} .timeline .ev.keep::before{{background:var(--teal)}}
svg{{background:var(--panel);border:1px solid var(--line);border-radius:12px;margin:8px 0}}
</style></head>
<body><div class="layout"><nav><div class="brand">PNEUMORA</div><div class="sub">Early air-leak co-pilot · A to Z</div>{links}</nav>
<main>{sections}</main></div></body></html>"""


if __name__ == "__main__":
    OUT.write_text(build(), encoding="utf-8")
    print(OUT, OUT.stat().st_size)

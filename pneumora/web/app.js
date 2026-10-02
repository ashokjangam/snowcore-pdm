const state = {
  page: "now",
  mode: "simple",
  at: "2020-06-06T20:30",
  range: null,
  boot: null,
  maintTab: "board",
  query: "",
  palette: false,
  composer: false,
  toast: "",
  selected: null,
  why: false,
  calMonth: null,
  focus: "F04",
};

const titles = {
  now: "What needs attention",
  copilot: "Leak alerts vs real failures",
  work: "Maintenance",
  performance: "Compressor performance",
  training: "Training studio",
  evidence: "Engineering evidence",
};

const $ = (selector) => document.querySelector(selector);
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[char]));

async function api(path, options) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

function clock(value) {
  const date = new Date(value);
  return date.toLocaleString("en-GB", {
    day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit",
  });
}

function lineChart(series, key, color, auto = false) {
  if (!series.length) return "<p class='muted'>No readings in this window.</p>";
  const values = series.map((row) => row[key]);
  const min = auto ? Math.min(...values) : Math.min(6.5, ...values);
  const max = auto ? Math.max(...values) : Math.max(10.2, ...values);
  const span = Math.max(max - min, 0.001);
  const width = 760;
  const height = 240;
  const x = (index) => 36 + (index * (width - 52)) / Math.max(series.length - 1, 1);
  const y = (value) => 18 + (max - value) * (height - 42) / span;
  const path = values.map((value, index) => `${index ? "L" : "M"}${x(index).toFixed(1)},${y(value).toFixed(1)}`).join(" ");
  const low = y(7);
  return `<svg class="chart" viewBox="0 0 ${width} ${height}" role="img">
    ${auto ? "" : `<line x1="36" y1="${low}" x2="${width - 16}" y2="${low}" stroke="#c56b3c" stroke-dasharray="4 4"/><text x="40" y="${Math.max(14, low - 6)}" fill="#c56b3c" font-size="11">Low-air point</text>`}
    <path d="${path}" fill="none" stroke="${color}" stroke-width="3" stroke-linejoin="round"/>
  </svg>`;
}

function bars(rows, label, value, max) {
  const scale = max || Math.max(...rows.map(value), 0.001);
  return `<div class="bars">${rows.map((row) => `
    <div class="bar-row"><span>${esc(label(row))}</span><div class="track"><span style="width:${Math.min(100, Math.abs(value(row)) / scale * 100)}%"></span></div><b>${value(row).toFixed(2)}</b></div>
  `).join("")}</div>`;
}

function shell() {
  const page = state.page;
  $("#app").innerHTML = `
    <aside class="rail">
      <a class="brand" href="#now"><img src="/assets/pneumora-logo-reversed.svg" alt="PNEUMORA"></a>
      <div class="asset-pill">${esc(state.boot.asset.id)} · ${esc(state.boot.asset.place)}</div>
      <nav>
        ${["now", "copilot", "work", "performance", "training", "evidence"].map((name) => `
          <button class="nav-btn ${page === name ? "active" : ""}" data-page="${name}">
            ${titles[name]}
            ${name === "work" ? `<small>${state.boot.open_orders}</small>` : ""}
          </button>`).join("")}
      </nav>
      ${replayPanel()}
    </aside>
    <main class="stage">
      <header class="top">
        <div class="mark"><img src="/assets/pneumora-icon.svg" alt=""><div><div class="kicker">Compressor intelligence</div><h1>${titles[page]}</h1></div></div>
        <div class="tools">
          <div class="seg">
            <button class="${state.mode === "simple" ? "active" : ""}" data-mode="simple">Simple</button>
            <button class="${state.mode === "engineering" ? "active" : ""}" data-mode="engineering">Engineering</button>
          </div>
          <button class="icon-btn" id="search">Search · Ctrl K</button>
        </div>
      </header>
      <section class="content" id="content"></section>
    </main>
    ${state.palette ? palette() : ""}
    ${state.composer ? composer() : ""}
    ${state.toast ? `<div class="toast">${esc(state.toast)}</div>` : ""}`;
  document.querySelectorAll("[data-page]").forEach((button) => button.onclick = () => { state.page = button.dataset.page; render(); });
  document.querySelectorAll("[data-mode]").forEach((button) => button.onclick = () => { state.mode = button.dataset.mode; render(); });
  bindReplay();
  $("#search").onclick = () => { state.palette = true; render(); };
}

const pad = (value) => String(value).padStart(2, "0");
const isoDay = (date) => `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
const toReplay = (text) => {
  const date = new Date(text.replace(" ", "T"));
  date.setMinutes(Math.ceil(date.getMinutes() / 5) * 5, 0, 0);
  return `${isoDay(date)}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
};

function marksOn(day) {
  const start = new Date(`${day}T00:00`);
  const end = new Date(start.getTime() + 86400000);
  return state.boot.marks.filter((mark) => new Date(mark.start.replace(" ", "T")) < end && new Date(mark.end.replace(" ", "T")) >= start);
}

function replayPanel() {
  const month = state.calMonth || state.at.slice(0, 7);
  const [year, monthIndex] = month.split("-").map(Number);
  const first = new Date(year, monthIndex - 1, 1);
  const lead = (first.getDay() + 6) % 7;
  const days = new Date(year, monthIndex, 0).getDate();
  const minDay = state.range.start.slice(0, 10);
  const maxDay = state.range.end.slice(0, 10);
  const cells = [];
  for (let i = 0; i < lead; i += 1) cells.push(`<span></span>`);
  for (let d = 1; d <= days; d += 1) {
    const day = `${month}-${pad(d)}`;
    const kinds = new Set(marksOn(day).map((mark) => mark.kind));
    const disabled = day < minDay || day > maxDay;
    cells.push(`<button class="day ${day === state.at.slice(0, 10) ? "picked" : ""} ${kinds.has("failure") ? "has-failure" : ""} ${kinds.has("copilot") ? "has-copilot" : ""}" data-day="${day}" ${disabled ? "disabled" : ""} title="${[...kinds].map((kind) => kind === "failure" ? "Reported failure" : "Leak detector alert").join(" · ")}">${d}</button>`);
  }
  const today = marksOn(state.at.slice(0, 10));
  const dayStart = new Date(`${state.at.slice(0, 10)}T00:00`).getTime();
  const bands = today.map((mark) => {
    const s = Math.max(0, (new Date(mark.start.replace(" ", "T")).getTime() - dayStart) / 60000);
    const e = Math.min(1440, (new Date(mark.end.replace(" ", "T")).getTime() - dayStart) / 60000 + 5);
    return `<i class="band ${mark.kind}" style="left:${(s / 1440) * 100}%;width:${Math.max(0.8, ((e - s) / 1440) * 100)}%" title="${esc(mark.label)}"></i>`;
  }).join("");
  const label = first.toLocaleString("en-GB", { month: "long", year: "numeric" });
  return `<div class="replay">
    <div class="replay-head"><label>Replay</label>
      <div class="jumps"><button id="prev-alert" title="Jump to the previous alert or failure">‹ Alert</button><button id="next-alert" title="Jump to the next alert or failure">Alert ›</button></div>
    </div>
    <div class="cal">
      <div class="cal-head"><button id="cal-prev" aria-label="Previous month">‹</button><b>${esc(label)}</b><button id="cal-next" aria-label="Next month">›</button></div>
      <div class="cal-grid">${["M", "T", "W", "T", "F", "S", "S"].map((w) => `<em>${w}</em>`).join("")}${cells.join("")}</div>
    </div>
    <div class="day-track">${bands}</div>
    <input id="minute" type="range" min="0" max="1435" step="5" value="${Number(state.at.slice(11, 13)) * 60 + Number(state.at.slice(14, 16))}" aria-label="Time of day">
    <div class="clock">${esc(clock(state.at))}</div>
    <div class="legend"><span><i class="dot failure"></i>Reported failure</span><span><i class="dot copilot"></i>Leak detector alert</span></div>
  </div>`;
}

function bindReplay() {
  document.querySelectorAll("[data-day]").forEach((button) => button.onclick = () => {
    state.at = `${button.dataset.day}T${state.at.slice(11, 16)}`;
    state.calMonth = null;
    render();
  });
  const shiftMonth = (delta) => {
    const [y, m] = (state.calMonth || state.at.slice(0, 7)).split("-").map(Number);
    const next = new Date(y, m - 1 + delta, 1);
    state.calMonth = `${next.getFullYear()}-${pad(next.getMonth() + 1)}`;
    render();
  };
  $("#cal-prev").onclick = () => shiftMonth(-1);
  $("#cal-next").onclick = () => shiftMonth(1);
  const jump = (direction) => {
    const now = state.at.replace("T", " ");
    const starts = state.boot.marks.map((mark) => toReplay(mark.start)).sort();
    const target = direction > 0 ? starts.find((s) => s.replace("T", " ") > now) : [...starts].reverse().find((s) => s.replace("T", " ") < now);
    if (!target) { state.toast = direction > 0 ? "No later alerts in the replay" : "No earlier alerts in the replay"; render(); return; }
    state.at = target;
    state.calMonth = null;
    state.page = "now";
    render();
  };
  $("#prev-alert").onclick = () => jump(-1);
  $("#next-alert").onclick = () => jump(1);
  $("#minute").oninput = (event) => {
    const minutes = Number(event.target.value);
    state.at = `${state.at.slice(0, 10)}T${pad(Math.floor(minutes / 60))}:${pad(minutes % 60)}`;
    $(".clock").textContent = clock(state.at);
  };
  $("#minute").onchange = () => render();
}

function palette() {
  const items = [
    ["now", "Open the live compressor view"],
    ["work", "Open the maintenance board"],
    ["performance", "Open measured performance"],
    ["training", "Open the training studio"],
    ["evidence", "Open engineering evidence"],
  ].filter((item) => item[1].toLowerCase().includes(state.query.toLowerCase()) || titles[item[0]].toLowerCase().includes(state.query.toLowerCase()));
  return `<div class="backdrop" id="close-palette"></div><div class="palette">
    <input id="query" placeholder="Jump to a view" value="${esc(state.query)}">
    ${items.map(([page, label]) => `<button data-jump="${page}">${titles[page]}<div class="muted">${label}</div></button>`).join("")}
  </div>`;
}

function composer() {
  return `<div class="backdrop" id="close-composer"></div><form class="dialog" id="order-form">
    <div class="mark"><img src="/assets/pneumora-icon.svg" alt=""><h2>New work order</h2></div>
    <label class="field"><span>What is happening</span><textarea name="problem" required rows="3"></textarea></label>
    <label class="field"><span>What to check first</span><input name="action" required></label>
    <label class="field"><span>Assign</span><select name="technician" id="techs"></select></label>
    <label class="field"><span>Part</span><select name="part" id="parts"></select></label>
    <label class="field"><span>Priority</span><select name="priority"><option value="planned">Planned</option><option value="urgent">Urgent</option></select></label>
    <div class="row-actions"><button class="btn" type="submit">Create order</button><button class="btn ghost" type="button" id="cancel-order">Cancel</button></div>
  </form>`;
}

async function renderNow() {
  const data = await api(`/api/now?at=${encodeURIComponent(state.at)}`);
  const tone = { ok: "var(--ok)", watch: "var(--copper)", low: "var(--low)" }[data.state];
  const copilot = data.copilot || {};
  const explanation = data.explanation;
  const why = state.why ? `<div class="why-panel" id="why-panel">
      <div class="kicker">Why “${esc(data.title)}”</div>
      <p><b>Decided by:</b> ${esc(data.decided_by)}. Checks run top to bottom; the first one that fires sets the status.</p>
      <table class="table"><thead><tr><th></th><th>Check</th><th>Reading now</th><th>Normal</th><th>Source</th></tr></thead><tbody>
        ${data.reasons.map((r) => `<tr class="${r.triggered ? "fired" : ""}"><td>${r.triggered ? "<span class='chip warn'>Fired</span>" : "<span class='chip'>OK</span>"}</td><td>${esc(r.check)}</td><td>${esc(r.reading)}</td><td class="muted">${esc(r.normal)}</td><td class="muted">${esc(r.source)}</td></tr>`).join("")}
      </tbody></table></div>` : "";
  const copilotChip = copilot.status
    ? `<span class="chip ${copilot.active ? "warn" : ""}" title="Promoted after cross-validation on three compressors. It runs beside the existing alarm and never replaces it.">Early air-leak predictor · ${copilot.active ? "alerting" : "quiet"} · promoted, cross-validated</span>`
    : "";
  $("#content").innerHTML = `
    ${data.model_status === "NO_PROMOTION" && state.mode === "engineering" ? `<div class="notice">No predictive model passed the frozen tests. The existing low-pressure alarm stays the safety signal. ${copilot.evidence ? ` The early air-leak predictor runs beside it: held out by compressor it predicted ${esc(copilot.evidence.air_predicted)} air leaks at least 2 h before the train had to come off, against the alarm's ${esc(copilot.evidence.alarm_air_predicted)}, at ${copilot.evidence.prediction_false_per_day.toFixed(3)} false alerts per healthy day.` : ""}</div>` : ""}
    <article class="hero" style="--tone:${tone}">
      <div>
        <div class="kicker">APU-01</div>
        <h2><button class="why-title" id="why-title" title="Show why this status is showing">${esc(data.title)}</button></h2>
        <p class="lede">${esc(explanation)}</p>
        <div class="action"><b>Next action.</b> ${esc(data.action)}</div>
        <p>${copilotChip} <button class="btn ghost why-btn" id="why-btn" aria-expanded="${state.why}">${state.why ? "Hide reasons" : "Why?"}</button></p>
      </div>
      <div class="estimate">
        <div class="kicker">Time until air is low</div>
        <strong>${esc(data.estimate)}</strong>
        <p>${esc(data.estimate_note)}</p>
        <span class="stamp">Live estimate</span>
      </div>
    </article>
    ${why}
    <div class="grid">
      <article class="card"><h3>Available air</h3>${lineChart(data.series, "reservoirs", "#2f95c4")}</article>
      <article class="card"><h3>Panel pressure</h3>${lineChart(data.series, "tp3", "#1b2327")}</article>
    </div>
    ${state.mode === "engineering" && data.sensors ? `<div class="sensors">
      <div><span>Reservoir</span><b>${data.sensors.reservoirs}</b><span>bar</span></div>
      <div><span>Panel</span><b>${data.sensors.tp3}</b><span>bar</span></div>
      <div><span>Motor</span><b>${data.sensors.current}</b><span>A</span></div>
      <div><span>Oil</span><b>${data.sensors.oil}</b><span>°C</span></div>
      <div><span>Loaded</span><b>${Math.round(data.sensors.loaded * 100)}%</b><span>of interval</span></div>
      ${copilot.status ? `<div><span>Non-stop loaded</span><b>${copilot.loaded_minutes}</b><span>min · leak detector alerts after about 60</span></div>` : ""}
    </div>` : ""}
    ${data.order ? `<article class="ticket">
      <div><header><div><div class="priority">${esc(data.order.priority)} · ${esc(data.order.id)}</div><h3>${esc(data.order.problem)}</h3></div><img src="/assets/pneumora-icon.svg" alt="" width="42"></header>
      <p><b>Check first.</b> ${esc(data.order.action)}</p><p class="muted">${esc(data.order.technician)} · ${esc(data.order.part)} · ${esc(data.order.status)}</p></div>
      <div class="row-actions"><button class="btn copper" data-status="progress" data-id="${data.order.id}">Start work</button><button class="btn ghost" data-status="done" data-id="${data.order.id}">Complete</button></div>
    </article>` : ""}`;
  const toggleWhy = () => { state.why = !state.why; renderNow(); };
  $("#why-title").onclick = toggleWhy;
  $("#why-btn").onclick = toggleWhy;
  bindOrderButtons();
}

function bindOrderButtons() {
  document.querySelectorAll("[data-status]").forEach((button) => {
    button.onclick = async () => {
      await api(`/api/work-orders/${button.dataset.id}`, { method: "PATCH", body: JSON.stringify({ status: button.dataset.status }) });
      state.toast = `Work order ${button.dataset.id} updated`;
      render();
    };
  });
}

async function renderWork() {
  const data = await api("/api/maintenance");
  const columns = [["ready", "Ready"], ["progress", "In progress"], ["parts", "Waiting on parts"], ["done", "Done"]];
  $("#content").innerHTML = `
    <div class="tabs">
      ${["board", "parts", "crew"].map((tab) => `<button class="btn ${state.maintTab === tab ? "" : "ghost"}" data-tab="${tab}">${tab}</button>`).join("")}
      <button class="btn copper" id="new-order">New work order</button>
    </div>
    ${state.maintTab === "board" ? `<div class="board">${columns.map(([status, label]) => `
      <section class="column"><h3>${label}</h3><div class="kanban">${data.orders.filter((order) => order.status === status).map((order) => `
        <article class="${order.priority === "urgent" ? "urgent" : ""}">
          <div class="priority">${esc(order.id)} · ${esc(order.asset)}</div>
          <p>${esc(order.problem)}</p>
          <p class="muted">${esc(order.technician)} · ${esc(order.part)}</p>
          <div class="row-actions">
            ${status !== "progress" ? `<button class="icon-btn" data-status="progress" data-id="${order.id}">Start</button>` : ""}
            ${status !== "parts" ? `<button class="icon-btn" data-status="parts" data-id="${order.id}">Parts</button>` : ""}
            ${status !== "done" ? `<button class="icon-btn" data-status="done" data-id="${order.id}">Done</button>` : ""}
          </div>
        </article>`).join("")}</div></section>`).join("")}</div>` : ""}
    ${state.maintTab === "parts" ? `<article class="card"><table class="table"><thead><tr><th>Part</th><th>Stock</th><th>Reorder</th><th>Example cost</th><th></th></tr></thead><tbody>
      ${data.parts.map((part) => `<tr><td>${esc(part.name)}<div class="muted">${esc(part.sku)}</div></td><td class="${part.stock <= part.reorder_at ? "low-stock" : ""}">${part.stock}</td><td>${part.reorder_at}</td><td>€${part.cost_eur}</td><td><button class="icon-btn" data-part="${part.sku}" data-delta="-1">Use</button> <button class="icon-btn" data-part="${part.sku}" data-delta="1">Receive</button></td></tr>`).join("")}
    </tbody></table><p class="muted">Costs are example values used by this maintenance system.</p></article>` : ""}
    ${state.maintTab === "crew" ? `<div class="grid">${data.technicians.map((person) => `<article class="card"><div class="kicker">${esc(person.shift)}</div><h3>${esc(person.name)}</h3><p>${esc(person.role)}</p><p class="muted">${data.orders.filter((order) => order.technician === person.name && order.status !== "done").length} open orders</p></article>`).join("")}</div>` : ""}`;
  document.querySelectorAll("[data-tab]").forEach((button) => button.onclick = () => { state.maintTab = button.dataset.tab; render(); });
  $("#new-order").onclick = async () => { state.composer = true; await render(); fillComposer(data); };
  bindOrderButtons();
  document.querySelectorAll("[data-part]").forEach((button) => button.onclick = async () => {
    await api(`/api/parts/${button.dataset.part}/adjust`, { method: "POST", body: JSON.stringify({ delta: Number(button.dataset.delta) }) });
    state.toast = "Stock updated";
    render();
  });
}

function fillComposer(data) {
  const form = $("#order-form");
  if (!form) return;
  $("#techs").innerHTML = data.technicians.map((person) => `<option>${esc(person.name)}</option>`).join("");
  $("#parts").innerHTML = data.parts.map((part) => `<option>${esc(part.name)}</option>`).join("");
  $("#cancel-order").onclick = () => { state.composer = false; render(); };
  form.onsubmit = async (event) => {
    event.preventDefault();
    const body = Object.fromEntries(new FormData(form));
    const created = await api("/api/work-orders", { method: "POST", body: JSON.stringify(body) });
    state.composer = false;
    state.toast = `${created.id} is ready`;
    state.boot = await api("/api/bootstrap");
    render();
  };
}

async function renderPerformance() {
  const data = await api("/api/performance");
  const latest = data.measured.at(-1) || {};
  const example = data.example_factory.at(-1) || {};
  $("#content").innerHTML = `
    <div class="sensors">
      <div><span>Telemetry coverage</span><b>${Math.round((latest.coverage || 0) * 100)}%</b></div>
      <div><span>Compressor running</span><b>${Math.round((latest.runtime || 0) * 100)}%</b></div>
      <div><span>Loaded</span><b>${Math.round((latest.loaded || 0) * 100)}%</b></div>
      <div><span>Under strain</span><b>${((latest.strain || 0) * 100).toFixed(1)}%</b></div>
    </div>
      <article class="card" style="margin-top:16px"><h3>Measured compressor load</h3>${lineChart(data.measured, "loaded", "#1b2327", true)}<p class="muted">Share of each day the compressor was loaded. Source: observed telemetry.</p></article>
    <article class="card example"><div class="stamp">Example factory score</div><h3>Not this train’s measured output</h3>
      <div class="sensors"><div><span>Example OEE</span><b>${Math.round((example.oee || 0) * 100)}%</b></div><div><span>Example good units</span><b>${example.good_units || 0}</b></div><div><span>Example downtime cost</span><b>€${example.cost || 0}</b></div></div>
      ${lineChart(data.example_factory.filter((row) => row.oee != null), "oee", "#c56b3c", true)}
    </article>`;
}

async function renderTraining() {
  const data = await api("/api/training");
  const maxHits = 4;
  $("#content").innerHTML = `
    <article class="hero" style="--tone:var(--copper)"><div><div class="kicker">${esc(data.decision.status)}</div><h2>Four observed failures.</h2><p class="lede">${esc(data.target)}</p></div><div class="estimate"><div class="kicker">February windows</div><strong>${data.trained_rows.february_feature_windows.toLocaleString()}</strong><p>Synthetic training rows in the diagnostic refit: ${data.trained_rows.synthetic_training_rows_diagnostic_refit.toLocaleString()}. Calibration and test stayed observed.</p></div></article>
    <div class="grid">
      <article class="card"><h3>Observed episodes warned</h3>${bars(data.arms, (row) => row.name.replaceAll("_", " "), (row) => row.episodes_warned, maxHits)}</article>
      <article class="card"><h3>Signal influence</h3>${bars(data.feature_importance.slice(0, 8), (row) => row.feature.replaceAll("_", " "), (row) => Math.abs(row.importance))}<p class="muted">${esc(data.note)}</p></article>
    </div>`;
}

const when = (text) => text ? clock(text.replace(" ", "T")) : "—";
const ms = (text) => new Date(text.replace(" ", "T")).getTime();
const hours = (minutes) => minutes >= 120 ? `${(minutes / 60).toFixed(1)} h` : `${Math.round(minutes)} min`;
const outcomeChip = {
  caught_in_time: "<span class='chip'>Caught in time</span>",
  too_late: "<span class='chip warn'>Too late</span>",
  no_reported_failure: "<span class='chip warn'>No reported failure</span>",
};

function timeline(track) {
  const width = 1000, left = 190, right = 16;
  const t0 = ms(track.window[0]), t1 = ms(track.window[1]);
  const x = (t) => left + ((ms(t) - t0) / (t1 - t0)) * (width - left - right);
  const lanes = [["Reported failures", 34], ["Leak detector alerts", 84], ["Existing low-pressure alarm", 134]];
  const months = [];
  for (let d = new Date(t0); d.getTime() <= t1; d = new Date(d.getFullYear(), d.getMonth() + 1, 1)) {
    if (d.getTime() >= t0) months.push(d);
  }
  return `<svg class="chart timeline" viewBox="0 0 ${width} 180" role="img" aria-label="Leak detector alerts and alarm against reported failures">
    ${lanes.map(([name, y]) => `<text x="0" y="${y + 4}" font-size="12" fill="#6d645c">${name}</text><line x1="${left}" x2="${width - right}" y1="${y}" y2="${y}" stroke="#e7e1d8"/>`).join("")}
    ${months.map((d) => { const p = left + ((d.getTime() - t0) / (t1 - t0)) * (width - left - right); return `<line x1="${p}" x2="${p}" y1="16" y2="150" stroke="#efeae3"/><text x="${p + 3}" y="170" font-size="11" fill="#6d645c">${d.toLocaleString("en-GB", { month: "short" })}</text>`; }).join("")}
    ${track.failures.map((f) => `<g class="hit" data-focus="${f.id}"><title>${esc(f.id)} · ${esc(f.report)} · ${when(f.start)} to ${when(f.end)}</title>
      <rect x="${x(f.start) - 2}" y="22" width="${Math.max(5, x(f.end) - x(f.start) + 4)}" height="24" rx="4" fill="#8d3424"/>
      <text x="${x(f.start)}" y="16" font-size="11" fill="#8d3424">${esc(f.id)}</text>
      <line x1="${x(f.start)}" x2="${x(f.start)}" y1="46" y2="146" stroke="#8d3424" stroke-dasharray="3 3" opacity=".5"/></g>`).join("")}
    ${track.copilot.map((r) => `<g class="hit" data-replay="${esc(r.raised_at)}"><title>${esc(r.alert_id)} · raised ${when(r.raised_at)} · ${esc(r.outcome.replaceAll("_", " "))}${r.failure_id ? ` (${esc(r.failure_id)})` : ""}</title>
      <circle cx="${x(r.raised_at)}" cy="84" r="7" fill="${r.outcome === "caught_in_time" ? "#c56b3c" : "#fffdf9"}" stroke="#c56b3c" stroke-width="2"/></g>`).join("")}
    ${track.low_pressure_alarm.map((r) => `<g class="hit" data-replay="${esc(r.raised_at)}"><title>Low-pressure alarm · ${when(r.raised_at)} · ${esc(r.outcome.replaceAll("_", " "))}</title>
      <rect x="${x(r.raised_at) - 1}" y="124" width="${r.outcome === "caught_in_time" ? 4 : 2}" height="20" fill="${r.outcome === "caught_in_time" ? "#1b2327" : "#a9a29a"}"/></g>`).join("")}
  </svg>`;
}

function failureZoom(track, f) {
  if (!f.series.length) return "<p class='muted'>No readings around this failure.</p>";
  const width = 1000, height = 300, left = 46, right = 46, top = 20, bottom = 34;
  const t0 = ms(f.series[0].t), t1 = ms(f.series.at(-1).t);
  const x = (t) => left + ((ms(t) - t0) / Math.max(t1 - t0, 1)) * (width - left - right);
  const inside = (t) => t && ms(t) >= t0 && ms(t) <= t1;
  const maxLoaded = Math.max(10, ...f.series.map((p) => p.loaded));
  const yl = (v) => top + (1 - Math.sqrt(Math.max(v, 0) / maxLoaded)) * (height - top - bottom);
  const loadTicks = [2, 10, 30, 60, 120, 240].filter((v) => v <= maxLoaded);
  const pressures = f.series.map((p) => p.reservoirs).filter((v) => v != null);
  const pMin = Math.min(6.5, ...pressures), pMax = Math.max(10, ...pressures);
  const yp = (v) => top + ((pMax - v) / (pMax - pMin)) * (height - top - bottom);
  const area = `M${x(f.series[0].t)},${yl(0)} ` + f.series.map((p) => `L${x(p.t).toFixed(1)},${yl(p.loaded).toFixed(1)}`).join(" ") + ` L${x(f.series.at(-1).t)},${yl(0)} Z`;
  const line = f.series.filter((p) => p.reservoirs != null).map((p, i) => `${i ? "L" : "M"}${x(p.t).toFixed(1)},${yp(p.reservoirs).toFixed(1)}`).join(" ");
  const fs = Math.max(t0, ms(f.start)), fe = Math.min(t1, ms(f.end));
  const xs = left + ((fs - t0) / (t1 - t0)) * (width - left - right), xe = left + ((fe - t0) / (t1 - t0)) * (width - left - right);
  const marker = (t, color, label, dash, row) => inside(t)
    ? `<line x1="${x(t)}" x2="${x(t)}" y1="${top}" y2="${height - bottom}" stroke="${color}" stroke-width="2" ${dash ? 'stroke-dasharray="5 4"' : ""}/><text x="${x(t) + 4}" y="${top + 12 + row * 14}" font-size="11" fill="${color}">${label}</text>`
    : "";
  const ticks = [];
  for (let k = 0; k <= 6; k += 1) {
    const t = t0 + ((t1 - t0) * k) / 6;
    const px = left + ((t - t0) / (t1 - t0)) * (width - left - right);
    ticks.push(`<text x="${px}" y="${height - 12}" font-size="11" fill="#6d645c" text-anchor="middle">${clock(new Date(t))}</text>`);
  }
  return `<svg class="chart zoom" viewBox="0 0 ${width} ${height}" role="img" aria-label="Compressor non-stop run length and air pressure around ${esc(f.id)}">
    <rect x="${xs}" y="${top}" width="${Math.max(2, xe - xs)}" height="${height - top - bottom}" fill="#8d3424" opacity=".07"/>
    ${inside(f.copilot_first) ? (() => {
      const xa = x(f.copilot_first), xb = Math.max(left, xa - (track.persistence_minutes * 60000 / Math.max(t1 - t0, 1)) * (width - left - right));
      return `<rect x="${xb}" y="${top}" width="${Math.max(2, xa - xb)}" height="${height - top - bottom}" fill="#c56b3c" opacity=".18"/><text x="${(xa + xb) / 2}" y="${height - bottom - 6}" font-size="11" fill="#c56b3c" text-anchor="middle">${track.persistence_minutes}-min check</text>`;
    })() : ""}
    <path d="${area}" fill="#c56b3c" opacity=".22" stroke="#c56b3c" stroke-width="1.5"/>
    <line x1="${left}" x2="${width - right}" y1="${yl(track.threshold_minutes)}" y2="${yl(track.threshold_minutes)}" stroke="#c56b3c" stroke-dasharray="2 3"/>
    <path d="${line}" fill="none" stroke="#2f95c4" stroke-width="2.5"/>
    <line x1="${left}" x2="${width - right}" y1="${yp(7)}" y2="${yp(7)}" stroke="#2f95c4" stroke-dasharray="4 4" opacity=".6"/>
    <text x="${width - right - 4}" y="${yp(7) - 5}" font-size="11" fill="#2f95c4" text-anchor="end">7 bar low-air point</text>
    <text x="${left + 4}" y="${yl(track.threshold_minutes) - 5}" font-size="11" fill="#c56b3c">${track.threshold_minutes.toFixed(2)} min line</text>
    <text x="4" y="${top - 6}" font-size="11" fill="#c56b3c">min</text><text x="${width - 30}" y="${top - 6}" font-size="11" fill="#2f95c4">bar</text>
    ${loadTicks.map((v) => `<text x="4" y="${yl(v) + 4}" font-size="11" fill="#c56b3c">${v}</text>`).join("")}
    ${[7, 8, 9, 10].filter((v) => v >= pMin && v <= pMax).map((v) => `<text x="${width - 30}" y="${yp(v) + 4}" font-size="11" fill="#2f95c4">${v}</text>`).join("")}
    ${marker(f.start, "#8d3424", f.onset_precision === "day" ? "Log: day of failure (no time given)" : "Log: leak starts", false, 0)}
    ${marker(f.copilot_first, "#c56b3c", "Leak detector alert", false, 1)}
    ${marker(f.lps_first, "#1b2327", "Low-pressure alarm", false, 2)}
    ${marker(f.removal_deadline, "#1b2327", "Last moment to act (2 h before removal)", true, 3)}
    ${ticks.join("")}
  </svg>`;
}

function failureStory(f, track) {
  const onset = f.onset_precision === "day" ? "the start of the logged day (the log gives only the date)" : "the logged start of the leak";
  const co = f.copilot_first == null
    ? "The leak detector did not alert in time."
    : f.onset_precision === "day"
      ? `The leak detector alerted at ${when(f.copilot_first)}, ${hours(f.copilot_minutes_after_start)} into the logged day. The log has no start time, so we cannot say whether this was before or after the leak began. That left ${hours(f.copilot_minutes_before_end - 120)} to act before the train had to come off.`
    : f.copilot_minutes_after_start < 0
      ? `The leak detector alerted at ${when(f.copilot_first)}, ${hours(-f.copilot_minutes_after_start)} <b>before</b> ${onset}, so here it did warn ahead. That left ${hours(f.copilot_minutes_before_end - 120)} to act before the train had to come off.`
      : `The leak detector alerted at ${when(f.copilot_first)}, ${hours(f.copilot_minutes_after_start)} <b>after</b> ${onset}, so here it confirmed a leak already under way rather than predicting it. That left ${hours(f.copilot_minutes_before_end - 120)} to act before the train had to come off.`;
  const lps = f.lps_first == null
    ? "The existing low-pressure alarm did not fire in time."
    : `The existing low-pressure alarm fired at ${when(f.lps_first)}, ${hours(f.lps_minutes_after_start)} after the logged start.`;
  let signal = "";
  if (f.copilot_first) {
    const alertAt = ms(f.copilot_first);
    const hour = f.series.filter((p) => ms(p.t) <= alertAt && ms(p.t) > alertAt - track.persistence_minutes * 60000).map((p) => p.loaded);
    if (hour.length) signal = ` Why it waited: it needs every 5-minute reading for ${track.persistence_minutes} minutes to show a run longer than the line. In that hour the shortest reading was ${Math.min(...hour).toFixed(1)} min, so the compressor never got a normal rest.`;
  }
  return `<p><b>${esc(f.id)} · ${esc(f.report)}.</b> ${when(f.start)} to ${when(f.end)}. ${co}${signal} ${lps}</p>`;
}

async function renderCopilot() {
  const track = await api("/api/copilot");
  const caught = track.failures.filter((f) => f.copilot_first != null);
  const lead = caught.map((f) => f.copilot_minutes_before_end - 120);
  const after = caught.filter((f) => f.onset_precision !== "day" && f.copilot_minutes_after_start >= 0).map((f) => f.copilot_minutes_after_start);
  const before = caught.filter((f) => f.copilot_minutes_after_start < 0).map((f) => -f.copilot_minutes_after_start);
  const focus = track.failures.find((f) => f.id === state.focus) || track.failures[0];
  const e = track.evidence;
  $("#content").innerHTML = `
    <article class="hero" style="--tone:var(--copper)">
      <div><div class="kicker">${esc(track.status.replaceAll("_", " "))}</div>
        <h2>It confirms a leak early. It does not predict one.</h2>
        <p class="lede">A healthy compressor works for about two minutes, rests, and repeats. With an air leak it can never fill the tanks, so it stops resting. The leak detector alerts when every 5-minute reading for ${track.persistence_minutes} minutes in a row shows a run longer than ${track.threshold_minutes.toFixed(2)} minutes. One long reading means nothing, because many normal readings are above that line. A full hour without a normal rest is the signal, which is why the alert always comes at least ${track.persistence_minutes} minutes after the compressor stops resting.</p>
        <div class="action"><b>What it gives the crew.</b> On the ${caught.length} reported leaks it caught, it alerted ${after.length ? `<b>after</b> the logged start on ${after.length} (${hours(Math.min(...after))} to ${hours(Math.max(...after))} after)` : ""}${before.length ? `, and once ${hours(Math.max(...before))} before the reported onset` : ""}, leaving at least ${hours(Math.min(...lead))} to inspect before the train must come off service.</div>
      </div>
      <div class="estimate">
        <div class="kicker">Reported failures caught in time</div>
        <strong>${track.tally.copilot.caught_in_time} of ${track.tally.failures}</strong>
        <p>Existing low-pressure alarm: <b>${track.tally.low_pressure_alarm.caught_in_time} of ${track.tally.failures}</b>.</p>
        <p class="muted">Alerts with no reported failure: leak detector ${track.tally.copilot.no_reported_failure} of ${track.tally.copilot.alerts}; alarm ${track.tally.low_pressure_alarm.no_reported_failure} of ${track.tally.low_pressure_alarm.alerts}.</p>
      </div>
    </article>
    <article class="card" style="margin-top:16px"><h3>Every alert against the maintenance log · ${when(track.window[0])} to ${when(track.window[1])}</h3>
      ${timeline(track)}
      <p class="muted">Filled circle: leak detector alert that landed on a reported failure in time. Hollow circle: alert with no reported failure. Click a failure to zoom in, or an alert to replay that moment.</p>
    </article>
    <article class="card" style="margin-top:16px">
      <div class="tabs">${track.failures.map((f) => `<button class="btn ${f.id === focus.id ? "" : "ghost"}" data-focus="${f.id}">${esc(f.id)}</button>`).join("")}
        <button class="btn copper" data-replay="${esc(focus.copilot_first || focus.start)}">Replay this moment</button></div>
      <h3>Zoom into ${esc(focus.id)}: what the compressor did, and when each alert fired</h3>
      ${failureZoom(track, focus)}
      <p class="legend dark"><span><i class="dot copilot"></i>Non-stop run length (minutes, square-root scale so short runs stay visible)</span><span><i class="dot blue"></i>Reservoir pressure (bar)</span><span><i class="dot failure"></i>Reported failure period</span></p>
      ${failureStory(focus, track)}
    </article>
    <article class="card" style="margin-top:16px"><h3>All ${track.copilot.length} leak detector alerts</h3>
      <table class="table"><thead><tr><th>Alert</th><th>Raised</th><th>Cleared</th><th>Longest non-stop run</th><th>Outcome</th><th>Against the failure</th><th></th></tr></thead><tbody>
      ${track.copilot.map((r) => `<tr><td>${esc(r.alert_id)}</td><td>${when(r.raised_at)}</td><td>${when(r.cleared_at)}</td><td>${r.peak_loaded_minutes.toFixed(0)} min</td><td>${outcomeChip[r.outcome]}</td>
        <td>${r.failure_id ? `${esc(r.failure_id)} · ${r.minutes_after_start < 0 ? `${hours(-r.minutes_after_start)} before onset` : `${hours(r.minutes_after_start)} after onset`}` : "<span class='muted'>—</span>"}</td>
        <td><button class="icon-btn" data-replay="${esc(r.raised_at)}">Replay</button></td></tr>`).join("")}
      </tbody></table>
    </article>
    <article class="card" style="margin-top:16px"><h3>Read this before trusting it</h3>
      <p><b>These four failures are the ones the detector was designed on.</b> The track record above shows how it behaves, but it is not independent proof. The honest numbers come from data it never saw. Frozen and tested on two 2022 compressors, it caught ${e.external_air_leaks_caught} of 3 air leaks with ${e.external_false_alerts} false alert. Holding out each compressor in turn, it predicted ${esc(e.air_predicted)} air leaks at least 2 h before the train had to come off, against the alarm's ${esc(e.alarm_air_predicted)}, at ${e.prediction_false_per_day.toFixed(3)} false alerts per healthy day. That passed every pre-declared gate, so it is <b>promoted</b>, with one caveat: the protocol was revised after the first version failed on false alerts.</p>
      <p><b>It is early detection, not a forecast hours ahead.</b> The leaks in this data start abruptly, and no signal we measured rises hours before them.</p>
      <p><b>Alerts with no reported failure are not proven false.</b> Some may be unlogged faults, but we cannot verify that from this data, so they are counted against the leak detector.</p>
      <p class="muted">It runs beside the existing alarm and never replaces it. The work orders it opens are drafts for a person to review.</p>
    </article>`;
  document.querySelectorAll("[data-focus]").forEach((node) => node.onclick = () => { state.focus = node.dataset.focus; renderCopilot(); });
  document.querySelectorAll("[data-replay]").forEach((node) => node.onclick = () => {
    state.at = toReplay(node.dataset.replay);
    state.calMonth = null;
    state.page = "now";
    state.why = true;
    render();
  });
}

function externalCard(study) {
  if (!study) return "";
  const gates = Object.entries(study.gates).map(([name, ok]) => `<span class="chip ${ok ? "" : "warn"}">${ok ? "Pass" : "Fail"} · ${esc(name.replaceAll("_", " "))}</span>`).join(" ");
  return `<article class="card" style="margin-top:16px"><div class="kicker">${esc(study.status)}</div><h3>Official-protocol study with untouched 2022 data</h3>
    <p class="muted">${esc(study.detector)}. Target: ${esc(study.target)}.</p>
    <table class="table"><thead><tr><th>Data</th><th>Who</th><th>Caught in time</th><th>False alerts</th><th>Healthy days</th></tr></thead><tbody>
      ${study.rows.map((row) => `<tr><td>${esc(row.study)}</td><td>${esc(row.who)}</td><td>${esc(row.caught)}</td><td>${row.false_alerts}</td><td>${row.days}</td></tr>`).join("")}
    </tbody></table><p>${gates}</p><p class="muted">${esc(study.reading)}</p>${crossCard(study.cross_validation)}</article>`;
}

function crossCard(study) {
  if (!study) return "";
  const gates = Object.entries(study.gates).map(([name, ok]) => `<span class="chip ${ok ? "" : "warn"}">${ok ? "Pass" : "Fail"} · ${esc(name.replaceAll("_", " "))}</span>`).join(" ");
  return `<h3 style="margin-top:18px">Leave-one-compressor-out, all nine failures · ${esc(study.status)}</h3>
    <table class="table"><thead><tr><th>Who</th><th>Caught in time</th><th>Air leaks</th><th>False alerts</th><th>Per healthy day</th></tr></thead><tbody>
      ${study.rows.map((row) => `<tr><td>${esc(row.who)}</td><td>${esc(row.caught)}</td><td>${row.air} of 7</td><td>${row.false_alerts}</td><td>${row.per_day}</td></tr>`).join("")}
    </tbody></table><p>${gates}</p><p class="muted">The budget is one false alert per seven healthy days (0.143).</p>`;
}

async function renderEvidence() {
  const data = await api("/api/evidence");
  const ranges = Object.entries(data.profile.ranges);
  $("#content").innerHTML = `
    <div class="sensors">
      <div><span>Observed rows</span><b>${data.profile.rows.toLocaleString()}</b></div>
      <div><span>Cadence</span><b>${data.profile.cadence_seconds}s</b></div>
      <div><span>Failures</span><b>4</b></div>
      <div><span>Decision</span><b>${esc(data.decision.status)}</b></div>
    </div>
    <article class="card" style="margin-top:16px"><h3>Measured ranges</h3><table class="table"><thead><tr><th>Signal</th><th>Min</th><th>Median</th><th>Max</th></tr></thead><tbody>
      ${ranges.map(([name, range]) => `<tr><td>${esc(name)}</td><td>${range.min.toFixed(2)}</td><td>${range.median.toFixed(2)}</td><td>${range.max.toFixed(2)}</td></tr>`).join("")}
    </tbody></table><p class="muted">UCI DOI ${esc(data.profile.doi)}</p><p class="muted">${esc(data.profile.sha256)}</p></article>
    ${externalCard(data.external_validation)}
    <article class="card" style="margin-top:16px"><h3>What this product does not claim</h3>${data.limits.map((limit) => `<p>${esc(limit)}</p>`).join("")}</article>`;
}

async function render() {
  shell();
  try {
    if (state.page === "now") await renderNow();
    if (state.page === "copilot") await renderCopilot();
    if (state.page === "work") await renderWork();
    if (state.page === "performance") await renderPerformance();
    if (state.page === "training") await renderTraining();
    if (state.page === "evidence") await renderEvidence();
  } catch (error) {
    $("#content").innerHTML = `<article class="card"><h3>This view could not load</h3><p>${esc(error.message)}</p></article>`;
  }
  const closePalette = $("#close-palette");
  if (closePalette) closePalette.onclick = () => { state.palette = false; render(); };
  document.querySelectorAll("[data-jump]").forEach((button) => button.onclick = () => {
    state.page = button.dataset.jump;
    state.palette = false;
    render();
  });
  const query = $("#query");
  if (query) {
    query.oninput = (event) => { state.query = event.target.value; render(); $("#query").focus(); };
    query.focus();
  }
  if (state.toast) setTimeout(() => { state.toast = ""; const toast = $(".toast"); if (toast) toast.remove(); }, 2200);
}

document.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
    event.preventDefault();
    state.palette = !state.palette;
    render();
  }
  if (event.key === "Escape") {
    state.palette = false;
    state.composer = false;
    render();
  }
});

api("/api/bootstrap").then((boot) => {
  state.boot = boot;
  state.at = boot.replay_default.slice(0, 16);
  state.range = boot.range;
  render();
}).catch((error) => {
  document.body.innerHTML = `<main class="content"><article class="card"><h2>PNEUMORA could not start</h2><p>${esc(error.message)}</p></article></main>`;
});

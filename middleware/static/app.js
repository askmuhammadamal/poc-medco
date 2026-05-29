"use strict";

// Latest value per address keyed by "unit/type/addr". Drives the live grid.
const rows = new Map();
const HISTORY_MAX = 200;
let allowWrites = false;

const $ = (sel) => document.querySelector(sel);
const key = (e) => `${e.unitId}/${e.objectType}/${e.address}`;
const fmtValue = (e) => (e.isBit ? (e.newValue ? "true" : "false") : String(e.newValue));

function ageText(iso) {
  const ms = Date.now() - new Date(iso).getTime();
  if (ms < 0) return "0s";
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  return m < 60 ? `${m}m` : `${Math.floor(m / 60)}h`;
}

// ---- live grid ----
function upsert(e) {
  rows.set(key(e), e);
}

function renderGrid() {
  const tbody = $("#grid tbody");
  const sorted = [...rows.values()].sort((a, b) =>
    a.objectType === b.objectType ? a.address - b.address : a.objectType.localeCompare(b.objectType)
  );
  tbody.innerHTML = sorted
    .map(
      (e) =>
        `<tr><td>${e.modicon}</td><td>${e.objectType}</td><td>${e.address}</td>` +
        `<td>${e.label ?? ""}</td><td class="val">${fmtValue(e)}</td>` +
        `<td class="age" data-ts="${e.timestamp}">${ageText(e.timestamp)}</td></tr>`
    )
    .join("");
  $("#grid-count").textContent = `(${rows.size})`;
}

function tickAges() {
  document.querySelectorAll("#grid .age").forEach((td) => {
    td.textContent = ageText(td.dataset.ts);
  });
}

// ---- history ----
function pushHistory(e) {
  const ul = $("#history");
  const li = document.createElement("li");
  const old = e.oldValue === null || e.oldValue === undefined ? "(init)" : e.oldValue;
  li.textContent = `${new Date(e.timestamp).toLocaleTimeString()}  ${e.modicon} ${e.objectType} ${e.address}: ${old} → ${fmtValue(e)}`;
  ul.prepend(li);
  while (ul.childElementCount > HISTORY_MAX) ul.removeChild(ul.lastChild);
}

// ---- SSE ----
function startStream() {
  const es = new EventSource("/api/stream");
  es.onmessage = (msg) => {
    let e;
    try { e = JSON.parse(msg.data); } catch { return; }
    upsert(e);
    pushHistory(e);
  };
  es.onerror = () => { /* EventSource auto-retries */ };
  // Batch DOM renders to ~4/s instead of per-event.
  setInterval(renderGrid, 250);
  setInterval(tickAges, 1000);
}

// ---- status + config ----
async function loadConfig() {
  try {
    const cfg = await (await fetch("/api/config")).json();
    allowWrites = !!cfg.allowWrites;
    $("#transport").textContent = `transport: ${cfg.transport} ${cfg.tcp ? cfg.tcp.host + ":" + cfg.tcp.port : ""}`;
    applyWriteBanner();
  } catch { /* ignore */ }
}

async function pollHealth() {
  try {
    const h = await (await fetch("/api/health")).json();
    const conn = $("#conn");
    conn.textContent = `connection: ${h.connectionState}`;
    conn.className = "pill " + (h.connectionState === "Connected" ? "pill-ok" : "pill-bad");
    if (typeof h.allowWrites === "boolean" && h.allowWrites !== allowWrites) {
      allowWrites = h.allowWrites;
      applyWriteBanner();
    }
  } catch {
    $("#conn").textContent = "connection: worker unreachable";
    $("#conn").className = "pill pill-bad";
  }
}

function applyWriteBanner() {
  const banner = $("#writes");
  const wb = $("#write-banner");
  const btn = $("#write-btn");
  if (allowWrites) {
    banner.textContent = "writes: ENABLED";
    banner.className = "pill pill-warn";
    wb.textContent = "⚠ Writes ENABLED — submitted values reach the PLC.";
    wb.className = "banner banner-warn";
    btn.disabled = false;
  } else {
    banner.textContent = "writes: disabled";
    banner.className = "pill pill-ok";
    wb.textContent = "Writes are DISABLED. Start the worker with --allow-writes true to enable.";
    wb.className = "banner banner-off";
    btn.disabled = true;
  }
}

// ---- write form ----
async function submitWrite(ev) {
  ev.preventDefault();
  const f = ev.target;
  const result = $("#write-result");
  const body = {
    unitId: Number(f.unitId.value),
    objectType: f.objectType.value,
    address: Number(f.address.value),
    value: Number(f.value.value),
    confirm: f.confirm.checked,
  };
  result.textContent = "sending…";
  result.className = "result";
  try {
    const resp = await fetch("/api/write", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await resp.json().catch(() => ({}));
    if (resp.ok) {
      result.textContent = `OK — wrote ${body.objectType} ${data.modicon ?? body.address} = ${body.value}`;
      result.classList.add("ok");
    } else {
      result.textContent = `HTTP ${resp.status}: ${data.error ?? "failed"}${data.hint ? " — " + data.hint : ""}`;
      result.classList.add("bad");
    }
  } catch (e) {
    result.textContent = `request failed: ${e}`;
    result.classList.add("bad");
  }
}

// ---- discovery ----
async function loadDiscovery() {
  const el = $("#discovery");
  el.textContent = "loading…";
  const resp = await fetch("/api/discovery");
  if (resp.status === 204) {
    el.textContent = "No discovery report yet. Run the worker with --mode=Discover.";
    return;
  }
  const data = await resp.json();
  const s = data.summary || {};
  let html = "";
  if (s.respondingUnits) {
    html += `<p class="disc-summary">Units: ${(s.respondingUnits || []).join(", ")} · ${s.durationMs ?? "?"} ms</p>`;
  }
  for (const ot of data.objectTypes || []) {
    html += `<details><summary>unit ${ot.unitId} · ${ot.objectType} — alive ${ot.aliveCount ?? (ot.alive || []).length}, dead ${ot.deadCount ?? 0}, err ${ot.errorCount ?? 0}</summary>`;
    if ((ot.alive || []).length) {
      html += "<table class='disc'><thead><tr><th>modicon</th><th>addr</th><th>value</th></tr></thead><tbody>";
      html += ot.alive.map((a) => `<tr><td>${a.modicon}</td><td>${a.address}</td><td>${a.value}</td></tr>`).join("");
      html += "</tbody></table>";
    }
    html += "</details>";
  }
  el.innerHTML = html || "<p>Empty report.</p>";
}

// ---- boot ----
async function boot() {
  const snap = await (await fetch("/api/state")).json().catch(() => []);
  for (const e of snap) upsert(e);
  renderGrid();
  startStream();
  await loadConfig();
  pollHealth();
  setInterval(pollHealth, 5000);
  $("#write-form").addEventListener("submit", submitWrite);
  $("#discovery-refresh").addEventListener("click", loadDiscovery);
  loadDiscovery();
}

boot();

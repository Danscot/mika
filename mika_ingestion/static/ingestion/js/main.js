"use strict";

// ═══════════════════════════════════════════════════════════════════════════
//  UTILS
// ═══════════════════════════════════════════════════════════════════════════

function getCsrf() {
  const m = document.cookie.match(/csrftoken=([^;]+)/);
  return m ? m[1] : "";
}

function esc(str) {
  return String(str)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function fmt(n) {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (n >= 1_000)     return (n / 1_000).toFixed(1) + "k";
  return String(n);
}

function fmtDate(ts) {
  if (!ts) return "—";
  const d = new Date(ts * 1000);
  return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" })
    + " " + d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
}

function fmtSize(kb) {
  if (kb >= 1024) return (kb / 1024).toFixed(1) + " MB";
  return kb + " KB";
}

let _toastTimer;
function toast(msg, type = "ok") {
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.className   = "toast show " + type;
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => el.classList.remove("show"), 3000);
}

async function api(method, url, body) {
  const opts = {
    method,
    headers: { "X-CSRFToken": getCsrf() },
  };
  if (body && !(body instanceof FormData)) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  } else if (body) {
    opts.body = body;
  }
  const res = await fetch(url, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

// ═══════════════════════════════════════════════════════════════════════════
//  NAV — sidebar view switching
// ═══════════════════════════════════════════════════════════════════════════

const navItems = document.querySelectorAll(".nav-item");
const views    = document.querySelectorAll(".view");

function switchView(name) {
  navItems.forEach(b => b.classList.toggle("active", b.dataset.view === name));
  views.forEach(v => v.classList.toggle("active", v.id === "view-" + name));

  if (name === "databases") loadDatabases();
  if (name === "bots")      loadBots();
  if (name === "ingest")    loadIndexList();
}

navItems.forEach(btn =>
  btn.addEventListener("click", () => switchView(btn.dataset.view))
);

// ═══════════════════════════════════════════════════════════════════════════
//  DATABASES VIEW
// ═══════════════════════════════════════════════════════════════════════════

let _allDbs     = [];
let _activeBots = [];

async function loadDatabases() {
  try {
    const [dbRes, botRes] = await Promise.all([
      api("GET", "/api/db/stats/"),
      api("GET", "/api/bots/"),
    ]);
    _allDbs     = dbRes.databases   || [];
    _activeBots = botRes.bots       || [];
    renderDatabases();
    updateSidebarStatus();
  } catch (e) {
    toast("Failed to load databases: " + e.message, "err");
  }
}

function botCountForIndex(indexName) {
  return _activeBots.filter(b => b.index_name === indexName).length;
}

function renderDatabases() {
  const grid  = document.getElementById("db-grid");
  const empty = document.getElementById("db-empty");

  // KPIs
  const totalVectors = _allDbs.reduce((s, d) => s + d.vectors, 0);
  const totalChunks  = _allDbs.reduce((s, d) => s + d.chunks, 0);
  const totalSize    = _allDbs.reduce((s, d) => s + d.size_kb, 0);

  document.getElementById("kpi-total-dbs").textContent     = _allDbs.length;
  document.getElementById("kpi-total-vectors").textContent = fmt(totalVectors);
  document.getElementById("kpi-total-chunks").textContent  = fmt(totalChunks);
  document.getElementById("kpi-total-size").textContent    = fmtSize(totalSize);

  // Remove old cards (keep the empty state node)
  grid.querySelectorAll(".db-card").forEach(c => c.remove());

  if (_allDbs.length === 0) {
    empty.style.display = "";
    return;
  }
  empty.style.display = "none";

  _allDbs.forEach(db => {
    const bots        = botCountForIndex(db.name);
    const shownSrcs   = db.sources.slice(0, 3);
    const extraSrcs   = db.sources.length - shownSrcs.length;

    const card = document.createElement("div");
    card.className = "db-card";
    card.innerHTML = `
      <div class="db-card-header">
        <span class="db-card-name">${esc(db.name)}</span>
        <span class="db-card-badge${bots ? " has-bots" : ""}">
          ${bots ? `⎈ ${bots} bot${bots > 1 ? "s" : ""}` : "no bots"}
        </span>
      </div>
      <div class="db-card-meta">
        <div class="db-meta-item">
          <span class="db-meta-val">${fmt(db.vectors)}</span>
          <span class="db-meta-key">Vectors</span>
        </div>
        <div class="db-meta-item">
          <span class="db-meta-val">${fmt(db.chunks)}</span>
          <span class="db-meta-key">Chunks</span>
        </div>
        <div class="db-meta-item">
          <span class="db-meta-val">${fmtSize(db.size_kb)}</span>
          <span class="db-meta-key">Size</span>
        </div>
        <div class="db-meta-item">
          <span class="db-meta-val">${db.sources.length}</span>
          <span class="db-meta-key">Sources</span>
        </div>
      </div>
      ${shownSrcs.length ? `
      <div class="db-card-sources">
        ${shownSrcs.map(s => `<span class="db-source-tag">${esc(s)}</span>`).join("")}
        ${extraSrcs > 0 ? `<span class="db-source-more">+${extraSrcs} more…</span>` : ""}
      </div>` : ""}
      <span class="db-card-updated">Updated ${fmtDate(db.updated_at)}</span>
    `;

    card.addEventListener("click", () => openDbModal(db));
    grid.appendChild(card);
  });
}

document.getElementById("db-refresh-btn").addEventListener("click", loadDatabases);

// ── DB detail modal ────────────────────────────────────────────────────────

let _modalDb = null;

function openDbModal(db) {
  _modalDb = db;
  document.getElementById("db-modal-title").textContent = db.name;

  const bots = botCountForIndex(db.name);
  document.getElementById("db-modal-stats").innerHTML = `
    <div class="db-modal-stat">
      <span class="db-modal-stat-val">${fmt(db.vectors)}</span>
      <span class="db-modal-stat-key">Vectors</span>
    </div>
    <div class="db-modal-stat">
      <span class="db-modal-stat-val">${fmt(db.chunks)}</span>
      <span class="db-modal-stat-key">Chunks</span>
    </div>
    <div class="db-modal-stat">
      <span class="db-modal-stat-val">${fmtSize(db.size_kb)}</span>
      <span class="db-modal-stat-key">Size</span>
    </div>
    <div class="db-modal-stat">
      <span class="db-modal-stat-val">${db.sources.length}</span>
      <span class="db-modal-stat-key">Sources</span>
    </div>
    <div class="db-modal-stat">
      <span class="db-modal-stat-val">${bots}</span>
      <span class="db-modal-stat-key">Bots using</span>
    </div>
    <div class="db-modal-stat">
      <span class="db-modal-stat-val" style="font-size:12px;font-weight:500">${fmtDate(db.updated_at)}</span>
      <span class="db-modal-stat-key">Last updated</span>
    </div>
  `;

  const srcList = document.getElementById("db-modal-sources");
  if (db.sources.length === 0) {
    srcList.innerHTML = `<p class="source-empty">No sources recorded for this index.</p>`;
  } else {
    srcList.innerHTML = db.sources
      .map(s => `<div class="source-item">${esc(s)}</div>`)
      .join("");
  }

  document.getElementById("db-modal").removeAttribute("hidden");
}

function closeDbModal() {
  document.getElementById("db-modal").setAttribute("hidden", "");
  _modalDb = null;
}

document.getElementById("db-modal-close").addEventListener("click",  closeDbModal);
document.getElementById("db-modal-close2").addEventListener("click", closeDbModal);

document.getElementById("db-modal-delete-btn").addEventListener("click", async () => {
  if (!_modalDb) return;
  const bots = botCountForIndex(_modalDb.name);
  const warn = bots
    ? `⚠ ${bots} bot${bots > 1 ? "s are" : " is"} connected to this database.\n\n`
    : "";
  if (!confirm(`${warn}Delete database "${_modalDb.name}"?\nThis cannot be undone.`)) return;

  try {
    await api("POST", `/api/db/${encodeURIComponent(_modalDb.name)}/delete/`);
    toast(`Database "${_modalDb.name}" deleted`, "ok");
    closeDbModal();
    loadDatabases();
  } catch (e) {
    toast("Delete failed: " + e.message, "err");
  }
});

// Close modal on overlay click
document.getElementById("db-modal").addEventListener("click", e => {
  if (e.target === e.currentTarget) closeDbModal();
});

// ═══════════════════════════════════════════════════════════════════════════
//  BOTS VIEW
// ═══════════════════════════════════════════════════════════════════════════

let _allBots  = [];
let _editBotId = null;

async function loadBots() {
  try {
    const [botRes, dbRes] = await Promise.all([
      api("GET", "/api/bots/"),
      api("GET", "/api/db/stats/"),
    ]);
    _allBots = botRes.bots      || [];
    _allDbs  = dbRes.databases  || [];
    renderBots();
    populateBotIndexSelect();
    updateSidebarStatus();
  } catch (e) {
    toast("Failed to load bots: " + e.message, "err");
  }
}

function renderBots() {
  const grid  = document.getElementById("bot-grid");
  const empty = document.getElementById("bot-empty");

  grid.querySelectorAll(".bot-card").forEach(c => c.remove());

  if (_allBots.length === 0) {
    empty.style.display = "";
    return;
  }
  empty.style.display = "none";

  _allBots.forEach(bot => {
    const card    = document.createElement("div");
    card.className = "bot-card";
    const running  = bot.status === "running";

    // Normalise index list (support both legacy index_name and new index_names)
    const indexes  = bot.index_names || (bot.index_name ? [bot.index_name] : ["—"]);

    card.innerHTML = `
      <div class="bot-card-header">
        <span class="bot-card-name">${esc(bot.name)}</span>
        <span class="bot-status-badge ${running ? "running" : "stopped"}" id="badge-config-${esc(bot.id)}">
          ${running ? "● RUNNING" : "○ STOPPED"}
        </span>
      </div>
      <div class="bot-card-detail">
        <div class="bot-detail-row">
          <span class="bot-detail-key">Databases</span>
          <span class="bot-detail-val">
            <div class="bot-indexes">
              ${indexes.map(i => `<span class="bot-index-tag">${esc(i)}</span>`).join("")}
            </div>
          </span>
        </div>
        <div class="bot-detail-row">
          <span class="bot-detail-key">Model</span>
          <span class="bot-detail-val">${esc(bot.model)}</span>
        </div>
        <div class="bot-detail-row">
          <span class="bot-detail-key">Token</span>
          <span class="bot-detail-val">${maskToken(bot.token)}</span>
        </div>
        <div class="bot-detail-row" id="sv-status-row-${esc(bot.id)}">
          <span class="bot-detail-key">Process</span>
          <span class="bot-detail-val"><span class="process-badge" id="sv-badge-${esc(bot.id)}">checking…</span></span>
        </div>
        ${bot.system_prompt ? `
        <div class="bot-detail-row">
          <span class="bot-detail-key">Prompt</span>
          <span class="bot-detail-val">${esc(bot.system_prompt.slice(0, 60))}${bot.system_prompt.length > 60 ? "…" : ""}</span>
        </div>` : ""}
      </div>
      <div class="bot-card-actions">
        <button class="btn-sm" data-action="logs"   data-id="${esc(bot.id)}">⊡ Logs</button>
        <button class="btn-sm accent" data-action="edit" data-id="${esc(bot.id)}">✎ Edit</button>
        <button class="btn-sm" data-action="toggle" data-id="${esc(bot.id)}">
          ${running ? "■ Stop" : "▶ Start"}
        </button>
        <button class="btn-sm danger" data-action="delete" data-id="${esc(bot.id)}">⊘ Delete</button>
      </div>
    `;
    grid.appendChild(card);

    // Fetch real process status in background (don't block render)
    if (running) fetchProcessStatus(bot.id);
  });

  // Wire card action buttons
  grid.querySelectorAll("[data-action]").forEach(btn => {
    btn.addEventListener("click", e => {
      e.stopPropagation();
      const id     = btn.dataset.id;
      const action = btn.dataset.action;
      if (action === "logs")   openLogDrawer(id);
      if (action === "edit")   openBotModal(id);
      if (action === "toggle") toggleBot(id);
      if (action === "delete") deleteBot(id);
    });
  });
}

// Fetch the real supervisor process state and update the badge in-place
async function fetchProcessStatus(botId) {
  try {
    const data = await api("GET", `/api/bots/${botId}/status/`);
    const badge = document.getElementById(`sv-badge-${botId}`);
    if (!badge) return;

    const sv = data.sv_status || "UNKNOWN";
    badge.textContent = sv + (data.uptime ? ` · ${data.uptime}` : "");
    badge.className   = `process-badge ${sv}`;

    // If the process is FATAL/EXITED but bots.json says running, show a warning
    if (["FATAL", "EXITED", "BACKOFF"].includes(sv)) {
      const configBadge = document.getElementById(`badge-config-${botId}`);
      if (configBadge) {
        configBadge.textContent = "⚠ CRASHED";
        configBadge.className   = "bot-status-badge stopped";
      }
    }
  } catch (_) {
    const badge = document.getElementById(`sv-badge-${botId}`);
    if (badge) { badge.textContent = "supervisor unavailable"; badge.className = "process-badge UNKNOWN"; }
  }
}

function maskToken(token) {
  if (!token || token.length < 12) return "••••••••";
  return token.slice(0, 6) + "••••" + token.slice(-4);
}

async function toggleBot(id) {
  const bot    = _allBots.find(b => b.id === id);
  if (!bot) return;
  const newStatus = bot.status === "running" ? "stopped" : "running";
  try {
    await api("POST", `/api/bots/${id}/update/`, { status: newStatus });
    toast(`Bot "${bot.name}" ${newStatus}`, "ok");
    await loadBots();
  } catch (e) {
    toast("Error: " + e.message, "err");
  }
}

async function deleteBot(id) {
  const bot = _allBots.find(b => b.id === id);
  if (!bot) return;
  if (!confirm(`Delete bot "${bot.name}"? This cannot be undone.`)) return;
  try {
    await api("POST", `/api/bots/${id}/delete/`);
    toast(`Bot "${bot.name}" deleted`, "ok");
    await loadBots();
  } catch (e) {
    toast("Error: " + e.message, "err");
  }
}

// ── Bot modal ──────────────────────────────────────────────────────────────

function populateBotIndexSelect(selectedNames = []) {
  const sel = document.getElementById("bot-index");
  sel.innerHTML = _allDbs.length
    ? _allDbs.map(d =>
        `<option value="${esc(d.name)}"
          ${selectedNames.includes(d.name) ? "selected" : ""}>
          ${esc(d.name)} (${fmt(d.vectors)} vectors)
        </option>`
      ).join("")
    : `<option value="" disabled>— no databases yet —</option>`;
}

function openBotModal(editId = null) {
  _editBotId = editId;
  const bot  = editId ? _allBots.find(b => b.id === editId) : null;

  document.getElementById("modal-title").textContent  = bot ? "Edit Bot" : "New Bot";
  document.getElementById("bot-name").value           = bot?.name          || "";
  document.getElementById("bot-token").value          = bot?.token         || "";
  document.getElementById("bot-model").value          = bot?.model         || "gemma-4-31b-it";
  document.getElementById("bot-prompt").value         = bot?.system_prompt || "";

  // Resolve selected indexes (support legacy index_name string)
  const selectedIndexes = bot?.index_names
    || (bot?.index_name ? [bot.index_name] : []);
  populateBotIndexSelect(selectedIndexes);

  document.getElementById("bot-modal").removeAttribute("hidden");
  document.getElementById("bot-name").focus();
}

function closeBotModal() {
  document.getElementById("bot-modal").setAttribute("hidden", "");
  _editBotId = null;
}

document.getElementById("open-bot-modal-btn").addEventListener("click", () => openBotModal());
document.getElementById("modal-close-btn").addEventListener("click",   closeBotModal);
document.getElementById("modal-cancel-btn").addEventListener("click",  closeBotModal);

document.getElementById("bot-modal").addEventListener("click", e => {
  if (e.target === e.currentTarget) closeBotModal();
});

document.getElementById("modal-save-btn").addEventListener("click", async () => {
  const selectedOpts  = [...document.getElementById("bot-index").selectedOptions];
  const selectedIndexes = selectedOpts.map(o => o.value);

  const payload = {
    name:          document.getElementById("bot-name").value.trim(),
    token:         document.getElementById("bot-token").value.trim(),
    index_names:   selectedIndexes,
    model:         document.getElementById("bot-model").value,
    system_prompt: document.getElementById("bot-prompt").value.trim(),
  };

  if (!payload.name)               { toast("Bot name is required", "err"); return; }
  if (!payload.token)              { toast("Telegram token is required", "err"); return; }
  if (!payload.index_names.length) { toast("Select at least one database", "err"); return; }

  try {
    if (_editBotId) {
      await api("POST", `/api/bots/${_editBotId}/update/`, payload);
      toast("Bot updated", "ok");
    } else {
      await api("POST", "/api/bots/create/", payload);
      toast("Bot created", "ok");
    }
    closeBotModal();
    await loadBots();
  } catch (e) {
    toast("Error: " + e.message, "err");
  }
});

// ═══════════════════════════════════════════════════════════════════════════
//  SIDEBAR STATUS
// ═══════════════════════════════════════════════════════════════════════════

function updateSidebarStatus() {
  const dot  = document.getElementById("global-status-dot");
  const text = document.getElementById("global-status-text");

  const totalDBs   = _allDbs.length;
  const runningBot = (_allBots || []).filter(b => b.status === "running").length;

  if (totalDBs === 0) {
    dot.className  = "status-dot warn";
    text.textContent = "No databases";
  } else if (runningBot > 0) {
    dot.className  = "status-dot ok";
    text.textContent = `${runningBot} bot${runningBot > 1 ? "s" : ""} running`;
  } else {
    dot.className  = "status-dot";
    text.textContent = `${totalDBs} db${totalDBs > 1 ? "s" : ""} · no bots`;
  }
}

// ═══════════════════════════════════════════════════════════════════════════
//  INGEST VIEW
// ═══════════════════════════════════════════════════════════════════════════

let activeSource  = "url";
let activeMode    = "new";
let uploadedFile  = null;
let isRunning     = false;
let startTime     = null;
let logText       = [];

const ACCEPTED_EXTENSIONS = [".pdf", ".md", ".markdown", ".docx", ".doc"];

// ── DOM refs ───────────────────────────────────────────────────────────────
const statusPill   = document.getElementById("status-pill");
const runBtn       = document.getElementById("run-btn");
const logBody      = document.getElementById("log-body");
const progressFill = document.getElementById("progress-fill");
const statChunks   = document.getElementById("stat-chunks");
const statVectors  = document.getElementById("stat-vectors");
const statTime     = document.getElementById("stat-time");
const modeHint     = document.getElementById("mode-hint");
const uploadName   = document.getElementById("upload-name");
const pdfInput     = document.getElementById("pdf-file-input");
const uploadZone   = document.getElementById("upload-zone");

// ── Source tabs ────────────────────────────────────────────────────────────
document.querySelectorAll(".tab").forEach(btn => {
  btn.addEventListener("click", () => {
    activeSource = btn.dataset.tab;
    document.querySelectorAll(".tab").forEach(t =>
      t.classList.toggle("active", t === btn)
    );
    document.querySelectorAll(".source-pane").forEach(p =>
      p.classList.toggle("active", p.id === "pane-" + activeSource)
    );
  });
});

// ── Extension chips ────────────────────────────────────────────────────────
document.querySelectorAll(".chip").forEach(chip =>
  chip.addEventListener("click", () => chip.classList.toggle("on"))
);

// ── Mode toggle ────────────────────────────────────────────────────────────
document.getElementById("mode-new").addEventListener("click",    () => setMode("new"));
document.getElementById("mode-append").addEventListener("click", () => setMode("append"));

function setMode(m) {
  activeMode = m;
  document.getElementById("mode-new").classList.toggle("active",    m === "new");
  document.getElementById("mode-append").classList.toggle("active", m === "append");
  modeHint.textContent = m === "new"
    ? "Creates a fresh index — replaces any existing file with this name."
    : "New data is merged into the existing index. Previous knowledge is preserved.";
}

// ── File upload ────────────────────────────────────────────────────────────
function isAccepted(file) {
  const ext = "." + file.name.split(".").pop().toLowerCase();
  return ACCEPTED_EXTENSIONS.includes(ext);
}

function setUploadedFile(file) {
  if (!file) return;
  if (!isAccepted(file)) {
    addLog("Unsupported file type: " + file.name, "err");
    return;
  }
  uploadedFile = file;
  uploadName.textContent = "⊡ " + file.name;
}

pdfInput.setAttribute("accept", ACCEPTED_EXTENSIONS.join(","));
pdfInput.addEventListener("change", () => setUploadedFile(pdfInput.files[0] || null));

uploadZone.addEventListener("dragover",  e => { e.preventDefault(); uploadZone.classList.add("dragover"); });
uploadZone.addEventListener("dragleave", () => uploadZone.classList.remove("dragover"));
uploadZone.addEventListener("drop", e => {
  e.preventDefault();
  uploadZone.classList.remove("dragover");
  setUploadedFile(e.dataTransfer.files[0] || null);
});

// ── Load index list for datalist autocomplete ──────────────────────────────
async function loadIndexList() {
  try {
    const data = await api("GET", "/api/indexes/");
    const dl   = document.getElementById("existing-indexes");
    dl.innerHTML = (data.indexes || [])
      .map(n => `<option value="${esc(n)}">`)
      .join("");
  } catch (_) {}
}

// ── Log helpers ────────────────────────────────────────────────────────────
function ts() { return new Date().toTimeString().slice(0, 8); }

function addLog(msg, level = "info") {
  const line  = document.createElement("div");
  line.className = "log-line";
  line.innerHTML = `<span class="log-ts">${ts()}</span><span class="log-msg ${level}">${esc(msg)}</span>`;
  logBody.appendChild(line);
  logBody.scrollTop = logBody.scrollHeight;
  logText.push(`[${ts()}] ${msg}`);
}

function addSep() {
  const sep = document.createElement("div");
  sep.className = "log-sep";
  logBody.appendChild(sep);
  logBody.scrollTop = logBody.scrollHeight;
}

function setProgress(pct) {
  progressFill.style.width = Math.min(pct, 100) + "%";
}

function setStatus(state) {
  statusPill.className = "status-pill" + (state !== "ready" ? " " + state : "");
  const lbl = { ready: "● READY", running: "● RUNNING", error: "● ERROR" };
  statusPill.textContent = lbl[state] || "● READY";
}

function setRunning(on) {
  isRunning       = on;
  runBtn.disabled = on;
  setStatus(on ? "running" : "ready");
}

function setStats(chunks, vectors, elapsed) {
  statChunks.textContent  = chunks;
  statVectors.textContent = vectors;
  statTime.textContent    = elapsed;
}

// ── Log controls ───────────────────────────────────────────────────────────
document.getElementById("btn-clear").addEventListener("click", () => {
  logBody.innerHTML = "";
  logText = [];
  setProgress(0);
  setStats("—", "—", "—");
  setStatus("ready");
});

document.getElementById("btn-copy").addEventListener("click", () => {
  navigator.clipboard.writeText(logText.join("\n")).catch(() => {});
});

// ── SSE consumer ───────────────────────────────────────────────────────────
function consumeSSE(response) {
  const reader  = response.body.getReader();
  const decoder = new TextDecoder();
  let   buf     = "";

  function handleChunk({ done, value }) {
    if (done) { finishRun(); return; }
    buf += decoder.decode(value, { stream: true });
    const frames = buf.split("\n\n");
    buf = frames.pop();

    for (const frame of frames) {
      const evMatch   = frame.match(/^event: (.+)/m);
      const dataMatch = frame.match(/^data: (.+)/m);
      if (!dataMatch) continue;

      const event = evMatch ? evMatch[1] : "message";
      let   data;
      try { data = JSON.parse(dataMatch[1]); } catch { continue; }
      handleSSEEvent(event, data);
    }

    reader.read().then(handleChunk).catch(err => {
      addLog("Stream error: " + err.message, "err");
      finishRun(true);
    });
  }

  reader.read().then(handleChunk);
}

function handleSSEEvent(event, data) {
  if (event === "log") {
    addLog(data.msg, data.level || "info");
    const prog = { warn: 20, ok: 60 };
    if (data.level in prog) {
      const cur = parseFloat(progressFill.style.width) || 0;
      setProgress(Math.max(cur, prog[data.level]));
    }
  }
  if (event === "done") {
    addSep();
    addLog(`✓ complete — ${data.chunks} chunks · ${data.vectors} vectors`, "bold");
    setProgress(100);
    const elapsed = ((Date.now() - startTime) / 1000).toFixed(1) + "s";
    setStats(data.chunks, data.vectors, elapsed);
    finishRun(false);
    loadIndexList();
    // Refresh DB panel in background so stats are current when user switches
    api("GET", "/api/db/stats/").then(r => {
      _allDbs = r.databases || [];
      updateSidebarStatus();
    }).catch(() => {});
  }
  if (event === "error") {
    addSep();
    addLog("✗ " + data.msg, "err");
    finishRun(true);
  }
}

function finishRun(error = false) {
  setRunning(false);
  if (error) setStatus("error");
}

// ── Run ────────────────────────────────────────────────────────────────────
runBtn.addEventListener("click", () => {
  if (isRunning) return;

  const indexName = document.getElementById("index-name").value.trim() || "default";
  const append    = activeMode === "append";

  setRunning(true);
  startTime = Date.now();
  setProgress(0);
  setStats("—", "—", "—");
  addSep();

  if      (activeSource === "url")    runUrl(indexName, append);
  else if (activeSource === "github") runGitHub(indexName, append);
  else if (activeSource === "pdf")    runFile(indexName, append);
});

async function runUrl(indexName, append) {
  const url = document.getElementById("url-input").value.trim();
  if (!url) { addLog("No URL provided.", "err"); finishRun(true); return; }

  addLog(`Ingesting URL → ${url}`, "bold");
  addLog(`Mode: ${append ? "append" : "new index"} · index: ${indexName}`, "info");

  try {
    const res = await fetch("/api/ingest/url/", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": getCsrf() },
      body: JSON.stringify({ url, index_name: indexName, append }),
    });
    if (!res.ok) { const e = await res.json(); addLog(e.error, "err"); finishRun(true); return; }
    consumeSSE(res);
  } catch (err) { addLog(err.message, "err"); finishRun(true); }
}

async function runGitHub(indexName, append) {
  const repoUrl    = document.getElementById("gh-url").value.trim();
  const extensions = [...document.querySelectorAll(".chip.on")].map(c => c.dataset.ext);

  if (!repoUrl) { addLog("No repository URL provided.", "err"); finishRun(true); return; }

  addLog(`Ingesting GitHub → ${repoUrl}`, "bold");
  addLog(`Extensions: ${extensions.join(" ")} · mode: ${append ? "append" : "new"}`, "info");

  try {
    const res = await fetch("/api/ingest/github/", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": getCsrf() },
      body: JSON.stringify({ repo_url: repoUrl, index_name: indexName, append, extensions }),
    });
    if (!res.ok) { const e = await res.json(); addLog(e.error, "err"); finishRun(true); return; }
    consumeSSE(res);
  } catch (err) { addLog(err.message, "err"); finishRun(true); }
}

async function runFile(indexName, append) {
  if (!uploadedFile) {
    addLog("No file selected. Please upload a PDF, Markdown, or DOCX file.", "err");
    finishRun(true);
    return;
  }

  const ext = "." + uploadedFile.name.split(".").pop().toUpperCase();
  addLog(`Ingesting ${ext} → ${uploadedFile.name}`, "bold");
  addLog(`Mode: ${append ? "append" : "new index"} · index: ${indexName}`, "info");

  const form = new FormData();
  form.append("file",       uploadedFile);
  form.append("index_name", indexName);
  form.append("append",     append ? "true" : "false");

  try {
    const res = await fetch("/api/ingest/file/", {
      method: "POST",
      headers: { "X-CSRFToken": getCsrf() },
      body: form,
    });
    if (!res.ok) { const e = await res.json(); addLog(e.error, "err"); finishRun(true); return; }
    consumeSSE(res);
  } catch (err) { addLog(err.message, "err"); finishRun(true); }
}

// ═══════════════════════════════════════════════════════════════════════════
//  KEYBOARD SHORTCUTS
// ═══════════════════════════════════════════════════════════════════════════

document.addEventListener("keydown", e => {
  if (e.key === "Escape") {
    closeBotModal();
    closeDbModal();
  }
  // Ctrl/Cmd + 1/2/3 → switch views
  if ((e.ctrlKey || e.metaKey) && e.key === "1") { e.preventDefault(); switchView("databases"); }
  if ((e.ctrlKey || e.metaKey) && e.key === "2") { e.preventDefault(); switchView("ingest"); }
  if ((e.ctrlKey || e.metaKey) && e.key === "3") { e.preventDefault(); switchView("bots"); }
});

// ═══════════════════════════════════════════════════════════════════════════
//  INIT
// ═══════════════════════════════════════════════════════════════════════════

loadDatabases();
loadIndexList();

// ═══════════════════════════════════════════════════════════════════════════
//  LOG DRAWER
// ═══════════════════════════════════════════════════════════════════════════

let _logBotId      = null;
let _logEventSource = null;
let _logStreaming   = false;
let _logSrc        = "stdout";   // "stdout" | "stderr"
let _logLines      = { stdout: [], stderr: [] };

function openLogDrawer(botId) {
  const bot = _allBots.find(b => b.id === botId);
  if (!bot) return;

  _logBotId    = botId;
  _logStreaming = false;
  _logLines    = { stdout: [], stderr: [] };

  document.getElementById("log-drawer-title").textContent =
    `Logs · ${bot.name}`;
  document.getElementById("log-drawer-body").innerHTML = "";
  document.getElementById("log-process-badge").textContent = "loading…";
  document.getElementById("log-process-badge").className = "process-badge";
  document.getElementById("log-drawer-stream-btn").textContent = "▶ Live";

  // Reset tabs
  document.querySelectorAll(".log-tab").forEach(t =>
    t.classList.toggle("active", t.dataset.src === "stdout")
  );
  _logSrc = "stdout";

  document.getElementById("log-drawer").removeAttribute("hidden");

  // Load status + initial log lines
  loadLogDrawerStatus(botId);
  loadLogLines(botId, false);
}

function closeLogDrawer() {
  stopLogStream();
  document.getElementById("log-drawer").setAttribute("hidden", "");
  _logBotId = null;
}

document.getElementById("log-drawer-close").addEventListener("click", closeLogDrawer);
document.getElementById("log-drawer").addEventListener("click", e => {
  if (e.target === e.currentTarget) closeLogDrawer();
});

// Tab switching
document.querySelectorAll(".log-tab").forEach(tab => {
  tab.addEventListener("click", () => {
    _logSrc = tab.dataset.src;
    document.querySelectorAll(".log-tab").forEach(t =>
      t.classList.toggle("active", t === tab)
    );
    renderLogLines();
  });
});

// Live stream toggle
document.getElementById("log-drawer-stream-btn").addEventListener("click", () => {
  if (_logStreaming) {
    stopLogStream();
    document.getElementById("log-drawer-stream-btn").textContent = "▶ Live";
  } else {
    startLogStream();
    document.getElementById("log-drawer-stream-btn").textContent = "■ Stop";
  }
});

async function loadLogDrawerStatus(botId) {
  try {
    const data  = await api("GET", `/api/bots/${botId}/status/`);
    const sv    = data.sv_status || "UNKNOWN";
    const badge = document.getElementById("log-process-badge");
    const mode  = data.mode === "subprocess" ? "dev" : "prod";
    badge.textContent = `${sv}${data.pid ? ` · pid ${data.pid}` : ""}${data.uptime ? ` · ${data.uptime}` : ""} [${mode}]`;
    badge.className   = `process-badge ${sv}`;

    const meta = document.getElementById("log-drawer-meta");
    meta.innerHTML = `
      <span><strong>mode:</strong> ${esc(data.mode || "unknown")}</span>
      <span><strong>log:</strong> ${esc(data.log_path || "—")}</span>
    `;
  } catch (e) {
    const badge = document.getElementById("log-process-badge");
    badge.textContent = "unavailable";
    badge.className   = "process-badge UNKNOWN";
  }
}

function loadLogLines(botId, streaming) {
  // Close any existing stream
  stopLogStream();

  const url = `/api/bots/${botId}/logs/?lines=80${streaming ? "&stream=1" : ""}`;
  _logEventSource = new EventSource(url);

  _logEventSource.onmessage = e => {
    try {
      const data = JSON.parse(e.data);
      const src  = data.src || "stdout";
      _logLines[src].push(data.line);
      if (_logSrc === src) appendLogLine(data.line, src);
    } catch (_) {}
  };

  _logEventSource.onerror = () => {
    if (!streaming) _logEventSource.close();
  };
}

function startLogStream() {
  _logStreaming = true;
  _logLines = { stdout: [], stderr: [] };
  document.getElementById("log-drawer-body").innerHTML = "";
  loadLogLines(_logBotId, true);
}

function stopLogStream() {
  if (_logEventSource) {
    _logEventSource.close();
    _logEventSource = null;
  }
  _logStreaming = false;
}

function renderLogLines() {
  const body = document.getElementById("log-drawer-body");
  body.innerHTML = "";
  (_logLines[_logSrc] || []).forEach(line => appendLogLine(line, _logSrc));
}

function appendLogLine(line, src) {
  const body = document.getElementById("log-drawer-body");
  const div  = document.createElement("div");
  div.className = "log-line";

  // Detect level from log content
  const lower = line.toLowerCase();
  let level = "info";
  if (lower.includes("[error]") || lower.includes("error") || lower.includes("traceback") || lower.includes("exception")) level = "err";
  else if (lower.includes("[warning]") || lower.includes("warning") || lower.includes("warn")) level = "warn";
  else if (lower.includes("[info]")) level = "info";
  if (src === "stderr") level = "err";

  div.innerHTML = `<span class="log-msg ${level}">${esc(line)}</span>`;
  body.appendChild(div);
  body.scrollTop = body.scrollHeight;
}

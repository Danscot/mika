"use strict";

// ── State ─────────────────────────────────────────────────────────────────────
let activeSource = "url";
let activeMode   = "new";
let uploadedFile = null;   // renamed from pdfFile — now accepts PDF/MD/DOCX
let isRunning    = false;
let startTime    = null;
let logText      = [];

const ACCEPTED_EXTENSIONS = [".pdf", ".md", ".markdown", ".docx", ".doc"];
const ACCEPTED_MIME_TYPES = [
  "application/pdf",
  "text/markdown",
  "text/x-markdown",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "application/msword",
];

// ── DOM refs ──────────────────────────────────────────────────────────────────
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

// ── Source tabs ───────────────────────────────────────────────────────────────
document.querySelectorAll(".tab").forEach(btn => {
  btn.addEventListener("click", () => {
    activeSource = btn.dataset.tab;
    document.querySelectorAll(".tab").forEach(t => {
      t.classList.toggle("active", t === btn);
      t.setAttribute("aria-selected", t === btn ? "true" : "false");
    });
    document.querySelectorAll(".source-pane").forEach(p => {
      p.classList.toggle("active", p.id === `pane-${activeSource}`);
    });
  });
});

// ── Extension chips ───────────────────────────────────────────────────────────
document.querySelectorAll(".chip").forEach(chip => {
  chip.addEventListener("click", () => chip.classList.toggle("on"));
});

// ── Mode toggle ───────────────────────────────────────────────────────────────
document.getElementById("mode-new").addEventListener("click",    () => setMode("new"));
document.getElementById("mode-append").addEventListener("click", () => setMode("append"));

function setMode(m) {
  activeMode = m;
  document.getElementById("mode-new").classList.toggle("active",    m === "new");
  document.getElementById("mode-append").classList.toggle("active", m === "append");
  modeHint.textContent = m === "new"
    ? "Creates a fresh index. Any existing file with this name will be replaced."
    : "New data is merged into the existing index. Previous knowledge is preserved.";
}

// ── File upload (PDF / MD / DOCX) ─────────────────────────────────────────────

function isAcceptedFile(file) {
  const ext = "." + file.name.split(".").pop().toLowerCase();
  return ACCEPTED_EXTENSIONS.includes(ext);
}

function setUploadedFile(file) {
  if (!file) return;
  if (!isAcceptedFile(file)) {
    addLog(`Unsupported file type: ${file.name}. Please upload a PDF, Markdown, or DOCX file.`, "err");
    return;
  }
  uploadedFile = file;
  const ext = "." + file.name.split(".").pop().toUpperCase();
  uploadName.textContent = `⊡ ${file.name}`;
}

// Update the file input to accept all supported types
pdfInput.setAttribute("accept", ACCEPTED_EXTENSIONS.join(","));

pdfInput.addEventListener("change", () => {
  setUploadedFile(pdfInput.files[0] || null);
});

uploadZone.addEventListener("dragover",  e => { e.preventDefault(); uploadZone.classList.add("dragover"); });
uploadZone.addEventListener("dragleave", () => uploadZone.classList.remove("dragover"));
uploadZone.addEventListener("drop", e => {
  e.preventDefault();
  uploadZone.classList.remove("dragover");
  setUploadedFile(e.dataTransfer.files[0] || null);
});

// ── Log helpers ───────────────────────────────────────────────────────────────
function ts() {
  return new Date().toTimeString().slice(0, 8);
}

function addLog(msg, level = "info") {
  const line = document.createElement("div");
  line.className = "log-line";
  line.innerHTML = `<span class="log-ts">${ts()}</span><span class="log-msg ${level}">${escHtml(msg)}</span>`;
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

function escHtml(str) {
  return str.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}

function setProgress(pct) {
  progressFill.style.width = Math.min(pct, 100) + "%";
}

function setStatus(state) {
  statusPill.className = "status-pill" + (state !== "ready" ? " " + state : "");
  const labels = { ready: "● READY", running: "● RUNNING", error: "● ERROR" };
  statusPill.textContent = labels[state] || "● READY";
}

function setStats(chunks, vectors, elapsed) {
  statChunks.textContent  = chunks;
  statVectors.textContent = vectors;
  statTime.textContent    = elapsed;
}

function setRunning(on) {
  isRunning       = on;
  runBtn.disabled = on;
  setStatus(on ? "running" : "ready");
}

// ── Log controls ──────────────────────────────────────────────────────────────
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

// ── Load existing indexes for autocomplete ────────────────────────────────────
async function loadIndexes() {
  try {
    const res  = await fetch("/api/indexes/");
    const data = await res.json();
    const dl   = document.getElementById("existing-indexes");
    dl.innerHTML = data.indexes.map(n => `<option value="${escHtml(n)}"`).join("");
    document.getElementById("index-name").setAttribute("list", "existing-indexes");
  } catch (_) {}
}
loadIndexes();

// ── SSE consumer ──────────────────────────────────────────────────────────────
function consumeSSE(response) {
  const reader  = response.body.getReader();
  const decoder = new TextDecoder();
  let   buf     = "";

  function processChunk({ done, value }) {
    if (done) { finishRun(); return; }
    buf += decoder.decode(value, { stream: true });

    const frames = buf.split("\n\n");
    buf = frames.pop();

    for (const frame of frames) {
      const eventMatch = frame.match(/^event: (.+)/m);
      const dataMatch  = frame.match(/^data: (.+)/m);
      if (!dataMatch) continue;

      const event = eventMatch ? eventMatch[1] : "message";
      let   data;
      try { data = JSON.parse(dataMatch[1]); } catch { continue; }

      handleSSEEvent(event, data);
    }

    reader.read().then(processChunk).catch(err => {
      addLog("Stream error: " + err.message, "err");
      finishRun(true);
    });
  }

  reader.read().then(processChunk);
}

function handleSSEEvent(event, data) {
  if (event === "log") {
    addLog(data.msg, data.level || "info");
    const stageProgress = { warn: 20, ok: 60 };
    if (data.level in stageProgress) {
      const cur = parseFloat(progressFill.style.width) || 0;
      setProgress(Math.max(cur, stageProgress[data.level]));
    }
  }

  if (event === "done") {
    addSep();
    addLog(`✓ complete — ${data.chunks} chunks · ${data.vectors} vectors`, "bold");
    setProgress(100);
    const elapsed = ((Date.now() - startTime) / 1000).toFixed(1) + "s";
    setStats(data.chunks, data.vectors, elapsed);
    finishRun(false);
    loadIndexes();
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

// ── Run ingestion ─────────────────────────────────────────────────────────────
runBtn.addEventListener("click", () => {
  if (isRunning) return;

  const indexName = document.getElementById("index-name").value.trim() || "default";
  const append    = activeMode === "append";

  setRunning(true);
  startTime = Date.now();
  setProgress(0);
  setStats("—", "—", "—");
  addSep();

  if (activeSource === "url")        runUrl(indexName, append);
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
  addLog(`Extensions: ${extensions.join(" ")} · mode: ${append ? "append" : "new index"}`, "info");

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

// Unified file upload handler (PDF + MD + DOCX)
async function runFile(indexName, append) {
  if (!uploadedFile) {
    addLog("No file selected. Please upload a PDF, Markdown, or DOCX file.", "err");
    finishRun(true);
    return;
  }

  const ext = "." + uploadedFile.name.split(".").pop().toUpperCase();
  addLog(`Ingesting ${ext} file → ${uploadedFile.name}`, "bold");
  addLog(`Mode: ${append ? "append" : "new index"} · index: ${indexName}`, "info");

  const form = new FormData();
  form.append("file",        uploadedFile);
  form.append("index_name",  indexName);
  form.append("append",      append ? "true" : "false");

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

// ── CSRF helper ───────────────────────────────────────────────────────────────
function getCsrf() {
  const m = document.cookie.match(/csrftoken=([^;]+)/);
  return m ? m[1] : "";
}

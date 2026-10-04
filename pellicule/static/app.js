const filmEl = document.getElementById("film");
const legendsEl = document.getElementById("legends");
const tokenBarEl = document.getElementById("token-bar");
const sessionListEl = document.getElementById("session-list");

const TIMELINE_LAYERS = [
  "llm",
  "tool_request",
  "policy",
  "exec",
  "case_write",
  "mode",
  "kilo_log",
  "compact",
];

let layerMeta = {};
const policyRows = new Map();
let promptTotal = 0;
let completionTotal = 0;
let contextWindow = null;
let liveReplay = true;

function formatTime(iso) {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  } catch {
    return iso;
  }
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function updateTokenBar() {
  const total = promptTotal + completionTotal;
  const windowLabel = contextWindow ? `${contextWindow} tokens déclarés` : "fenêtre inconnue";
  tokenBarEl.textContent = `Cumul ${total} (${promptTotal} prompt / ${completionTotal} completion) — ${windowLabel}`;
}

function accumulateTokens(ev) {
  if (typeof ev.prompt_tokens === "number") promptTotal += ev.prompt_tokens;
  if (typeof ev.completion_tokens === "number") completionTotal += ev.completion_tokens;
  if (ev.layer === "models" && ev.detail && ev.detail.payload) {
    const data = ev.detail.payload.data;
    if (Array.isArray(data)) {
      for (const item of data) {
        const w = item.context_window || item.max_context_tokens || item.max_model_len;
        if (typeof w === "number" && w > 0) contextWindow = w;
      }
    }
  }
  updateTokenBar();
}

function askBadge(askState) {
  if (!askState) return "";
  const labels = {
    pending: "en attente",
    approved: "approuvé",
    rejected_by_user: "refusé",
  };
  const text = labels[askState] || askState;
  return `<span class="ask-badge ask-${askState}">${escapeHtml(text)}</span>`;
}

function tokenLine(ev) {
  const pt = ev.prompt_tokens;
  const ct = ev.completion_tokens;
  const lat = ev.latency_ms;
  const parts = [];
  if (lat != null) parts.push(`${lat} ms`);
  if (pt != null || ct != null) {
    parts.push(`tokens ${pt ?? "?"} / ${ct ?? "?"}`);
  } else if (ev.layer === "llm") {
    parts.push('<span class="tokens-unknown">tokens inconnus</span>');
  }
  if (ev.model) parts.push(`<code>${escapeHtml(ev.model)}</code>`);
  if (ev.mode_confidence) {
    parts.push(`<span class="mode-confidence-${escapeHtml(ev.mode_confidence)}">${escapeHtml(ev.mode_confidence)}</span>`);
  }
  return parts.join(" · ");
}

function metaForEvent(ev) {
  const d = ev.detail || {};
  if (ev.layer === "tool_request") {
    const tool = d.tool ? `<code>${escapeHtml(d.tool)}</code>` : "";
    const id = ev.tool_call_id ? `<code>${escapeHtml(ev.tool_call_id)}</code>` : "";
    const args =
      d.arguments != null
        ? `<span class="event-args">${escapeHtml(JSON.stringify(d.arguments))}</span>`
        : "";
    const retry =
      d.retry_of && d.retry_index
        ? `<span class="retry-badge">réessai × ${d.retry_index}</span>`
        : "";
    return [retry, tool, id, args].filter(Boolean).join(" · ");
  }
  if (ev.layer === "policy") {
    const rule = d.matched_rule ? `<code>${escapeHtml(d.matched_rule)}</code>` : "";
    const ask = d.verdict === "ask" ? askBadge(d.ask_state) : "";
    const kilo = d.kilo_log ? `<span class="kilo-snippet">${escapeHtml(d.kilo_log)}</span>` : "";
    return [d.verdict, ask, rule, kilo].filter(Boolean).join(" · ");
  }
  if (ev.layer === "exec") {
    const id = ev.tool_call_id ? `<code>${escapeHtml(ev.tool_call_id)}</code>` : "";
    const body = d.body;
    const size = body && body.size_bytes != null ? `${body.size_bytes} o` : "";
    const hash = body && body.sha256 ? body.sha256.slice(0, 12) + "…" : "";
    return [id, size, hash ? `sha ${hash}` : ""].filter(Boolean).join(" · ");
  }
  if (ev.layer === "case_write") {
    const path = d.path ? `<code>${escapeHtml(d.path)}</code>` : "";
    const action = d.action ? escapeHtml(d.action) : "";
    const size = d.size_bytes != null ? `${d.size_bytes} o` : "";
    const note = d.annotation ? `<span class="forbidden-write">${escapeHtml(d.annotation)}</span>` : "";
    return [action, path, size, note].filter(Boolean).join(" · ");
  }
  if (ev.layer === "mode") {
    return [`mode <code>${escapeHtml(d.mode || ev.mode || "")}</code>`, d.source].filter(Boolean).join(" · ");
  }
  if (ev.layer === "kilo_log") {
    return escapeHtml(d.raw || ev.summary || "");
  }
  return tokenLine(ev);
}

function policyDetailHtml(ev) {
  const d = ev.detail || {};
  const lines = [];
  if (d.matched_rule) lines.push(`<dt>Règle gagnante</dt><dd><code>${escapeHtml(d.matched_rule)}</code></dd>`);
  if (d.losers && d.losers.length) {
    lines.push(`<dt>Perdantes</dt><dd><ul>${d.losers.map((l) => `<li><code>${escapeHtml(l)}</code></li>`).join("")}</ul></dd>`);
  }
  if (d.rule_source) lines.push(`<dt>Source</dt><dd><code>${escapeHtml(d.rule_source)}</code></dd>`);
  if (d.config_source) lines.push(`<dt>Config</dt><dd>${escapeHtml(d.config_source)}</dd>`);
  if (d.dialect) lines.push(`<dt>Dialecte</dt><dd>${escapeHtml(d.dialect)}</dd>`);
  if (d.precedence) lines.push(`<dt>Précédence</dt><dd>${escapeHtml(d.precedence)}</dd>`);
  if (d.kilo_log) lines.push(`<dt>Log Kilo</dt><dd><code>${escapeHtml(d.kilo_log)}</code></dd>`);
  if (d.ask_state) lines.push(`<dt>État ask</dt><dd>${escapeHtml(d.ask_state)}</dd>`);
  if (d.annotation) lines.push(`<dt>Note</dt><dd>${escapeHtml(d.annotation)}</dd>`);
  if (d.agree === false) {
    lines.push(`<dt>Accord</dt><dd class="disagree">agree: false</dd>`);
    if (d.hypothesis) lines.push(`<dt>Hypothèse</dt><dd class="disagree">${escapeHtml(d.hypothesis)}</dd>`);
  } else if (d.agree === true && d.kilo_log) {
    lines.push(`<dt>Accord</dt><dd>agree: true</dd>`);
  }
  if (d.retry_burned_completion_tokens) {
    lines.push(`<dt>Tokens brûlés</dt><dd>${d.retry_burned_completion_tokens}</dd>`);
  }
  return `<dl class="policy-detail">${lines.join("")}</dl>`;
}

function applyPolicyRowClasses(row, ev) {
  row.classList.remove(
    "is-policy-deny",
    "is-policy-ask",
    "is-policy-ask-pending",
    "is-policy-ask-approved",
    "is-policy-ask-rejected",
    "is-agree-false",
    "is-retry-policy"
  );
  const d = ev.detail || {};
  const verdict = d.verdict;
  if (verdict === "deny") row.classList.add("is-policy-deny");
  if (verdict === "ask") {
    row.classList.add("is-policy-ask");
    if (d.ask_state === "pending") row.classList.add("is-policy-ask-pending");
    if (d.ask_state === "approved") row.classList.add("is-policy-ask-approved");
    if (d.ask_state === "rejected_by_user") row.classList.add("is-policy-ask-rejected");
  }
  if (d.agree === false) row.classList.add("is-agree-false");
  if (d.retry_of && d.retry_index) row.classList.add("is-retry-policy");
}

function updatePolicyRow(ev) {
  const id = ev.tool_call_id;
  if (!id || !policyRows.has(id)) {
    appendEvent(ev);
    return;
  }
  const row = policyRows.get(id);
  const body = row.querySelector(".event-body");
  if (!body) return;
  const summary = body.querySelector(".event-summary");
  const meta = body.querySelector(".event-meta");
  if (summary) summary.textContent = ev.summary || summary.textContent;
  if (meta) meta.innerHTML = metaForEvent(ev);
  const panel = body.querySelector(".detail-panel");
  if (panel) panel.innerHTML = policyDetailHtml(ev);
  applyPolicyRowClasses(row, ev);
}

function appendEvent(ev) {
  if (
    ev.layer === "policy" &&
    ev.detail &&
    (ev.detail.ask_transition || ev.detail.kilo_reconciliation) &&
    ev.tool_call_id
  ) {
    updatePolicyRow(ev);
    accumulateTokens(ev);
    return;
  }

  if (!TIMELINE_LAYERS.includes(ev.layer)) return;

  const row = document.createElement("article");
  row.className = "event-row";
  if (ev.parent_session_id) {
    row.classList.add("is-nested");
  }
  if (ev.summary && String(ev.summary).includes("error")) {
    row.classList.add("is-error");
  }
  if (ev.layer === "tool_request") {
    row.classList.add("is-tool-request");
    if (ev.detail && ev.detail.retry_of && ev.detail.retry_index) {
      row.classList.add("is-retry");
    }
  }
  if (ev.layer === "exec") {
    row.classList.add("is-exec");
  }
  if (ev.layer === "policy") {
    applyPolicyRowClasses(row, ev);
    if (ev.tool_call_id) policyRows.set(ev.tool_call_id, row);
  }
  if (ev.layer === "case_write") {
    row.classList.add("is-case-write");
    if (ev.detail && ev.detail.annotation) {
      row.classList.add("is-forbidden-write");
    }
  }
  if (ev.layer === "mode") row.classList.add("is-mode");
  if (ev.layer === "kilo_log") row.classList.add("is-kilo-log");

  const time = document.createElement("div");
  time.className = "event-time";
  time.textContent = formatTime(ev.ts);

  const layer = document.createElement("div");
  layer.className = "event-layer";
  layer.textContent = ev.layer;

  const body = document.createElement("div");
  body.className = "event-body";
  const legend = layerMeta[ev.layer];
  if (legend && legend.legend_fr) {
    const leg = document.createElement("div");
    leg.className = "event-legend";
    leg.textContent = legend.legend_fr;
    body.appendChild(leg);
  }
  if (ev.parent_session_id) {
    const parent = document.createElement("div");
    parent.className = "parent-link";
    parent.textContent = `session fille → parent ${ev.parent_session_id}`;
    body.appendChild(parent);
  }

  const summary = document.createElement("div");
  summary.className = "event-summary";
  summary.textContent = ev.summary || "(sans résumé)";

  const meta = document.createElement("div");
  meta.className = "event-meta";
  meta.innerHTML = metaForEvent(ev);

  body.appendChild(summary);
  body.appendChild(meta);

  if (ev.layer === "policy" && ev.detail && (ev.detail.verdict === "deny" || ev.detail.verdict === "ask")) {
    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "detail-toggle";
    toggle.textContent = "Détail";
    const panel = document.createElement("div");
    panel.className = "detail-panel hidden";
    panel.innerHTML = policyDetailHtml(ev);
    toggle.addEventListener("click", () => {
      panel.classList.toggle("hidden");
    });
    body.appendChild(toggle);
    body.appendChild(panel);
  }

  row.appendChild(time);
  row.appendChild(layer);
  row.appendChild(body);
  filmEl.appendChild(row);
  accumulateTokens(ev);
}

function renderLegends() {
  legendsEl.innerHTML = "";
  for (const key of TIMELINE_LAYERS) {
    const block = layerMeta[key];
    if (!block) continue;
    const panel = document.createElement("div");
    panel.className = "legend-panel";
    panel.innerHTML = `<div class="layer-tag">${escapeHtml(key)}</div><p class="legend-text">${escapeHtml(block.legend_fr)}</p>`;
    legendsEl.appendChild(panel);
  }
}

async function loadLegend() {
  const res = await fetch("/api/layers");
  layerMeta = await res.json();
  renderLegends();
}

function resetFilm() {
  filmEl.innerHTML = "";
  policyRows.clear();
  promptTotal = 0;
  completionTotal = 0;
  contextWindow = null;
  updateTokenBar();
}

async function replaySession(sessionId) {
  liveReplay = false;
  const res = await fetch(`/sessions/${encodeURIComponent(sessionId)}`);
  const data = await res.json();
  resetFilm();
  for (const ev of data.events || []) {
    appendEvent(ev);
  }
  if (data.tokens && data.tokens.total != null) {
    promptTotal = data.tokens.prompt_tokens || 0;
    completionTotal = data.tokens.completion_tokens || 0;
    updateTokenBar();
  }
}

async function loadSessions() {
  const res = await fetch("/sessions");
  const data = await res.json();
  sessionListEl.innerHTML = "";
  for (const s of data.sessions || []) {
    const li = document.createElement("li");
    const btn = document.createElement("button");
    const label = s.case_dir ? `${s.session_id.slice(0, 8)}…` : s.session_id.slice(0, 8) + "…";
    btn.textContent = `${label} (${s.event_count || 0})`;
    btn.title = s.session_id;
    btn.addEventListener("click", () => replaySession(s.session_id));
    li.appendChild(btn);
    sessionListEl.appendChild(li);
  }
}

function connect() {
  const es = new EventSource("/events");
  es.onmessage = (msg) => {
    if (!liveReplay) return;
    try {
      const data = JSON.parse(msg.data);
      if (data.type === "connected") return;
      appendEvent(data);
    } catch {
      /* ignore */
    }
  };
  es.onerror = () => {
    es.close();
    setTimeout(connect, 2000);
  };
}

loadLegend();
loadSessions();
updateTokenBar();
connect();

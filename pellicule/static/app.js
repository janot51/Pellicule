const filmEl = document.getElementById("film");
const legendsEl = document.getElementById("legends");
const tokenBarEl = document.getElementById("token-bar");
const trajectoryEl = document.getElementById("trajectory");
const connectionStatusEl = document.getElementById("connection-status");
const liveBtnEl = document.getElementById("live-btn");
const sessionGroupsEl = document.getElementById("session-groups");
const sessionHintEl = document.getElementById("session-hint");
const sessionEmptyEl = document.getElementById("session-empty");
const legendsDrawerEl = document.getElementById("legends-drawer");
const layerFilterChipsEl = document.getElementById("layer-filter-chips");
const layersEnableAllBtn = document.getElementById("layers-enable-all");
const layersDisableAllBtn = document.getElementById("layers-disable-all");
const filmEmptyEl = document.getElementById("film-empty");
const filmEmptyHintEl = document.getElementById("film-empty-hint");
const replayLatestBtn = document.getElementById("replay-latest-btn");
let latestSessionId = null;

const TIMELINE_LAYERS = [
  "llm",
  "tool_request",
  "policy",
  "exec",
  "case_write",
  "mode",
  "kilo_log",
  "compact",
  "click",
  "mcp",
  "skill",
];

let layerMeta = {};
const policyRows = new Map();
const toolRequestRows = new Map();
let execIds = new Set();
let replayComplete = false;
let promptTotal = 0;
let completionTotal = 0;
let contextWindow = null;
/** @type {Record<string, number>} */
let sessionContextParts = {};
let sessionContextMeasuredBytes = 0;
let sessionLlmCallCount = 0;
let liveReplay = true;
const toolCycleEls = new Map();
let currentTurnBlock = null;
let turnIndex = -1;
let turnSegments = [];
let turnAnchorEls = [];
let sseOpen = false;
let activeSessionId = null;

const SEGMENT_TONE_RANK = {
  neutral: 0,
  compact: 1,
  ask: 2,
  retry: 3,
  deny: 4,
  error: 5,
};

const LAYER_FILTER_STORAGE_KEY = "pellicule.disabledLayers";
const THEME_STORAGE_KEY = "pellicule.theme";
let disabledLayers = new Set();

function loadDisabledLayers() {
  disabledLayers = new Set();
  try {
    const raw = localStorage.getItem(LAYER_FILTER_STORAGE_KEY);
    if (!raw) return;
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) {
      for (const name of parsed) {
        if (typeof name === "string" && TIMELINE_LAYERS.includes(name)) {
          disabledLayers.add(name);
        }
      }
    }
  } catch {
    disabledLayers = new Set();
  }
}

function persistDisabledLayers() {
  localStorage.setItem(LAYER_FILTER_STORAGE_KEY, JSON.stringify([...disabledLayers]));
}

function isLayerEnabled(layer) {
  return !disabledLayers.has(layer);
}

function setLayerEnabled(layer, enabled) {
  if (!TIMELINE_LAYERS.includes(layer)) return;
  if (enabled) disabledLayers.delete(layer);
  else disabledLayers.add(layer);
  persistDisabledLayers();
  syncLayerFilterChips();
  applyLayerFilters();
}

function setAllLayersEnabled(enabled) {
  if (enabled) disabledLayers.clear();
  else TIMELINE_LAYERS.forEach((l) => disabledLayers.add(l));
  persistDisabledLayers();
  syncLayerFilterChips();
  applyLayerFilters();
}

function syncLayerFilterChips() {
  if (!layerFilterChipsEl) return;
  layerFilterChipsEl.querySelectorAll(".layer-chip").forEach((btn) => {
    const layer = btn.dataset.layer;
    if (!layer) return;
    const on = isLayerEnabled(layer);
    btn.classList.toggle("is-on", on);
    btn.setAttribute("aria-pressed", on ? "true" : "false");
  });
  if (legendsEl) {
    legendsEl.querySelectorAll(".legend-card").forEach((card) => {
      const layer = card.dataset.layer;
      if (!layer) return;
      card.classList.toggle("is-layer-off", !isLayerEnabled(layer));
    });
  }
}

function renderLayerFilterChips() {
  if (!layerFilterChipsEl) return;
  layerFilterChipsEl.innerHTML = "";
  for (const key of TIMELINE_LAYERS) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "layer-chip" + (isLayerEnabled(key) ? " is-on" : "");
    btn.dataset.layer = key;
    btn.textContent = key;
    btn.setAttribute("aria-pressed", isLayerEnabled(key) ? "true" : "false");
    btn.title = layerMeta[key]?.legend_fr || key;
    btn.addEventListener("click", () => {
      setLayerEnabled(key, !isLayerEnabled(key));
    });
    layerFilterChipsEl.appendChild(btn);
  }
}

function applyLayerFilters() {
  if (!filmEl) return;
  filmEl.querySelectorAll(".event-row").forEach((row) => {
    const layer = row.dataset.layer;
    row.classList.toggle("is-layer-hidden", layer ? !isLayerEnabled(layer) : false);
  });
  filmEl.querySelectorAll(".tool-cycle").forEach((cycle) => {
    const anyVisible = cycle.querySelector(".event-row:not(.is-layer-hidden)");
    cycle.classList.toggle("is-layer-hidden", !anyVisible);
  });
  filmEl.querySelectorAll(".turn-block").forEach((block) => {
    const anyVisible = block.querySelector(".event-row:not(.is-layer-hidden)");
    block.classList.toggle("is-layer-hidden", !anyVisible);
  });
  updateFilmEmptyState();
}

function initLayerFilterControls() {
  loadDisabledLayers();
  if (layersEnableAllBtn) {
    layersEnableAllBtn.addEventListener("click", () => setAllLayersEnabled(true));
  }
  if (layersDisableAllBtn) {
    layersDisableAllBtn.addEventListener("click", () => setAllLayersEnabled(false));
  }
}

const CONTEXT_PART_LABELS = {
  conversation: "conversation",
  skill_body: "corps de skills",
  skill_catalogue: "catalogue de skills",
  agent_prompt: "prompt d'agent",
  command_template: "commande",
  tool_results: "résultats d'outils",
  tool_schemas: "schémas d'outils",
  system_unknown: "system non reconnu",
};

const CONTEXT_PART_ORDER = [
  "conversation",
  "skill_body",
  "skill_catalogue",
  "agent_prompt",
  "command_template",
  "tool_results",
  "tool_schemas",
  "system_unknown",
];

const CONTEXT_PART_COLORS = {
  conversation: "#f97316",
  skill_body: "#eab308",
  skill_catalogue: "#d97706",
  agent_prompt: "#64748b",
  command_template: "#14b8a6",
  tool_results: "#06b6d4",
  tool_schemas: "#a855f7",
  system_unknown: "#94a3b8",
};

const SOURCE_GLOSS = {
  default: "aucune commande /{mode} n'a été lue",
  slash: "la commande /{mode} a été lue dans le message",
  body_exact: "le prompt système recouvre le texte de l'agent",
  body_overlap: "le prompt système recoupe le texte de l'agent",
  kilo_task: "le dossier de tâche Kilo indique ce mode",
  body: "le prompt ne correspond à aucun agent",
  none: "pas de prompt système",
};

const CONFIDENCE_GLOSS = {
  unknown: "pas de preuve forte dans le message",
  likely: "correspondance probable",
  exact: "preuve directe",
  contradicted: "le dossier de tâche et le message ne disent pas le même mode",
};

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

function formatDuration(latencyMs) {
  if (latencyMs == null) return null;
  if (latencyMs >= 1000) {
    const sec = latencyMs / 1000;
    return `${sec.toLocaleString("fr-FR", { minimumFractionDigits: 1, maximumFractionDigits: 1 })} s`;
  }
  return `${latencyMs.toLocaleString("fr-FR")} ms`;
}

function spokenToolName(name) {
  if (!name) return "";
  const idx = name.indexOf("_");
  if (idx > 0) {
    const prefix = name.slice(0, idx);
    if (prefix.includes("-")) return name.slice(idx + 1);
  }
  return name;
}

function salientArgument(ev, args) {
  if (!args || typeof args !== "object") return null;
  if (args.subdir != null && args.subdir !== "") {
    return `sous-dossier ${args.subdir}`;
  }
  const pathKeys = ["path", "file_path", "filepath", "target_file"];
  for (const k of pathKeys) {
    if (args[k] != null && args[k] !== "") {
      return String(args[k]);
    }
  }
  if (args.case_name != null && args.case_name !== "") {
    return String(args.case_name);
  }
  if (args.case_dir != null && ev.case_dir && args.case_dir === ev.case_dir) {
    return null;
  }
  if (args.case_dir != null && args.case_dir !== "") {
    return String(args.case_dir);
  }
  return null;
}

function ruleFileName(ruleSource) {
  if (!ruleSource) return "";
  const parts = String(ruleSource).split(/[/\\]/);
  return parts[parts.length - 1] || ruleSource;
}

function layerLegend(layer) {
  const block = layerMeta[layer];
  return block && block.legend_fr ? block.legend_fr : layer;
}

function formatBytesCompact(bytes) {
  const n = Number(bytes);
  if (!Number.isFinite(n) || n < 0) return "—";
  if (n >= 1_000_000) {
    return `${(n / 1_000_000).toLocaleString("fr-FR", { maximumFractionDigits: 1 })} Mo`;
  }
  if (n >= 1000) {
    return `${(n / 1000).toLocaleString("fr-FR", { maximumFractionDigits: 1 })} ko`;
  }
  return `${n.toLocaleString("fr-FR")} o`;
}

function contextFillSegments(parts) {
  if (!parts) return [];
  const out = [];
  for (const key of CONTEXT_PART_ORDER) {
    if (!Object.prototype.hasOwnProperty.call(parts, key)) continue;
    const value = parts[key];
    if (typeof value !== "number" || value <= 0) continue;
    out.push({
      key,
      value,
      label: CONTEXT_PART_LABELS[key] || key,
      color: CONTEXT_PART_COLORS[key] || "#cbd5e1",
    });
  }
  return out;
}

function measuredBytesFromParts(parts, measuredBytes) {
  if (typeof measuredBytes === "number" && measuredBytes >= 0) return measuredBytes;
  if (!parts) return 0;
  return Object.values(parts).reduce((sum, v) => sum + (typeof v === "number" ? v : 0), 0);
}

function accumulateSessionContextFill(cf) {
  if (!cf || !cf.parts) return;
  sessionLlmCallCount += 1;
  const measured = measuredBytesFromParts(cf.parts, cf.measured_bytes);
  sessionContextMeasuredBytes += measured;
  for (const [key, val] of Object.entries(cf.parts)) {
    if (typeof val === "number") {
      sessionContextParts[key] = (sessionContextParts[key] || 0) + val;
    }
  }
}

function sessionContextFillSnapshot() {
  if (sessionLlmCallCount === 0) return null;
  return {
    unit: "bytes",
    parts: { ...sessionContextParts },
    measured_bytes: sessionContextMeasuredBytes,
    llm_call_count: sessionLlmCallCount,
  };
}

/**
 * @param {object} cf context_fill
 * @param {{ title?: string, compact?: boolean, subtitle?: string }} opts
 */
function contextUsageVisualHtml(cf, opts = {}) {
  if (!cf || !cf.parts) return "";
  const segments = contextFillSegments(cf.parts);
  if (!segments.length) return "";

  const measured = measuredBytesFromParts(cf.parts, cf.measured_bytes);
  const title = opts.title || "Répartition du contexte";
  const compact = opts.compact === true;

  const barInner = segments
    .map((s) => {
      const pct = measured > 0 ? (s.value / measured) * 100 : 0;
      const tip = `${s.label} : ${s.value.toLocaleString("fr-FR")} octets (${pct.toLocaleString("fr-FR", { maximumFractionDigits: 1 })} %)`;
      return `<div class="context-usage-seg" style="width:${pct}%;background:${s.color}" title="${escapeHtml(tip)}"></div>`;
    })
    .join("");

  const legend = segments
    .map((s) => {
      const pct = measured > 0 ? (s.value / measured) * 100 : 0;
      return `<div class="context-usage-legend-item">
  <span class="context-usage-swatch" style="background:${s.color}"></span>
  <span class="context-usage-legend-label">${escapeHtml(s.label)}</span>
  <span class="context-usage-legend-pct">${pct.toLocaleString("fr-FR", { maximumFractionDigits: 0 })} %</span>
  <span class="context-usage-legend-value">${formatBytesCompact(s.value)}</span>
</div>`;
    })
    .join("");

  let footnote = "";
  if (typeof cf.window_tokens === "number") {
    footnote = `<p class="context-usage-note">Fenêtre déclarée : ${cf.window_tokens.toLocaleString("fr-FR")} tokens — Pellicule n'a pas converti les octets en tokens.</p>`;
  } else if (!compact) {
    footnote = `<p class="context-usage-note">Fenêtre non déclarée — barre = parts de ce total en octets, pas un % de la fenêtre modèle.</p>`;
  }

  const subtitle = opts.subtitle ? `<span class="context-usage-sub">${escapeHtml(opts.subtitle)}</span>` : "";

  return `<div class="context-usage${compact ? " context-usage--compact" : ""}">
  <div class="context-usage-head">
    <div class="context-usage-head-left">
      <span class="context-usage-title">${escapeHtml(title)}</span>
      ${subtitle}
    </div>
    <span class="context-usage-total"><strong>${formatBytesCompact(measured)}</strong> octets</span>
  </div>
  <div class="context-usage-bar" role="img" aria-label="${escapeHtml(title)}">${barInner}</div>
  <div class="context-usage-legend">${legend}</div>
  ${footnote}
</div>`;
}

function contextFoldSummaryLabel(cf) {
  const measured = measuredBytesFromParts(cf.parts, cf.measured_bytes);
  return `Contexte · ${formatBytesCompact(measured)}`;
}

function contextUsageMiniBarHtml(cf) {
  if (!cf || !cf.parts) return "";
  const segments = contextFillSegments(cf.parts);
  const measured = measuredBytesFromParts(cf.parts, cf.measured_bytes);
  if (!segments.length) return "";
  const barInner = segments
    .map((s) => {
      const pct = measured > 0 ? (s.value / measured) * 100 : 0;
      const tip = `${s.label} : ${formatBytesCompact(s.value)}`;
      return `<span class="context-mini-seg" style="width:${pct}%;background:${s.color}" title="${escapeHtml(tip)}"></span>`;
    })
    .join("");
  return `<span class="context-mini-bar" role="img" aria-hidden="true">${barInner}</span>`;
}

function contextFoldBodyHtml(cf) {
  if (!cf || !cf.parts) return "";
  const visual = contextUsageVisualHtml(cf, { title: "Répartition de cet appel" });
  const provider = [];
  if (typeof cf.provider_prompt_tokens === "number") {
    let line = `Fournisseur : ${cf.provider_prompt_tokens.toLocaleString("fr-FR")} tokens de prompt`;
    if (cf.provider_prompt_tokens === 0) line += " (chiffre API, pas la somme des octets)";
    provider.push(`<p class="context-usage-provider">${escapeHtml(line)}.</p>`);
  }
  if (typeof cf.provider_completion_tokens === "number") {
    provider.push(
      `<p class="context-usage-provider">Fournisseur : ${cf.provider_completion_tokens.toLocaleString("fr-FR")} tokens de completion.</p>`
    );
  }
  return `${visual}${provider.join("")}`;
}

function buildEventContextPreview(cf) {
  const wrap = document.createElement("button");
  wrap.type = "button";
  wrap.className = "event-context-preview";
  wrap.title = "Ouvrir la répartition du contexte";
  const measured = measuredBytesFromParts(cf.parts, cf.measured_bytes);
  wrap.innerHTML = `${contextUsageMiniBarHtml(cf)}<span class="event-context-bytes">${formatBytesCompact(measured)}</span><span class="event-context-action">répartition</span>`;
  wrap.addEventListener("click", (e) => {
    e.stopPropagation();
    const row = wrap.closest(".event-row");
    if (!row) return;
    if (!row.classList.contains("is-open")) toggleEventRow(row);
    const fold = row.querySelector(".event-fold-context");
    if (fold) fold.open = true;
  });
  return wrap;
}

function updateTokenBar() {
  const total = promptTotal + completionTotal;
  const windowText = contextWindow
    ? contextWindow.toLocaleString("fr-FR")
    : "—";
  let html = `<div class="stats-row">
    <div class="stat"><span class="stat-label">Tokens cumulés</span><span class="stat-value">${total.toLocaleString("fr-FR")}</span></div>
    <div class="stat"><span class="stat-label">Prompt</span><span class="stat-value">${promptTotal.toLocaleString("fr-FR")}</span></div>
    <div class="stat"><span class="stat-label">Completion</span><span class="stat-value">${completionTotal.toLocaleString("fr-FR")}</span></div>
    <div class="stat"><span class="stat-label">Fenêtre modèle</span><span class="stat-value stat-value-sm">${escapeHtml(String(windowText))}</span></div>
  </div>`;
  const sessionCf = sessionContextFillSnapshot();
  if (sessionCf && sessionLlmCallCount > 0) {
    const appelLabel = sessionLlmCallCount === 1 ? "1 appel LLM" : `${sessionLlmCallCount} appels LLM`;
    const summaryLabel = `Contexte session · ${formatBytesCompact(sessionCf.measured_bytes)} · ${appelLabel}`;
    html += `<details class="token-bar-context">
      <summary>${escapeHtml(summaryLabel)}</summary>
      <div class="token-bar-context-body">${contextUsageVisualHtml(sessionCf, {
        title: "Cumul session",
        subtitle: "Somme des octets mesurés à chaque requête",
        compact: true,
      })}</div>
    </details>`;
  }
  tokenBarEl.innerHTML = html;
}

function updateFilmEmptyState() {
  if (!filmEmptyEl) return;
  const hasEvents =
    filmEl && filmEl.querySelectorAll(".event-row:not(.is-layer-hidden)").length > 0;
  filmEmptyEl.hidden = hasEvents;
  filmEl.classList.toggle("has-events", hasEvents);
  const showReplay =
    !hasEvents && liveReplay && latestSessionId && !replayComplete;
  if (filmEmptyHintEl) {
    filmEmptyHintEl.classList.toggle("hidden", !showReplay);
    if (showReplay) {
      filmEmptyHintEl.textContent =
        "Des sessions sont déjà sur le disque : le centre reste vide tant qu’aucun nouvel événement n’arrive en direct.";
    }
  }
  if (replayLatestBtn) {
    replayLatestBtn.classList.toggle("hidden", !showReplay);
  }
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
  if (ev.layer === "llm" && ev.detail && ev.detail.context_fill) {
    accumulateSessionContextFill(ev.detail.context_fill);
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

function askBadgeLabel(askState) {
  const labels = {
    pending: "en attente",
    approved: "approuvé",
    rejected_by_user: "refusé",
  };
  return labels[askState] || askState || "";
}

function shortPhrase(ev, ctx) {
  const d = ev.detail || {};
  const layer = ev.layer;

  if (layer === "mode") {
    const mode = d.mode || ev.mode || "—";
    const source = d.source != null ? d.source : "—";
    return `Mode ${mode}, source ${source}.`;
  }

  if (layer === "llm") {
    const isError =
      (d.error != null && d.error !== "") || (ev.summary && String(ev.summary).includes("error"));
    const inner = [];
    const dur = formatDuration(ev.latency_ms);
    if (dur) inner.push(`en ${dur}`);
    if (ev.completion_tokens != null) inner.push(`${ev.completion_tokens} tokens`);
    if (ev.model) inner.push(ev.model);
    if (isError) {
      return inner.length ? `Erreur de réponse ${inner.join(", ")}.` : "Erreur de réponse.";
    }
    if (inner.length === 0) return "Réponse.";
    let phrase = `Réponse ${inner.join(", ")}.`;
    if (d.context_fill && typeof d.context_fill.measured_bytes === "number") {
      phrase = phrase.replace(/\.$/, "");
      phrase += `, ${d.context_fill.measured_bytes.toLocaleString("fr-FR")} octets mesurés.`;
    }
    return phrase;
  }

  if (layer === "tool_request") {
    const toolRaw = d.tool || "";
    const tool = spokenToolName(toolRaw);
    if (toolRaw === "task" || tool === "task") {
      const agent = d.delegation_agent != null && d.delegation_agent !== "" ? d.delegation_agent : "agent non vu";
      return `Délégation à ${agent}.`;
    }
    let phrase = `Demande ${tool || "—"}`;
    const arg = salientArgument(ev, d.arguments);
    if (arg) phrase += `, ${arg}`;
    phrase += ".";
    if (d.retry_of && d.retry_index) {
      phrase = `Réessai × ${d.retry_index}. ${phrase}`;
    }
    if (replayComplete && ev.tool_call_id && !ctx.execIds.has(ev.tool_call_id)) {
      phrase += " Rien n'a tourné.";
    }
    return phrase;
  }

  if (layer === "policy") {
    const verdict = d.verdict || "—";
    const file = ruleFileName(d.rule_source) || "—";
    let losersPart;
    if (Array.isArray(d.losers)) {
      losersPart = d.losers.length === 0 ? "aucune règle perdante" : `règles perdantes : ${d.losers.join(", ")}`;
    } else {
      losersPart = "perdantes non indiquées";
    }
    let phrase = `Règle ${verdict}, fichier ${file}, ${losersPart}.`;
    if (d.verdict === "ask" && d.ask_state) {
      phrase += ` ${askBadgeLabel(d.ask_state)}.`;
    }
    return phrase;
  }

  if (layer === "exec") {
    const body = d.body || {};
    const size =
      body.size_bytes != null ? `${body.size_bytes.toLocaleString("fr-FR")} octets` : "taille non enregistrée";
    const hash = body.sha256 ? `${body.sha256.slice(0, 12)}…` : "—";
    return `Résultat, ${size}, extrait retenu, empreinte ${hash}.`;
  }

  if (layer === "case_write") {
    const action = d.action || "—";
    const path = d.path || "—";
    const size = d.size_bytes != null ? `${d.size_bytes.toLocaleString("fr-FR")} octets` : "taille non indiquée";
    let phrase = `Dossier d'affaire : ${action} ${path}, ${size}.`;
    if (d.annotation) phrase += ` ${d.annotation}`;
    return phrase;
  }

  if (layer === "kilo_log") {
    return "Ligne Kilo non comprise.";
  }

  if (layer === "compact") {
    if (d.before_count != null && d.after_count != null) {
      const removed = d.before_count - d.after_count;
      return `Contexte résumé : ${d.before_count} messages, puis ${d.after_count}. ${removed} retirés.`;
    }
    return layerLegend("compact");
  }

  if (layer === "skill") {
    const name = d.name || "—";
    const path = d.path || "—";
    return `Skill ${name} chargée, fichier ${path}.`;
  }

  if (layer === "click") {
    const tool = spokenToolName(d.tool || "");
    const choice = d.choice || "allow";
    if (choice === "reject") return `Clic de refus, ${tool}.`;
    if (choice === "allow_once") return `Clic Allow once, ${tool}.`;
    if (choice === "allow_always") return `Clic autorisation permanente, ${tool}.`;
    if (choice === "allow") {
      return `Clic d'autorisation, ${tool}. Le journal ne dit pas si c'était une fois ou pour toujours.`;
    }
    return ev.summary || layer;
  }

  if (layer === "mcp") {
    if (d.method === "tools/list") {
      const n = Array.isArray(d.tools) ? d.tools.length : 0;
      return `Le serveur MCP annonce ${n} outils.`;
    }
    if (d.method === "tools/call" && d.direction === "client") {
      const tool = spokenToolName(d.tool || "");
      const diff = d.argument_diff;
      if (diff && (diff.added?.length || diff.removed?.length || diff.changed?.length)) {
        const parts = [...(diff.added || []), ...(diff.removed || []), ...(diff.changed || [])];
        if (diff.tool_renamed) parts.unshift("nom d'outil");
        return `Kilo a modifié les arguments : ${parts.join(", ")}.`;
      }
      if (d.link === "none" || d.link === "ambiguous") {
        return `Kilo appelle ${tool} sur le serveur MCP. Lien demande : ${d.link === "none" ? "lien non vu" : "lien ambigu"}.`;
      }
      return `Kilo appelle ${tool} sur le serveur MCP.`;
    }
    if (d.body && !d.frame) return "trame tronquée dans le film";
    return ev.summary || layer;
  }

  return ev.summary || "(sans résumé)";
}

function whatHappened(ev, ctx) {
  const d = ev.detail || {};
  const layer = ev.layer;

  if (layer === "mode") {
    const mode = d.mode || ev.mode || "—";
    const source = d.source;
    const confidence = d.confidence || ev.mode_confidence;
    const lines = ["Même échange, autres droits : ce n'est pas un sous-agent."];
    if (source != null) {
      let gloss = SOURCE_GLOSS[source];
      if (gloss) {
        gloss = gloss.replace(/\{mode\}/g, mode);
        lines.push(gloss.charAt(0).toUpperCase() + gloss.charAt(1) + gloss.slice(1) + ".");
      } else {
        lines.push(`Source « ${source} ».`);
      }
    }
    if (confidence != null) {
      const cg = CONFIDENCE_GLOSS[confidence];
      if (cg) lines.push(cg.charAt(0).toUpperCase() + cg.slice(1) + ".");
      else lines.push(`Confiance « ${confidence} ».`);
    }
    return lines.join(" ");
  }

  if (layer === "llm") {
    const parts = [];
    if (d.stream === true) parts.push("Réponse en flux.");
    else parts.push("Réponse en bloc.");
    const cf = d.context_fill;
    if (!cf) {
      if (typeof ev.prompt_tokens === "number") {
        const n = ev.prompt_tokens;
        const tok = n === 1 ? "token" : "tokens";
        let line = `Le fournisseur annonce ${n.toLocaleString("fr-FR")} ${tok} de prompt`;
        if (n === 0) line += " ; ce 0 est son chiffre";
        parts.push(line + ".");
      } else if (ev.prompt_tokens === null) {
        parts.push("Le fournisseur n'a pas annoncé les tokens de prompt.");
      }
    }
    if (typeof ev.completion_tokens === "number") {
      const n = ev.completion_tokens;
      const tok = n === 1 ? "token" : "tokens";
      parts.push(`Le fournisseur annonce ${n.toLocaleString("fr-FR")} ${tok} de completion.`);
    } else if (ev.completion_tokens === null) {
      parts.push("Le fournisseur n'a pas annoncé les tokens de completion.");
    }
    const roles = d.message_roles;
    if (Array.isArray(roles) && roles.length > 0) {
      for (const r of roles) {
        if (r.role && typeof r.content_bytes === "number") {
          parts.push(
            `Pellicule a mesuré ${r.content_bytes.toLocaleString("fr-FR")} octets pour ${r.role}.`
          );
        }
      }
    } else {
      parts.push("Les tailles des messages ne sont pas dans l'événement.");
    }
    if (!d.messages) {
      parts.push("Le texte des messages n'est pas dans cet événement.");
    }
    if (cf) {
      parts.push("Répartition mesurée : ouvrez « Contexte » ou cliquez la barre sous la ligne.");
    } else {
      parts.push("Répartition de la fenêtre non calculée.");
    }
    return parts.join(" ");
  }

  if (layer === "tool_request") {
    const toolRaw = d.tool || "";
    const tool = spokenToolName(toolRaw);
    if (toolRaw === "task" || tool === "task") {
      const brief = d.delegation_brief;
      if (brief != null && brief !== "") return brief;
      return "brief non vu";
    }
    let text =
      "Le modèle a demandé l'outil. Ce n'est pas une exécution. La fenêtre Allow once est le clic de l'utilisateur, pas cette ligne.";
    if (d.retry_of && d.retry_index) {
      text = `Réessai × ${d.retry_index}. ${text}`;
    }
    return text;
  }

  if (layer === "policy") {
    if (d.verdict === "allow") {
      return "Ce verdict décrit la règle de l'agent dans la configuration. La fenêtre Allow once décrit le clic de l'utilisateur. Les deux ne sont pas le même fait.";
    }
    if (d.verdict === "deny") return "Cette règle bloque l'outil.";
    if (d.verdict === "ask") return "Cette règle demande un clic. Le clic est une autre ligne.";
    return "";
  }

  if (layer === "exec") {
    return "Le document entier reste hors du film. L'extrait est le début retenu, l'empreinte est sha256.";
  }

  if (layer === "case_write") {
    return "Seule preuve hors du modèle.";
  }

  if (layer === "kilo_log") {
    return "La source n'a pas été comprise. On ne l'interprète pas.";
  }

  if (layer === "compact") {
    const parts = [];
    if (d.dropped_by_role && typeof d.dropped_by_role === "object") {
      for (const [role, count] of Object.entries(d.dropped_by_role)) {
        parts.push(`${role} : ${count} retiré(s).`);
      }
    }
    if (d.notes_before === false) {
      parts.push("Aucun case_write de NOTES.md avant ce tour.");
    }
    if (parts.length) return parts.join(" ");
    return layerLegend("compact");
  }

  if (layer === "skill") {
    const parts = [];
    if (d.llm_ts) parts.push(`Horodatage de la réponse associée : ${d.llm_ts}.`);
    parts.push("Lecture de ce fichier, injection dans le message system.");
    if (d.why == null) parts.push("Motif non vu.");
    else if (d.why === "slash" && d.why_detail) parts.push(`Commande /${d.why_detail}.`);
    else if (d.why === "tool") parts.push("Nom cité dans une demande d'outil.");
    if (d.description) parts.push(`Le fichier déclare : ${d.description}`);
    return parts.join(" ");
  }

  if (layer === "click") {
    let text = "Ceci est le geste de l'utilisateur. La règle est la ligne policy du même outil.";
    if (d.agree === true) text += " Le journal concorde avec la règle.";
    if (d.agree === false) text += " Le journal ne concorde pas.";
    return text;
  }

  if (layer === "mcp") {
    return ev.summary || layerLegend(layer);
  }

  return ev.summary || "";
}

function genericDetailHtml(ev) {
  const d = ev.detail || {};
  const lines = [];
  for (const [key, val] of Object.entries(d)) {
    if (val === null || val === undefined) continue;
    const display = typeof val === "object" ? JSON.stringify(val) : String(val);
    lines.push(`<dt>${escapeHtml(key)}</dt><dd><code>${escapeHtml(display)}</code></dd>`);
  }
  if (d.raw != null && ev.layer === "kilo_log") {
    /* raw already listed */
  }
  if (!lines.length) return `<p class="muted-detail">Aucun détail.</p>`;
  return `<dl class="event-detail">${lines.join("")}</dl>`;
}

function formatRuleObjectPhrase(ev, obj) {
  const d = ev.detail || {};
  const tool = spokenToolName(d.tool || "");
  const file = ruleFileName(d.rule_source);
  if (d.verdict === "allow" && Array.isArray(d.losers) && d.losers.length === 0) {
    const keys = Object.keys(obj || {});
    if (keys.length === 1 && obj["*"] === "allow") {
      return `Dans ${file}, ${tool} est autorisé pour tous les chemins.`;
    }
  }
  if (d.verdict === "deny" && obj && typeof obj === "object") {
    const parts = [];
    for (const [pattern, action] of Object.entries(obj)) {
      parts.push(`${pattern} → ${action}`);
    }
    return `Dans ${file}, ${tool} : ${parts.join(", ")}.`;
  }
  return null;
}

async function enrichPolicyRule(row, ev) {
  const d = ev.detail || {};
  if (!d.tool || !d.rule_source || (d.verdict !== "allow" && d.verdict !== "deny")) return;
  const params = new URLSearchParams({
    tool: d.tool,
    rule_source: d.rule_source,
    mode: ev.mode || "",
  });
  try {
    const res = await fetch(`/api/rule?${params}`);
    if (!res.ok) return;
    const obj = await res.json();
    const phrase = formatRuleObjectPhrase(ev, obj);
    const folds = row.querySelectorAll(".event-fold");
    if (phrase && folds[0]) {
      const body = folds[0].querySelector(".fold-body");
      if (body) body.textContent = phrase;
    }
    if (folds[1]) {
      const body = folds[1].querySelector(".fold-body");
      if (body) {
        body.innerHTML =
          policyDetailHtml(ev) +
          `<pre class="journal-json">${escapeHtml(JSON.stringify(obj, null, 2))}</pre>`;
      }
    }
  } catch {
    /* ignore */
  }
}

function policyDetailHtml(ev) {
  const d = ev.detail || {};
  const lines = [];
  if (d.matched_rule) lines.push(`<dt>Règle gagnante</dt><dd><code>${escapeHtml(d.matched_rule)}</code></dd>`);
  if (Array.isArray(d.losers)) {
    const text =
      d.losers.length === 0
        ? "aucune"
        : `<ul>${d.losers.map((l) => `<li><code>${escapeHtml(l)}</code></li>`).join("")}</ul>`;
    lines.push(`<dt>Perdantes</dt><dd>${text}</dd>`);
  }
  if (d.rule_source) lines.push(`<dt>Source</dt><dd><code>${escapeHtml(d.rule_source)}</code></dd>`);
  if (d.config_source) lines.push(`<dt>Config</dt><dd>${escapeHtml(d.config_source)}</dd>`);
  if (d.dialect) lines.push(`<dt>Dialecte</dt><dd>${escapeHtml(d.dialect)}</dd>`);
  if (d.precedence) lines.push(`<dt>Précédence</dt><dd>${escapeHtml(d.precedence)}</dd>`);
  if (d.kilo_log) lines.push(`<dt>Log Kilo</dt><dd><code>${escapeHtml(d.kilo_log)}</code></dd>`);
  if (d.ask_state) lines.push(`<dt>État ask</dt><dd>${escapeHtml(d.ask_state)}</dd>`);
  if (d.annotation) lines.push(`<dt>Note</dt><dd>${escapeHtml(d.annotation)}</dd>`);
  if (typeof d.agree === "boolean") {
    lines.push(`<dt>Accord</dt><dd class="${d.agree === false ? "disagree" : ""}">${d.agree ? "concordant" : "non concordant"}</dd>`);
  }
  if (d.verdict === "deny" || d.verdict === "ask") {
    const hyp = d.hypothesis != null && d.hypothesis !== "" ? escapeHtml(d.hypothesis) : "aucune";
    lines.push(`<dt>Hypothèse</dt><dd class="${d.hypothesis ? "disagree" : ""}">${hyp}</dd>`);
  }
  if (d.retry_burned_completion_tokens) {
    lines.push(`<dt>Tokens brûlés</dt><dd>${d.retry_burned_completion_tokens}</dd>`);
  }
  return `<dl class="policy-detail">${lines.join("")}</dl>`;
}

function toolRequestDetailHtml(ev) {
  const d = ev.detail || {};
  const toolRaw = d.tool || "";
  const tool = spokenToolName(toolRaw);
  if (toolRaw !== "task" && tool !== "task") return genericDetailHtml(ev);
  const lines = [];
  if (d.delegation_agent != null) {
    lines.push(`<dt>Agent</dt><dd><code>${escapeHtml(d.delegation_agent)}</code></dd>`);
  }
  if (d.delegation_brief != null && d.delegation_brief !== "") {
    lines.push(`<dt>Brief</dt><dd>${escapeHtml(d.delegation_brief)}</dd>`);
  } else {
    lines.push("<dt>Brief</dt><dd>brief non vu</dd>");
    if (d.arguments && typeof d.arguments === "object") {
      lines.push("<dt>Clés d'arguments</dt><dd><code>" + escapeHtml(Object.keys(d.arguments).join(", ")) + "</code></dd>");
    }
  }
  return `<dl class="event-detail">${lines.join("")}</dl>`;
}

function llmMessageFoldHtml(ev) {
  const d = ev.detail || {};
  if (!d.messages) {
    return "<p>texte non enregistré</p>";
  }
  const blocks = Array.isArray(d.prompt_blocks) ? d.prompt_blocks : [];
  const parts = [];
  for (const msg of d.messages) {
    const role = msg.role || "?";
    const content = msg.content != null ? String(msg.content) : "";
    const excerpt = content.slice(0, 400);
    const size = msg.size_bytes != null ? msg.size_bytes : content.length;
    let header = role;
    const block = blocks.find((b) => b.kind && msg.role === "system");
    if (role === "system" && blocks.length) {
      header += ` — ${blocks.map((b) => b.label).join(", ")}`;
    }
    let line = `<p><strong>${escapeHtml(header)}</strong> (${size.toLocaleString("fr-FR")} car.) ${escapeHtml(excerpt)}`;
    if (msg.truncated) line += " [tronqué]";
    line += "</p>";
    parts.push(line);
  }
  if (!d.prompt_blocks && d.messages.some((m) => m.role === "system")) {
    parts.unshift("<p>blocs non calculés</p>");
  }
  return parts.join("") || "<p>texte non enregistré</p>";
}

function llmBrutFoldHtml(ev) {
  const d = ev.detail || {};
  if (!d.messages) return "<p>texte non enregistré</p>";
  return d.messages
    .map((msg) => {
      const role = msg.role || "?";
      const content = msg.content != null ? escapeHtml(String(msg.content)) : "";
      return `<p><strong>${escapeHtml(role)}</strong></p><pre class="journal-json">${content}</pre>`;
    })
    .join("");
}

function detailFoldHtml(ev) {
  if (ev.layer === "policy") return policyDetailHtml(ev);
  if (ev.layer === "tool_request") return toolRequestDetailHtml(ev);
  return genericDetailHtml(ev);
}

function journalHtml(ev) {
  return `<pre class="journal-json">${escapeHtml(JSON.stringify(ev, null, 2))}</pre>`;
}

function buildEventFolds(ev, ctx) {
  const folds = document.createElement("div");
  folds.className = "event-folds";

  const hasContextFill = ev.layer === "llm" && ev.detail && ev.detail.context_fill;

  const happened = document.createElement("details");
  happened.className = "event-fold event-fold-happened";
  happened.open = !hasContextFill;
  happened.innerHTML = `<summary>Ce qui s'est passé</summary><div class="fold-body">${escapeHtml(whatHappened(ev, ctx))}</div>`;

  const detail = document.createElement("details");
  detail.className = "event-fold event-fold-detail";
  detail.innerHTML = `<summary>Détail</summary><div class="fold-body">${detailFoldHtml(ev)}</div>`;

  const journal = document.createElement("details");
  journal.className = "event-fold event-fold-journal";
  journal.innerHTML = `<summary>Journal</summary><div class="fold-body">${journalHtml(ev)}</div>`;

  if (hasContextFill) {
    const cf = ev.detail.context_fill;
    const contextFold = document.createElement("details");
    contextFold.className = "event-fold event-fold-context";
    contextFold.innerHTML = `<summary class="context-fold-summary">${contextUsageMiniBarHtml(cf)}<span class="context-fold-summary-text">${escapeHtml(contextFoldSummaryLabel(cf))}</span></summary><div class="fold-body">${contextFoldBodyHtml(cf)}</div>`;
    folds.appendChild(contextFold);
  }

  folds.appendChild(happened);
  folds.appendChild(detail);
  if (ev.layer === "llm") {
    const messageFold = document.createElement("details");
    messageFold.className = "event-fold event-fold-message";
    messageFold.innerHTML = `<summary>Message</summary><div class="fold-body">${llmMessageFoldHtml(ev)}</div>`;
    const brutFold = document.createElement("details");
    brutFold.className = "event-fold event-fold-brut";
    brutFold.innerHTML = `<summary>Brut</summary><div class="fold-body">${llmBrutFoldHtml(ev)}</div>`;
    folds.appendChild(messageFold);
    folds.appendChild(brutFold);
  }
  folds.appendChild(journal);

  folds.addEventListener("click", (e) => {
    e.stopPropagation();
  });

  return folds;
}

function refreshRowPhrases(row, ev, ctx) {
  const summaryEl = row.querySelector(".event-summary");
  if (summaryEl) summaryEl.textContent = shortPhrase(ev, ctx);
  const happenedFold = row.querySelector(".event-fold-happened");
  if (happenedFold) {
    const body = happenedFold.querySelector(".fold-body");
    if (body) body.textContent = whatHappened(ev, ctx);
  }
  const detailFold = row.querySelector(".event-fold-detail");
  if (detailFold) {
    const body = detailFold.querySelector(".fold-body");
    if (body) body.innerHTML = detailFoldHtml(ev);
  }
  if (ev.layer === "llm" && ev.detail && ev.detail.context_fill) {
    const cf = ev.detail.context_fill;
    const contextFold = row.querySelector(".event-fold-context");
    if (contextFold) {
      const label = contextFold.querySelector(".context-fold-summary-text");
      if (label) label.textContent = contextFoldSummaryLabel(cf);
      const body = contextFold.querySelector(".fold-body");
      if (body) body.innerHTML = contextFoldBodyHtml(cf);
    }
    const preview = row.querySelector(".event-context-preview");
    if (preview) {
      const measured = measuredBytesFromParts(cf.parts, cf.measured_bytes);
      preview.innerHTML = `${contextUsageMiniBarHtml(cf)}<span class="event-context-bytes">${formatBytesCompact(measured)}</span><span class="event-context-action">répartition</span>`;
    }
  }
  const msgFold = row.querySelector(".event-fold-message");
  if (msgFold) {
    const body = msgFold.querySelector(".fold-body");
    if (body) body.innerHTML = llmMessageFoldHtml(ev);
  }
  const brutFold = row.querySelector(".event-fold-brut");
  if (brutFold) {
    const body = brutFold.querySelector(".fold-body");
    if (body) body.innerHTML = llmBrutFoldHtml(ev);
  }
  const journalFold = row.querySelector(".event-fold-journal");
  if (journalFold) {
    const body = journalFold.querySelector(".fold-body");
    if (body) body.innerHTML = journalHtml(ev);
  }
  row._event = ev;
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
  const ctx = { execIds, replayComplete };
  refreshRowPhrases(row, ev, ctx);
  applyPolicyRowClasses(row, ev);
  const layerEl = row.querySelector(".layer-pill");
  if (layerEl) layerEl.className = layerPillClasses(ev);
  enrichPolicyRule(row, ev);
  updateCurrentSegmentTone(ev);
}

function eventSegmentTone(ev) {
  const d = ev.detail || {};
  if (d.error || (ev.summary && String(ev.summary).includes("error"))) return "error";
  if (ev.layer === "policy") {
    if (d.agree === false) return "error";
    if (d.verdict === "deny") return "deny";
    if (d.verdict === "ask" && d.ask_state === "pending") return "ask";
  }
  if (ev.layer === "tool_request" && d.retry_of && d.retry_index) return "retry";
  if (ev.layer === "compact") return "compact";
  return null;
}

function mergeSegmentTone(current, next) {
  if (!next) return current;
  const curRank = SEGMENT_TONE_RANK[current] ?? 0;
  const nextRank = SEGMENT_TONE_RANK[next] ?? 0;
  return nextRank > curRank ? next : current;
}

function ensureTurnBlock(forLlm) {
  if (forLlm || currentTurnBlock === null) {
    if (forLlm) turnIndex += 1;
    else if (turnIndex < 0) turnIndex = 0;

    const block = document.createElement("div");
    block.className = "turn-block";
    block.dataset.turnIndex = String(turnIndex);

    const anchor = document.createElement("div");
    anchor.className = "turn-anchor";
    anchor.id = `tour-${turnIndex}`;
    anchor.dataset.turnIndex = String(turnIndex);
    block.appendChild(anchor);

    filmEl.appendChild(block);
    currentTurnBlock = block;
    turnAnchorEls[turnIndex] = anchor;
    turnSegments[turnIndex] = { tone: "neutral" };
    renderTrajectory();
  }
  return currentTurnBlock;
}

function updateCurrentSegmentTone(ev) {
  if (turnIndex < 0) return;
  const tone = eventSegmentTone(ev);
  if (!tone) return;
  turnSegments[turnIndex].tone = mergeSegmentTone(turnSegments[turnIndex].tone, tone);
  renderTrajectory();
}

function renderTrajectory() {
  if (!trajectoryEl) return;
  if (turnSegments.length === 0) {
    trajectoryEl.hidden = true;
    trajectoryEl.innerHTML = "";
    return;
  }
  trajectoryEl.hidden = false;
  trajectoryEl.innerHTML = "";
  for (let i = 0; i < turnSegments.length; i += 1) {
    const seg = document.createElement("button");
    seg.type = "button";
    seg.className = `trajectory-segment is-${turnSegments[i].tone || "neutral"}`;
    seg.title = `Tour ${i + 1}`;
    seg.setAttribute("aria-label", `Aller au tour ${i + 1}`);
    seg.addEventListener("click", () => scrollToTurn(i));
    trajectoryEl.appendChild(seg);
  }
}

function scrollToTurn(index) {
  const anchor = turnAnchorEls[index] || document.getElementById(`tour-${index}`);
  if (anchor) {
    anchor.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

function toolCycleHeaderText(ev) {
  const d = ev.detail || {};
  const tool = spokenToolName(d.tool || "") || "—";
  const arg = salientArgument(ev, d.arguments);
  return arg ? `${tool} — ${arg}` : tool;
}

function getInsertParent(ev) {
  const id = ev.tool_call_id;
  const cycleLayers = new Set(["tool_request", "policy", "exec", "click"]);
  if (!id || !cycleLayers.has(ev.layer)) {
    return ensureTurnBlock(false);
  }
  if (ev.layer === "tool_request") {
    if (!toolCycleEls.has(id)) {
      const cycle = document.createElement("div");
      cycle.className = "tool-cycle";
      const header = document.createElement("div");
      header.className = "tool-cycle-header";
      header.textContent = toolCycleHeaderText(ev);
      cycle.appendChild(header);
      ensureTurnBlock(false).appendChild(cycle);
      toolCycleEls.set(id, cycle);
    }
    return toolCycleEls.get(id);
  }
  if (toolCycleEls.has(id)) return toolCycleEls.get(id);
  return ensureTurnBlock(false);
}

function layerPillClasses(ev) {
  const classes = ["layer-pill", `is-${ev.layer.replace(/_/g, "-")}`];
  if (ev.layer === "policy") {
    const d = ev.detail || {};
    if (d.verdict === "deny") classes.push("is-policy-deny");
    if (d.verdict === "ask") classes.push("is-policy-ask");
  }
  return classes.join(" ");
}

function setConnectionStatus(mode) {
  if (!connectionStatusEl) return;
  connectionStatusEl.classList.remove("is-live", "is-replay", "is-offline");
  if (mode === "live") {
    connectionStatusEl.textContent = "En direct";
    connectionStatusEl.classList.add("is-live");
    if (liveBtnEl) liveBtnEl.classList.add("hidden");
    if (sessionHintEl) sessionHintEl.textContent = "Direct — film en cours";
  } else if (mode === "replay") {
    connectionStatusEl.textContent = "Rejeu";
    connectionStatusEl.classList.add("is-replay");
    if (liveBtnEl) liveBtnEl.classList.remove("hidden");
    if (sessionHintEl) sessionHintEl.textContent = "Rejeu enregistré — pas d’appels réseau";
  } else if (mode === "offline") {
    connectionStatusEl.textContent = "Déconnecté";
    connectionStatusEl.classList.add("is-offline");
  }
}

function refreshConnectionStatus() {
  if (!liveReplay) {
    setConnectionStatus("replay");
    return;
  }
  setConnectionStatus(sseOpen ? "live" : "offline");
}

function markRowLiveNew(row) {
  if (!liveReplay) return;
  row.classList.add("is-new");
  requestAnimationFrame(() => {
    window.setTimeout(() => row.classList.remove("is-new"), 400);
  });
}

function currentTheme() {
  return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
}

function syncThemeToggle() {
  const btn = document.getElementById("theme-toggle");
  if (!btn) return;
  const dark = currentTheme() === "dark";
  btn.setAttribute("aria-pressed", dark ? "true" : "false");
  btn.setAttribute(
    "aria-label",
    dark ? "Passer en mode clair" : "Passer en mode sombre"
  );
}

function applyTheme(theme) {
  const next = theme === "dark" ? "dark" : "light";
  document.documentElement.setAttribute("data-theme", next);
  try {
    localStorage.setItem(THEME_STORAGE_KEY, next);
  } catch {
    /* préférence non persistée */
  }
  syncThemeToggle();
}

function initThemeToggle() {
  const btn = document.getElementById("theme-toggle");
  if (!btn) return;
  syncThemeToggle();
  btn.addEventListener("click", () => {
    applyTheme(currentTheme() === "dark" ? "light" : "dark");
  });
}

function initLegendsDrawer() {
  if (!legendsDrawerEl) return;
  legendsDrawerEl.open = localStorage.getItem("pellicule.legendsOpen") === "true";
  legendsDrawerEl.addEventListener("toggle", () => {
    localStorage.setItem("pellicule.legendsOpen", legendsDrawerEl.open ? "true" : "false");
  });
}

function warnIfStylesMissing() {
  const shell = document.querySelector(".app-shell");
  if (!shell) return;
  const bg = getComputedStyle(document.body).backgroundImage;
  if (!bg || bg === "none") {
    console.warn(
      "Pellicule : les styles semblent absents. Ouvrez l’UI via http://127.0.0.1:8766 (pas en file://) et rechargez avec Ctrl+F5."
    );
  }
}

function truncatePath(path, maxLen) {
  if (!path || path.length <= maxLen) return path;
  return "…" + path.slice(-(maxLen - 1));
}

function toggleEventRow(row) {
  const open = row.classList.toggle("is-open");
  const btn = row.querySelector(".event-line");
  if (btn) btn.setAttribute("aria-expanded", open ? "true" : "false");
}

function appendEvent(ev) {
  if (ev.layer === "policy" && ev.detail && ev.detail.ask_transition && ev.tool_call_id) {
    updatePolicyRow(ev);
    accumulateTokens(ev);
    updateCurrentSegmentTone(ev);
    return;
  }

  if (!TIMELINE_LAYERS.includes(ev.layer)) return;

  if (ev.layer === "llm") {
    ensureTurnBlock(true);
  } else {
    ensureTurnBlock(false);
  }
  updateCurrentSegmentTone(ev);

  const ctx = { execIds, replayComplete };

  const row = document.createElement("article");
  row.className = "event-row";
  row.dataset.layer = ev.layer;
  if (!isLayerEnabled(ev.layer)) {
    row.classList.add("is-layer-hidden");
  }
  if (ev.parent_session_id) {
    row.classList.add("is-nested");
  }
  if (ev.summary && String(ev.summary).includes("error")) {
    row.classList.add("is-error");
  }
  if (ev.detail && ev.detail.error) {
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
  if (ev.layer === "click") row.classList.add("is-tool-request");
  if (ev.layer === "mcp") row.classList.add("is-exec");
  if (ev.layer === "skill") row.classList.add("is-mode");
  if (ev.layer === "case_write") {
    row.classList.add("is-case-write");
    if (ev.detail && ev.detail.annotation) {
      row.classList.add("is-forbidden-write");
    }
  }
  if (ev.layer === "mode") row.classList.add("is-mode");
  if (ev.layer === "kilo_log") row.classList.add("is-kilo-log");
  if (ev.layer === "compact") row.classList.add("is-compact");

  const time = document.createElement("div");
  time.className = "event-time";
  time.textContent = formatTime(ev.ts);

  const layer = document.createElement("div");
  layer.className = layerPillClasses(ev);
  layer.textContent = ev.layer;

  const body = document.createElement("div");
  body.className = "event-body";

  if (ev.parent_session_id) {
    const parent = document.createElement("div");
    parent.className = "parent-link";
    parent.textContent = `session fille → parent ${ev.parent_session_id}`;
    body.appendChild(parent);
  }

  const lineBtn = document.createElement("button");
  lineBtn.type = "button";
  lineBtn.className = "event-line";
  lineBtn.setAttribute("aria-expanded", "false");
  const summary = document.createElement("span");
  summary.className = "event-summary";
  summary.textContent = shortPhrase(ev, ctx);
  lineBtn.appendChild(summary);
  lineBtn.addEventListener("click", () => toggleEventRow(row));
  lineBtn.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      toggleEventRow(row);
    }
  });

  body.appendChild(lineBtn);
  if (ev.layer === "llm" && ev.detail && ev.detail.context_fill) {
    body.appendChild(buildEventContextPreview(ev.detail.context_fill));
  }
  body.appendChild(buildEventFolds(ev, ctx));

  row.appendChild(time);
  row.appendChild(layer);
  row.appendChild(body);
  row._event = ev;

  const parent = getInsertParent(ev);
  parent.appendChild(row);
  markRowLiveNew(row);
  accumulateTokens(ev);

  if (ev.layer === "policy") {
    enrichPolicyRule(row, ev);
  }

  if (ev.layer === "tool_request" && ev.tool_call_id) {
    toolRequestRows.set(ev.tool_call_id, row);
  }

  if (ev.layer === "exec" && ev.tool_call_id) {
    execIds.add(ev.tool_call_id);
    const trRow = toolRequestRows.get(ev.tool_call_id);
    if (trRow && trRow._event) {
      refreshRowPhrases(trRow, trRow._event, { execIds, replayComplete });
    }
  }
  applyLayerFilters();
}

function renderLegends() {
  if (!legendsEl) return;
  legendsEl.innerHTML = "";
  for (const key of TIMELINE_LAYERS) {
    const block = layerMeta[key];
    if (!block) continue;
    const panel = document.createElement("div");
    panel.className = "legend-card";
    panel.dataset.layer = key;
    if (!isLayerEnabled(key)) panel.classList.add("is-layer-off");
    panel.innerHTML = `<span class="legend-card-tag">${escapeHtml(key)}</span><p class="legend-card-text">${escapeHtml(block.legend_fr)}</p>`;
    legendsEl.appendChild(panel);
  }
}

async function loadLegend() {
  const res = await fetch("/api/layers");
  layerMeta = await res.json();
  renderLayerFilterChips();
  renderLegends();
  applyLayerFilters();
}

function resetFilm() {
  filmEl.innerHTML = "";
  policyRows.clear();
  toolRequestRows.clear();
  toolCycleEls.clear();
  execIds = new Set();
  replayComplete = false;
  promptTotal = 0;
  completionTotal = 0;
  contextWindow = null;
  sessionContextParts = {};
  sessionContextMeasuredBytes = 0;
  sessionLlmCallCount = 0;
  currentTurnBlock = null;
  turnIndex = -1;
  turnSegments = [];
  turnAnchorEls = [];
  renderTrajectory();
  updateTokenBar();
  updateFilmEmptyState();
}

async function replaySession(sessionId) {
  liveReplay = false;
  activeSessionId = sessionId;
  refreshConnectionStatus();
  const res = await fetch(`/sessions/${encodeURIComponent(sessionId)}`);
  const data = await res.json();
  resetFilm();
  const events = data.events || [];
  for (const ev of events) {
    if (ev.layer === "exec" && ev.tool_call_id) {
      execIds.add(ev.tool_call_id);
    }
  }
  replayComplete = true;
  for (const ev of events) {
    appendEvent(ev);
  }
  if (data.tokens && data.tokens.total != null) {
    promptTotal = data.tokens.prompt_tokens || 0;
    completionTotal = data.tokens.completion_tokens || 0;
    updateTokenBar();
  }
  loadSessions();
}

function formatSessionDate(meta) {
  const raw = meta.started_at || meta.created_at || meta.ts;
  if (!raw) return null;
  try {
    const d = new Date(raw);
    return d.toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" });
  } catch {
    return null;
  }
}

async function loadSessions() {
  const res = await fetch("/sessions");
  const data = await res.json();
  if (!sessionGroupsEl) return;
  sessionGroupsEl.innerHTML = "";
  const allSessions = data.sessions || [];
  latestSessionId = allSessions.length > 0 ? allSessions[0].session_id : null;
  updateFilmEmptyState();

  if (sessionEmptyEl) {
    sessionEmptyEl.hidden = allSessions.length > 0;
  }

  const groups = new Map();
  for (const s of allSessions) {
    const key = s.case_dir || "(sans affaire)";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(s);
  }

  for (const [caseKey, sessions] of groups) {
    const section = document.createElement("section");
    section.className = "session-group";
    const title = document.createElement("h3");
    title.className = "session-group-title";
    title.textContent = caseKey === "(sans affaire)" ? caseKey : truncatePath(caseKey, 42);
    title.title = caseKey;
    section.appendChild(title);

    const ul = document.createElement("ul");
    ul.className = "session-list";
    for (const s of sessions) {
      const li = document.createElement("li");
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "session-btn";
      if (s.session_id === activeSessionId) btn.classList.add("is-active");
      const shortId = s.session_id.slice(0, 8);
      btn.title = s.session_id;
      const main = document.createElement("span");
      main.textContent = `${shortId}… · ${s.event_count || 0} événements`;
      btn.appendChild(main);
      const dateStr = formatSessionDate(s);
      if (dateStr) {
        const meta = document.createElement("span");
        meta.className = "session-meta";
        meta.textContent = dateStr;
        btn.appendChild(meta);
      }
      btn.addEventListener("click", () => replaySession(s.session_id));
      li.appendChild(btn);
      ul.appendChild(li);
    }
    section.appendChild(ul);
    sessionGroupsEl.appendChild(section);
  }
}

function returnToLive() {
  liveReplay = true;
  activeSessionId = null;
  resetFilm();
  refreshConnectionStatus();
  loadSessions();
}

function connect() {
  const es = new EventSource("/events");
  es.onopen = () => {
    sseOpen = true;
    refreshConnectionStatus();
  };
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
    sseOpen = false;
    refreshConnectionStatus();
    es.close();
    setTimeout(connect, 2000);
  };
}

initThemeToggle();
initLegendsDrawer();
initLayerFilterControls();
warnIfStylesMissing();
if (liveBtnEl) {
  liveBtnEl.addEventListener("click", returnToLive);
}
if (replayLatestBtn) {
  replayLatestBtn.addEventListener("click", () => {
    if (latestSessionId) replaySession(latestSessionId);
  });
}
loadLegend();
loadSessions();
updateTokenBar();
updateFilmEmptyState();
refreshConnectionStatus();
connect();

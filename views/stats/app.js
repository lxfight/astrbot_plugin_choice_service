const bridge = window.AstrBotPluginView;
const fallbackText = new Map();
let latestPayload = null;

const elements = {
  endpoint: document.getElementById("endpoint"),
  status: document.getElementById("status"),
  total: document.getElementById("total"),
  successRate: document.getElementById("success-rate"),
  avgLatency: document.getElementById("avg-latency"),
  choiceCalls: document.getElementById("choice-calls"),
  distribution: document.getElementById("distribution"),
  runtime: document.getElementById("runtime"),
  recent: document.getElementById("recent"),
  refresh: document.getElementById("refresh"),
  reset: document.getElementById("reset"),
};

const t = (key, fallback) => bridge.t(`views.stats.${key}`, fallback);

function applyStaticText() {
  document.documentElement.lang = bridge.getLocale();
  document.title = t("title", "Choice Service");
  document.querySelectorAll("[data-i18n]").forEach((node) => {
    const key = node.dataset.i18n;
    node.textContent = t(key, fallbackText.get(node) || node.textContent);
  });
}

function addText(parent, tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  node.textContent = text;
  parent.appendChild(node);
  return node;
}

function percent(value) {
  return `${(Number(value || 0) * 100).toFixed(1)}%`;
}

function renderDistribution(stats) {
  const root = elements.distribution;
  root.replaceChildren();
  const entries = Object.entries(stats.choice_counts || {});
  if (!entries.length) {
    addText(root, "p", "empty", t("noChoices", "No choice data yet."));
    return;
  }
  const max = Math.max(...entries.map(([, count]) => Number(count) || 0), 1);
  for (const [label, count] of entries) {
    const row = document.createElement("div");
    row.className = "distribution-row";
    addText(row, "span", "distribution-label", label);
    const bar = document.createElement("div");
    bar.className = "bar";
    const fill = document.createElement("span");
    fill.style.width = `${Math.max(4, (Number(count) / max) * 100)}%`;
    bar.appendChild(fill);
    row.appendChild(bar);
    addText(row, "span", "distribution-value", String(count));
    root.appendChild(row);
  }
}

function renderRuntime(payload) {
  const root = elements.runtime;
  root.replaceChildren();
  const stats = payload.stats || {};
  const rows = [
    [t("provider", "Provider"), t(`providers.${payload.provider}`, payload.provider)],
    [t("model", "Model"), payload.model || "—"],
    [t("timeout", "Timeout"), `${payload.timeout_sec}s`],
    [t("apiKey", "API key"), payload.api_key_configured ? t("configured", "Configured") : t("missing", "Missing")],
    [t("boolCalls", "Yes/no calls"), String(stats.bool_calls || 0)],
    [t("failedCalls", "Failed calls"), String(stats.failed || 0)],
    [t("lastError", "Last error"), stats.last_error || "—"],
  ];
  for (const [label, value] of rows) {
    addText(root, "dt", "", label);
    addText(root, "dd", "", value);
  }
}

function renderRecent(stats) {
  const root = elements.recent;
  root.replaceChildren();
  const entries = stats.recent || [];
  if (!entries.length) {
    const row = document.createElement("tr");
    const cell = addText(row, "td", "empty", t("empty", "No decisions yet."));
    cell.colSpan = 6;
    root.appendChild(row);
    return;
  }
  const locale = bridge.getLocale();
  for (const item of entries) {
    const row = document.createElement("tr");
    addText(
      row,
      "td",
      "",
      new Date(item.at).toLocaleTimeString(locale, {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      }),
    );
    const kind = item.kind === "bool" ? t("kindBool", "Yes/no") : t("kindChoice", "Choice");
    const kindCell = addText(row, "td", "", "");
    addText(kindCell, "span", "kind", kind);
    addText(row, "td", "question", item.question);
    const result = item.ok
      ? item.kind === "bool"
        ? t(item.result === "yes" ? "yes" : "no", item.result)
        : item.result
      : t("error", "Error");
    addText(row, "td", item.ok ? "" : "failed", result);
    addText(row, "td", "", item.probability === null ? "—" : percent(item.probability));
    addText(row, "td", "", `${item.latency_ms} ms`);
    root.appendChild(row);
  }
}

function render(payload) {
  latestPayload = payload;
  const stats = payload.stats || {};
  elements.endpoint.textContent = `${payload.base_url} · ${payload.model}`;
  elements.total.textContent = String(stats.total || 0);
  elements.successRate.textContent = percent(stats.success_rate);
  elements.avgLatency.textContent = `${stats.average_latency_ms || 0} ms`;
  elements.choiceCalls.textContent = String(stats.choice_calls || 0);
  renderDistribution(stats);
  renderRuntime(payload);
  renderRecent(stats);
}

async function loadStats() {
  elements.status.dataset.kind = "muted";
  elements.status.textContent = t("loading", "Loading...");
  try {
    const payload = await bridge.apiGet("stats");
    elements.status.textContent = "";
    delete elements.status.dataset.kind;
    render(payload);
  } catch (error) {
    elements.status.dataset.kind = "error";
    elements.status.textContent = `${t("loadFailed", "Failed to load statistics")}: ${error.message}`;
  }
}

async function resetStats() {
  if (!window.confirm(t("confirmReset", "Reset all statistics?"))) return;
  try {
    const payload = await bridge.apiPost("stats/reset", {});
    elements.status.textContent = "";
    delete elements.status.dataset.kind;
    render(payload);
  } catch (error) {
    elements.status.dataset.kind = "error";
    elements.status.textContent = `${t("resetFailed", "Failed to reset statistics")}: ${error.message}`;
  }
}

async function init() {
  document.querySelectorAll("[data-i18n]").forEach((node) => {
    fallbackText.set(node, node.textContent.trim());
  });
  await bridge.ready();
  applyStaticText();
  bridge.onContext(() => {
    applyStaticText();
    if (latestPayload) render(latestPayload);
  });
  elements.refresh.addEventListener("click", loadStats);
  elements.reset.addEventListener("click", resetStats);
  await loadStats();
}

init();

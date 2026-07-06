const state = {
  selected: [],
  currentJobId: null,
  pollTimer: null,
  jobs: [],
  dashboard: null,
  diffs: null,
};

const els = {
  searchForm: document.querySelector("#searchForm"),
  themeMode: document.querySelector("#themeMode"),
  query: document.querySelector("#query"),
  searchResults: document.querySelector("#searchResults"),
  searchError: document.querySelector("#searchError"),
  githubStatusTitle: document.querySelector("#githubStatusTitle"),
  githubStatusText: document.querySelector("#githubStatusText"),
  refreshGithub: document.querySelector("#refreshGithub"),
  selectedRepos: document.querySelector("#selectedRepos"),
  listTitle: document.querySelector("#listTitle"),
  clearList: document.querySelector("#clearList"),
  manualUrl: document.querySelector("#manualUrl"),
  addManual: document.querySelector("#addManual"),
  mode: document.querySelector("#mode"),
  timeout: document.querySelector("#timeout"),
  startScan: document.querySelector("#startScan"),
  aiModel: document.querySelector("#aiModel"),
  autoAi: document.querySelector("#autoAi"),
  aiSystemPrompt: document.querySelector("#aiSystemPrompt"),
  aiAdditionalInstructions: document.querySelector("#aiAdditionalInstructions"),
  refreshModels: document.querySelector("#refreshModels"),
  lmStatus: document.querySelector("#lmStatus"),
  globalStatus: document.querySelector("#globalStatus"),
  logs: document.querySelector("#logs"),
  reportTitle: document.querySelector("#reportTitle"),
  jobMeta: document.querySelector("#jobMeta"),
  reportResults: document.querySelector("#reportResults"),
  savedJobs: document.querySelector("#savedJobs"),
  refreshJobs: document.querySelector("#refreshJobs"),
  refreshDashboard: document.querySelector("#refreshDashboard"),
  dashboardUpdated: document.querySelector("#dashboardUpdated"),
  dashboardOverview: document.querySelector("#dashboardOverview"),
  dashboardOrganizations: document.querySelector("#dashboardOrganizations"),
  dashboardHotspots: document.querySelector("#dashboardHotspots"),
  dashboardTimeline: document.querySelector("#dashboardTimeline"),
  refreshDiffs: document.querySelector("#refreshDiffs"),
  diffUpdated: document.querySelector("#diffUpdated"),
  diffOverview: document.querySelector("#diffOverview"),
  diffResults: document.querySelector("#diffResults"),
};

const systemTheme = window.matchMedia("(prefers-color-scheme: dark)");
let currentThemeMode = localStorage.getItem("repoScannerTheme") || "system";
applyTheme(currentThemeMode);

els.searchForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const query = els.query.value.trim();
  if (!query) return;

  setSearchError("");
  els.searchResults.innerHTML = renderSkeleton("Ricerca in corso...");

  try {
    const data = await getJson(`/api/search?q=${encodeURIComponent(query)}`);
    if (data.error) throw new Error(data.error);
    renderSearchResults(data.items || []);
  } catch (error) {
    els.searchResults.innerHTML = "";
    setSearchError(error.message);
  }
});

els.clearList.addEventListener("click", () => {
  state.selected = [];
  renderSelected();
});

els.addManual.addEventListener("click", () => {
  const url = els.manualUrl.value.trim();
  if (!url) return;
  addRepo({ name: repoNameFromUrl(url), url, description: "Aggiunto manualmente" });
  els.manualUrl.value = "";
});

els.startScan.addEventListener("click", async () => {
  if (!state.selected.length) return;
  els.startScan.disabled = true;
  els.globalStatus.textContent = "Avvio scansione";
  els.reportResults.innerHTML = renderSkeleton("Preparazione job...");
  els.logs.textContent = "";

  try {
    const payload = {
      urls: state.selected.map((repo) => repo.url),
      mode: els.mode.value,
      timeout: Number(els.timeout.value || 0),
      ai: readAiConfig(),
    };
    const data = await postJson("/api/scan", payload);
    if (data.error) throw new Error(data.error);
    state.currentJobId = data.job.id;
    await loadSavedJobs();
    startPolling();
  } catch (error) {
    els.startScan.disabled = false;
    els.globalStatus.textContent = "Errore";
    els.reportResults.innerHTML = `<div class="inline-error">${escapeHtml(error.message)}</div>`;
  }
});

els.refreshJobs.addEventListener("click", () => {
  loadSavedJobs();
  loadDashboard();
  loadDiffs();
});

els.refreshModels.addEventListener("click", () => {
  loadLmStudioStatus();
});

els.refreshDashboard.addEventListener("click", () => {
  loadDashboard();
});

els.refreshDiffs.addEventListener("click", () => {
  loadDiffs();
});

els.refreshGithub.addEventListener("click", () => {
  loadGithubStatus();
});

els.themeMode.addEventListener("change", () => {
  currentThemeMode = els.themeMode.value;
  localStorage.setItem("repoScannerTheme", currentThemeMode);
  applyTheme(currentThemeMode);
});

systemTheme.addEventListener("change", () => {
  if (currentThemeMode === "system") {
    applyTheme("system");
  }
});

function applyTheme(mode) {
  const resolved = mode === "system"
    ? (systemTheme.matches ? "dark" : "light")
    : mode;
  document.documentElement.dataset.theme = resolved;
  document.documentElement.dataset.themeMode = mode;
  els.themeMode.value = mode;
}

function readAiConfig() {
  return {
    model: els.aiModel.value,
    auto_analyze: els.autoAi.checked,
    system_prompt: els.aiSystemPrompt.value,
    additional_instructions: els.aiAdditionalInstructions.value,
  };
}

async function loadLmStudioStatus() {
  els.lmStatus.textContent = "Controllo LM Studio...";
  try {
    const status = await getJson("/api/ai/status");
    renderLmStudioStatus(status);
  } catch (error) {
    els.lmStatus.textContent = `LM Studio non raggiungibile: ${error.message}`;
  }
}

async function loadGithubStatus() {
  els.githubStatusTitle.textContent = "Verifica CLI in corso";
  els.githubStatusText.textContent = "Controllo se GitHub CLI e' disponibile e autenticata.";
  try {
    const status = await getJson("/api/github/status");
    renderGithubStatus(status);
  } catch (error) {
    els.githubStatusTitle.textContent = "Controllo non riuscito";
    els.githubStatusText.textContent = error.message;
  }
}

function renderGithubStatus(status) {
  const account = status.account ? ` come ${status.account}` : "";
  if (status.ready) {
    els.githubStatusTitle.textContent = `GitHub collegato${account}`;
    els.githubStatusText.textContent = "La ricerca e le scansioni GitHub useranno la CLI: puoi includere anche repository privati a cui hai accesso.";
    return;
  }
  if (!status.installed) {
    els.githubStatusTitle.textContent = "GitHub CLI non trovata";
    els.githubStatusText.textContent = "Per collegare GitHub installa la CLI e poi esegui: brew install gh, quindi gh auth login -h github.com.";
    return;
  }
  els.githubStatusTitle.textContent = "GitHub CLI non collegata";
  els.githubStatusText.textContent = "Per abilitare i repository privati esegui nel terminale: gh auth login -h github.com. L'app non salva token e usera' la sessione locale della CLI.";
}

function renderLmStudioStatus(status) {
  els.aiModel.innerHTML = `<option value="">Automatico</option>`;
  (status.models || [])
    .filter((model) => !/embed|embedding|reranker/i.test(model))
    .forEach((model) => {
      const option = document.createElement("option");
      option.value = model;
      option.textContent = model;
      if (model === status.selected_model) option.selected = true;
      els.aiModel.appendChild(option);
    });
  els.lmStatus.textContent = status.available
    ? `Connesso a ${status.base_url} - modello default: ${status.selected_model}`
    : `LM Studio non pronto: ${status.error || "nessun modello chat"}`;
}

function renderSearchResults(items) {
  if (!items.length) {
    els.searchResults.innerHTML = `<div class="empty">Nessun repository trovato.</div>`;
    return;
  }

  els.searchResults.innerHTML = items.map((item) => {
    const alreadySelected = state.selected.some((repo) => repo.url === item.url);
    return `
      <article class="repo-row">
        <div>
          <div class="repo-title">${escapeHtml(item.name)}</div>
          <p class="repo-description">${escapeHtml(item.description || "Nessuna descrizione.")}</p>
          <div class="repo-meta">
            <span>${escapeHtml(item.language || "Unknown")}</span>
            <span>${escapeHtml(item.provider || providerLabel(item.url))}</span>
            ${item.stars === null || item.stars === undefined ? "" : `<span>${Number(item.stars || 0).toLocaleString("it-IT")} stelle</span>`}
          </div>
        </div>
        <button type="button" data-add="${escapeHtml(item.url)}" ${alreadySelected ? "disabled" : ""}>
          ${alreadySelected ? "In lista" : "Aggiungi"}
        </button>
      </article>
    `;
  }).join("");

  els.searchResults.querySelectorAll("[data-add]").forEach((button) => {
    button.addEventListener("click", () => {
      const item = items.find((repo) => repo.url === button.dataset.add);
      if (item) addRepo(item);
    });
  });
}

function addRepo(repo) {
  if (!repo.url || state.selected.some((item) => item.url === repo.url)) return;
  state.selected.push(repo);
  renderSelected();
}

function renderSelected() {
  els.listTitle.textContent = `${state.selected.length} repository`;
  els.startScan.disabled = state.selected.length === 0;

  if (!state.selected.length) {
    els.selectedRepos.className = "selected-list empty";
    els.selectedRepos.textContent = "Nessun repository selezionato.";
    return;
  }

  els.selectedRepos.className = "selected-list";
  els.selectedRepos.innerHTML = state.selected.map((repo, index) => `
    <div class="selected-item">
      <div>
        <strong>${escapeHtml(repo.name || repoNameFromUrl(repo.url))}</strong>
        <div class="selected-url">${escapeHtml(repo.url)}</div>
      </div>
      <button type="button" data-remove="${index}">Rimuovi</button>
    </div>
  `).join("");

  els.selectedRepos.querySelectorAll("[data-remove]").forEach((button) => {
    button.addEventListener("click", () => {
      state.selected.splice(Number(button.dataset.remove), 1);
      renderSelected();
    });
  });
}

function startPolling() {
  if (state.pollTimer) clearInterval(state.pollTimer);
  pollJob();
  state.pollTimer = setInterval(pollJob, 1600);
}

async function pollJob() {
  if (!state.currentJobId) return;
  try {
    const data = await getJson(`/api/jobs/${state.currentJobId}`);
    renderJob(data.job);
    if (["completed", "failed"].includes(data.job.status) && data.job.ai_status !== "running") {
      clearInterval(state.pollTimer);
      state.pollTimer = null;
      els.startScan.disabled = state.selected.length === 0;
      loadSavedJobs();
      loadDashboard();
      loadDiffs();
    }
  } catch (error) {
    els.globalStatus.textContent = "Errore polling";
  }
}

async function loadDashboard() {
  els.dashboardUpdated.textContent = "Aggiornamento";
  try {
    const data = await getJson("/api/dashboard");
    state.dashboard = data;
    renderDashboard(data);
  } catch (error) {
    els.dashboardUpdated.textContent = "Errore";
    els.dashboardOverview.innerHTML = `<div class="inline-error">${escapeHtml(error.message)}</div>`;
  }
}

function renderDashboard(data) {
  const summary = data.summary || {};
  els.dashboardUpdated.textContent = `Aggiornato ${formatDate(data.updated_at)}`;
  els.dashboardOverview.innerHTML = `
    ${dashboardMetric("Organizzazioni", summary.organizations || 0, "perimetro scansionato")}
    ${dashboardMetric("Repository", summary.repositories || 0, "ultima scansione nota")}
    ${dashboardMetric("Finding attivi", summary.findings || 0, "sugli ultimi report")}
    ${dashboardMetric("Repo esposti", summary.risky_repositories || 0, "con finding aperti")}
    ${dashboardMetric("Esecuzioni", summary.jobs || 0, "archivio locale")}
  `;
  renderOrganizations(data.organizations || []);
  renderHotspots(data.hotspots || []);
  renderTimeline(data.timeline || []);
  wireDashboardJobButtons();
}

function dashboardMetric(label, value, detail) {
  return `
    <div class="dashboard-metric">
      <span class="metric-value">${formatNumber(value)}</span>
      <span class="metric-label">${escapeHtml(label)}</span>
      <span class="metric-detail">${escapeHtml(detail)}</span>
    </div>
  `;
}

function renderOrganizations(items) {
  if (!items.length) {
    els.dashboardOrganizations.className = "organization-list empty";
    els.dashboardOrganizations.textContent = "Nessuna organizzazione disponibile. Avvia una scansione per popolare la dashboard.";
    return;
  }

  els.dashboardOrganizations.className = "organization-list";
  els.dashboardOrganizations.innerHTML = items.map((org) => `
    <article class="organization-row risk-${escapeHtml(org.risk_level)}">
      <div class="organization-head">
        <div>
          <div class="org-name">${escapeHtml(org.name)}</div>
          <div class="org-meta">
            <span>${escapeHtml(org.provider || "Repository")}</span>
            <span>${formatNumber(org.repositories)} repo</span>
            <span>${formatNumber(org.findings)} finding</span>
            <span>${escapeHtml(formatDate(org.last_scan))}</span>
          </div>
        </div>
        <span class="risk-badge ${escapeHtml(org.risk_level)}">${escapeHtml(riskLabel(org.risk_level))}</span>
      </div>
      <div class="severity-strip">
        ${severityPill("Critici", org.severity?.critical || 0, "critical")}
        ${severityPill("Alti", org.severity?.high || 0, "high")}
        ${severityPill("Medi", org.severity?.medium || 0, "medium")}
        ${severityPill("Bassi", org.severity?.low || 0, "low")}
      </div>
      ${renderRuleChips(org.top_rules || [])}
      <div class="repo-mini-list">
        ${(org.repos || []).map(renderRepoMini).join("")}
      </div>
    </article>
  `).join("");
}

function severityPill(label, value, level) {
  return `<span class="severity-pill ${level}">${escapeHtml(label)} ${formatNumber(value)}</span>`;
}

function renderRuleChips(rules) {
  if (!rules.length) return `<div class="rule-chips muted">Nessuna regola ricorrente.</div>`;
  return `
    <div class="rule-chips">
      ${rules.map(([rule, count]) => `<span>${escapeHtml(rule)} <strong>${formatNumber(count)}</strong></span>`).join("")}
    </div>
  `;
}

function renderRepoMini(repo) {
  return `
    <button type="button" class="repo-mini risk-${escapeHtml(repo.risk_level)}" data-open-job="${escapeHtml(repo.job_id || "")}" ${repo.job_id ? "" : "disabled"}>
      <span>
        <strong>${escapeHtml(repo.name)}</strong>
        <small>${formatNumber(repo.findings)} finding | ${escapeHtml(riskLabel(repo.risk_level))}</small>
      </span>
      <span>${escapeHtml(formatDate(repo.last_scan))}</span>
    </button>
  `;
}

function renderHotspots(items) {
  if (!items.length) {
    els.dashboardHotspots.className = "hotspot-list empty";
    els.dashboardHotspots.textContent = "Nessun repository con finding nell'ultima scansione nota.";
    return;
  }

  els.dashboardHotspots.className = "hotspot-list";
  els.dashboardHotspots.innerHTML = items.map((repo) => `
    <button type="button" class="hotspot-row risk-${escapeHtml(repo.risk_level)}" data-open-job="${escapeHtml(repo.job_id || "")}" ${repo.job_id ? "" : "disabled"}>
      <span>
        <strong>${escapeHtml(repo.name)}</strong>
        <small>${escapeHtml(repo.organization)} | ${formatNumber(repo.findings)} finding</small>
      </span>
      <span class="risk-badge ${escapeHtml(repo.risk_level)}">${escapeHtml(riskLabel(repo.risk_level))}</span>
    </button>
  `).join("");
}

function renderTimeline(items) {
  if (!items.length) {
    els.dashboardTimeline.className = "timeline-list empty";
    els.dashboardTimeline.textContent = "Nessuna esecuzione disponibile.";
    return;
  }

  els.dashboardTimeline.className = "timeline-list";
  els.dashboardTimeline.innerHTML = items.map((job) => `
    <button type="button" class="timeline-row" data-open-job="${escapeHtml(job.id || "")}" ${job.id ? "" : "disabled"}>
      <span>
        <strong>${escapeHtml(formatDate(job.started_at))}</strong>
        <small>${formatNumber(job.repositories || 0)} repo | ${formatNumber(job.findings || 0)} finding</small>
      </span>
      <span>${escapeHtml(statusLabel(job.status))}</span>
    </button>
  `).join("");
}

function wireDashboardJobButtons() {
  document.querySelectorAll(".risk-pane [data-open-job]").forEach((button) => {
    button.addEventListener("click", async () => {
      const jobId = button.dataset.openJob;
      if (!jobId) return;
      const data = await getJson(`/api/jobs/${jobId}`);
      state.currentJobId = jobId;
      renderJob(data.job);
      renderSavedJobs();
      document.querySelector(".report-pane")?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });
}

async function loadDiffs() {
  els.diffUpdated.textContent = "Aggiornamento";
  try {
    const data = await getJson("/api/diffs");
    state.diffs = data;
    renderDiffs(data);
  } catch (error) {
    els.diffUpdated.textContent = "Errore";
    els.diffOverview.innerHTML = `<div class="inline-error">${escapeHtml(error.message)}</div>`;
  }
}

function renderDiffs(data) {
  const summary = data.summary || {};
  els.diffUpdated.textContent = `Aggiornato ${formatDate(data.updated_at)}`;
  els.diffOverview.innerHTML = `
    ${dashboardMetric("Repo confrontati", summary.repositories || 0, "almeno due scansioni")}
    ${dashboardMetric("Nuovi finding", summary.new || 0, "entrati nell'ultimo scan")}
    ${dashboardMetric("Risolti", summary.resolved || 0, "presenti prima, assenti ora")}
    ${dashboardMetric("Invariati", summary.unchanged || 0, "ancora presenti")}
    ${dashboardMetric("Saldo", Number(summary.new || 0) - Number(summary.resolved || 0), "nuovi meno risolti")}
  `;

  const comparisons = data.comparisons || [];
  if (!comparisons.length) {
    els.diffResults.className = "diff-list empty";
    els.diffResults.textContent = "Serve almeno una seconda scansione dello stesso repository per calcolare il delta.";
    return;
  }

  els.diffResults.className = "diff-list";
  els.diffResults.innerHTML = comparisons.map((item) => `
    <article class="diff-row">
      <div class="diff-head">
        <div>
          <div class="repo-title">${escapeHtml(item.repository)}</div>
          <div class="repo-meta">
            <span>${escapeHtml(item.organization)}</span>
            <span>${escapeHtml(formatDate(item.previous_at))}</span>
            <span>${escapeHtml(formatDate(item.latest_at))}</span>
          </div>
        </div>
        <div class="diff-counters">
          <span class="diff-count new">Nuovi ${formatNumber(item.new)}</span>
          <span class="diff-count resolved">Risolti ${formatNumber(item.resolved)}</span>
          <span class="diff-count unchanged">Invariati ${formatNumber(item.unchanged)}</span>
        </div>
      </div>
      <div class="diff-body">
        ${renderDiffItems("Nuovi finding", item.new_items || [])}
        ${renderDiffItems("Finding risolti", item.resolved_items || [])}
      </div>
      <div class="diff-actions">
        <button type="button" data-open-job="${escapeHtml(item.previous_job_id || "")}" ${item.previous_job_id ? "" : "disabled"}>Report precedente</button>
        <button type="button" data-open-job="${escapeHtml(item.latest_job_id || "")}" ${item.latest_job_id ? "" : "disabled"}>Report attuale</button>
      </div>
    </article>
  `).join("");
  wireDiffJobButtons();
}

function renderDiffItems(title, items) {
  if (!items.length) {
    return `
      <div class="diff-items muted">
        <strong>${escapeHtml(title)}</strong>
        <span>Nessun elemento.</span>
      </div>
    `;
  }
  return `
    <div class="diff-items">
      <strong>${escapeHtml(title)}</strong>
      ${items.map((item) => `
        <span>${escapeHtml(item.rule || "unknown-rule")} | ${escapeHtml(item.file || "unknown-file")}:${escapeHtml(String(item.line || "?"))}</span>
      `).join("")}
    </div>
  `;
}

function wireDiffJobButtons() {
  document.querySelectorAll(".diff-pane [data-open-job]").forEach((button) => {
    button.addEventListener("click", async () => {
      const jobId = button.dataset.openJob;
      if (!jobId) return;
      const data = await getJson(`/api/jobs/${jobId}`);
      state.currentJobId = jobId;
      renderJob(data.job);
      renderSavedJobs();
      document.querySelector(".report-pane")?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  });
}

async function loadSavedJobs() {
  try {
    const data = await getJson("/api/jobs");
    state.jobs = data.jobs || [];
    renderSavedJobs();
  } catch (error) {
    els.savedJobs.className = "saved-jobs empty";
    els.savedJobs.textContent = "Impossibile leggere le esecuzioni salvate.";
  }
}

function renderSavedJobs() {
  if (!state.jobs.length) {
    els.savedJobs.className = "saved-jobs empty";
    els.savedJobs.textContent = "Nessuna esecuzione salvata.";
    return;
  }

  els.savedJobs.className = "saved-jobs";
  els.savedJobs.innerHTML = state.jobs.map((job) => {
    const totalFindings = (job.results || []).reduce((sum, result) => sum + Number(result.findings || 0), 0);
    const active = job.id === state.currentJobId ? "active" : "";
    return `
      <article class="job-row ${active}">
        <div>
          <div class="job-title">${escapeHtml(formatDate(job.started_at))}</div>
          <div class="job-stats">
            <span>${escapeHtml(statusLabel(job.status))}</span>
            <span>${job.urls.length} repo</span>
            <span>${totalFindings} finding</span>
            <span>${escapeHtml(job.mode)}</span>
          </div>
        </div>
        <button type="button" data-open-job="${escapeHtml(job.id)}">Apri report</button>
      </article>
    `;
  }).join("");

  els.savedJobs.querySelectorAll("[data-open-job]").forEach((button) => {
    button.addEventListener("click", async () => {
      const jobId = button.dataset.openJob;
      const data = await getJson(`/api/jobs/${jobId}`);
      state.currentJobId = jobId;
      renderJob(data.job);
      renderSavedJobs();
      if (["queued", "running"].includes(data.job.status) || data.job.ai_status === "running") {
        startPolling();
      }
    });
  });
}

function renderJob(job) {
  els.globalStatus.textContent = statusLabel(job.status);
  els.reportTitle.textContent = job.status === "completed"
    ? "Scansione completata"
    : job.current
      ? `Verifica ${job.current}`
      : "Scansione in corso";
  const totals = jobTotals(job);
  els.jobMeta.textContent = `${job.results.length}/${job.urls.length} repo | ${totals.findings} finding | ${job.elapsed_seconds}s`;
  els.logs.textContent = (job.logs || []).join("\n");
  els.logs.scrollTop = els.logs.scrollHeight;

  if (!job.results.length) {
    els.reportResults.className = "report-results empty";
    els.reportResults.textContent = "In attesa del primo risultato.";
    return;
  }

  els.reportResults.className = "report-results";
  els.reportResults.innerHTML = renderJobSummary(job, totals) + renderAiAnalysis(job) + job.results.map(renderResult).join("");
  const aiButton = els.reportResults.querySelector("[data-generate-ai]");
  if (aiButton) {
    aiButton.addEventListener("click", () => generateAiAnalysis(job.id));
  }
}

async function generateAiAnalysis(jobId) {
  try {
    const data = await postJson(`/api/jobs/${jobId}/ai-analysis`, { ai: readAiConfig() });
    state.currentJobId = jobId;
    renderJob(data.job);
    startPolling();
  } catch (error) {
    els.reportResults.insertAdjacentHTML("afterbegin", `<div class="inline-error">${escapeHtml(error.message)}</div>`);
  }
}

function renderResult(result) {
  const badgeClass = result.status === "clean" ? "clean" : result.status === "findings" ? "findings" : "failed";
  const items = result.items && result.items.length
    ? result.items.map(renderFinding).join("")
    : `<div class="finding-path">${result.error ? escapeHtml(result.error) : "Nessun finding."}</div>`;

  return `
    <article class="summary-row">
      <div class="summary-head">
        <div>
          <strong>${escapeHtml(result.name)}</strong>
          <div class="selected-url">${escapeHtml(result.url)}</div>
        </div>
        <div class="summary-actions">
          ${result.report_url ? `<a class="button-link" href="${escapeHtml(result.report_url)}">Scarica JSON</a>` : ""}
          <span class="badge ${badgeClass}">${escapeHtml(statusLabel(result.status))} | ${result.findings}</span>
        </div>
      </div>
      ${items}
    </article>
  `;
}

function renderJobSummary(job, totals) {
  return `
    <section class="report-summary">
      <div>
        <span class="metric-value">${totals.repos}</span>
        <span class="metric-label">repository</span>
      </div>
      <div>
        <span class="metric-value">${totals.findings}</span>
        <span class="metric-label">finding totali</span>
      </div>
      <div>
        <span class="metric-value">${totals.clean}</span>
        <span class="metric-label">puliti</span>
      </div>
      <div>
        <span class="metric-value">${escapeHtml(statusLabel(job.status))}</span>
        <span class="metric-label">${escapeHtml(formatDate(job.started_at))}</span>
      </div>
      <div class="summary-download">
        <a class="button-link" href="/api/reports/${escapeHtml(job.id)}/summary.json">Scarica riepilogo</a>
      </div>
    </section>
  `;
}

function renderAiAnalysis(job) {
  const hasFindings = jobTotals(job).findings > 0;
  const status = job.ai_status || "not_started";
  const analysis = job.ai_analysis;
  const canGenerate = hasFindings && status !== "running";
  const buttonText = analysis ? "Rigenera analisi AI" : "Genera analisi AI";
  const body = analysis && analysis.content
    ? renderMarkdownEditor(job.id, analysis.content)
    : status === "running"
      ? `<div class="ai-content muted">Analisi in corso con LM Studio...</div>`
      : job.ai_error
        ? `<div class="inline-error">${escapeHtml(job.ai_error)}</div>`
        : `<div class="ai-content muted">${hasFindings ? "Nessuna analisi AI generata per questo report." : "Nessun finding da analizzare."}</div>`;
  const meta = analysis
    ? `<span>${escapeHtml(analysis.model || "modello locale")}</span><span>${escapeHtml(formatDate(analysis.generated_at))}</span>`
    : `<span>${escapeHtml(aiStatusLabel(status))}</span>`;

  return `
    <section class="ai-panel">
      <div class="ai-head">
        <div>
          <p class="eyebrow">Analisi AI locale</p>
          <h3>Triage assistito</h3>
          <div class="ai-meta">${meta}</div>
        </div>
        <button type="button" data-generate-ai="${escapeHtml(job.id)}" ${canGenerate ? "" : "disabled"}>
          ${escapeHtml(status === "running" ? "Analisi in corso" : buttonText)}
        </button>
      </div>
      ${body}
    </section>
  `;
}

function renderMarkdownEditor(jobId, content) {
  return `
    <div class="markdown-shell" data-md-document="${escapeHtml(jobId)}">
      <article class="markdown-body">${renderMarkdown(content)}</article>
    </div>
  `;
}

function cssEscape(value) {
  if (window.CSS && CSS.escape) return CSS.escape(value);
  return String(value).replaceAll('"', '\\"');
}

function aiStatusLabel(status) {
  return {
    not_started: "Non avviata",
    running: "In corso",
    completed: "Completata",
    failed: "Fallita",
  }[status] || status;
}

function renderMarkdown(text) {
  const lines = normalizeMarkdownDocument(text).replace(/\r\n?/g, "\n").split("\n");
  const html = [];
  let paragraph = [];
  let codeFence = null;
  let codeLines = [];

  function flushParagraph() {
    if (!paragraph.length) return;
    html.push(`<p>${inlineMarkdown(paragraph.join(" "))}</p>`);
    paragraph = [];
  }

  function flushCode() {
    if (!codeFence) return;
    const language = codeFence.language ? ` data-language="${escapeHtml(codeFence.language)}"` : "";
    html.push(`<pre${language}><code>${escapeHtml(codeLines.join("\n"))}</code></pre>`);
    codeFence = null;
    codeLines = [];
  }

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    const trimmed = line.trim();
    const fenceMatch = trimmed.match(/^```([A-Za-z0-9_-]+)?\s*$/);

    if (codeFence) {
      if (fenceMatch) {
        flushCode();
      } else {
        codeLines.push(line);
      }
      continue;
    }

    if (fenceMatch) {
      flushParagraph();
      codeFence = { language: fenceMatch[1] || "" };
      codeLines = [];
      continue;
    }

    if (!trimmed) {
      flushParagraph();
      continue;
    }

    if (/^---+$/.test(trimmed)) {
      flushParagraph();
      html.push("<hr>");
      continue;
    }

    const heading = trimmed.match(/^(#{1,6})\s+(.+)$/);
    if (heading) {
      flushParagraph();
      const level = Math.min(heading[1].length, 6);
      html.push(`<h${level}>${inlineMarkdown(heading[2])}</h${level}>`);
      continue;
    }

    if (isTableStart(lines, index)) {
      flushParagraph();
      const table = collectTable(lines, index);
      html.push(renderMarkdownTable(table.rows));
      index = table.nextIndex - 1;
      continue;
    }

    if (/^\s*[-*]\s+/.test(line)) {
      flushParagraph();
      const list = collectList(lines, index, "ul");
      html.push(renderMarkdownList(list.items, "ul"));
      index = list.nextIndex - 1;
      continue;
    }

    if (/^\s*\d+\.\s+/.test(line)) {
      flushParagraph();
      const list = collectList(lines, index, "ol");
      html.push(renderMarkdownList(list.items, "ol"));
      index = list.nextIndex - 1;
      continue;
    }

    if (/^\s*>\s?/.test(line)) {
      flushParagraph();
      const quote = collectBlockquote(lines, index);
      html.push(`<blockquote>${renderMarkdown(quote.lines.join("\n"))}</blockquote>`);
      index = quote.nextIndex - 1;
      continue;
    }

    paragraph.push(trimmed);
  }

  flushParagraph();
  flushCode();
  return html.join("");
}

function normalizeMarkdownDocument(text) {
  const source = String(text || "").trim();
  const fenced = source.match(/^```(?:markdown|md)?\s*\n([\s\S]*?)\n```\s*$/i);
  return fenced ? fenced[1].trim() : source;
}

function isTableStart(lines, index) {
  const current = lines[index] || "";
  const next = lines[index + 1] || "";
  return current.includes("|") && /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(next);
}

function collectTable(lines, index) {
  const rows = [splitTableRow(lines[index])];
  index += 2;
  while (index < lines.length && lines[index].includes("|") && lines[index].trim()) {
    rows.push(splitTableRow(lines[index]));
    index += 1;
  }
  return { rows, nextIndex: index };
}

function splitTableRow(line) {
  return line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((cell) => cell.trim());
}

function renderMarkdownTable(rows) {
  const header = rows[0] || [];
  const body = rows.slice(1);
  return `
    <div class="markdown-table-scroll">
      <table>
        <thead><tr>${header.map((cell) => `<th>${inlineMarkdown(cell)}</th>`).join("")}</tr></thead>
        <tbody>${body.map((row) => `<tr>${row.map((cell) => `<td>${inlineMarkdown(cell)}</td>`).join("")}</tr>`).join("")}</tbody>
      </table>
    </div>
  `;
}

function collectList(lines, index, type) {
  const pattern = type === "ol" ? /^\s*\d+\.\s+(.+)$/ : /^\s*[-*]\s+(.+)$/;
  const items = [];
  while (index < lines.length) {
    const match = lines[index].match(pattern);
    if (!match) break;
    items.push(match[1]);
    index += 1;
  }
  return { items, nextIndex: index };
}

function renderMarkdownList(items, type) {
  return `<${type}>${items.map((item) => `<li>${inlineMarkdown(item)}</li>`).join("")}</${type}>`;
}

function collectBlockquote(lines, index) {
  const quoteLines = [];
  while (index < lines.length && /^\s*>\s?/.test(lines[index])) {
    quoteLines.push(lines[index].replace(/^\s*>\s?/, ""));
    index += 1;
  }
  return { lines: quoteLines, nextIndex: index };
}

function inlineMarkdown(text) {
  const parts = String(text).split(/(`[^`]+`)/g);
  return parts.map((part) => {
    if (part.startsWith("`") && part.endsWith("`")) {
      return `<code>${escapeHtml(part.slice(1, -1))}</code>`;
    }
    return inlineText(part);
  }).join("");
}

function inlineText(text) {
  const source = String(text);
  const html = [];
  const linkPattern = /\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g;
  let cursor = 0;
  let match;

  while ((match = linkPattern.exec(source)) !== null) {
    html.push(inlineDecorations(source.slice(cursor, match.index)));
    html.push(`<a href="${escapeHtml(match[2])}" target="_blank" rel="noreferrer">${inlineDecorations(match[1])}</a>`);
    cursor = match.index + match[0].length;
  }

  html.push(inlineDecorations(source.slice(cursor)));
  return html.join("");
}

function inlineDecorations(text) {
  return escapeHtml(text)
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/__([^_]+)__/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*]+)\*/g, "$1<em>$2</em>")
    .replace(/(^|[^_])_([^_]+)_/g, "$1<em>$2</em>");
}

function renderFinding(item, index) {
  const title = `${item.rule} - ${item.file}:${item.line}`;
  return `
    <details class="finding-row" ${index === 0 ? "open" : ""}>
      <summary>
        <span>
          <strong>${escapeHtml(item.rule)}</strong>
          <span class="finding-path">${escapeHtml(item.file)}:${escapeHtml(String(item.line))}</span>
        </span>
        <span class="details-label">Dettagli</span>
      </summary>
      <dl class="finding-details">
        ${detailLine("Descrizione", item.description)}
        ${detailLine("Autore", item.author)}
        ${detailLine("Email", item.email)}
        ${detailLine("Data", item.date)}
        ${detailLine("Commit", item.commit)}
        ${detailLine("Fingerprint", item.fingerprint)}
        ${detailLine("Colonne", formatColumns(item))}
        ${item.link ? `<div><dt>Origine</dt><dd><a href="${escapeHtml(item.link)}" target="_blank" rel="noreferrer">Apri file alla riga</a></dd></div>` : ""}
      </dl>
    </details>
  `;
}

function detailLine(label, value) {
  if (!value) return "";
  return `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd></div>`;
}

function formatColumns(item) {
  if (!item.start_column && !item.end_column) return "";
  return `${item.start_column || "?"}-${item.end_column || "?"}`;
}

function jobTotals(job) {
  const results = job.results || [];
  return {
    repos: job.urls.length,
    findings: results.reduce((sum, result) => sum + Number(result.findings || 0), 0),
    clean: results.filter((result) => result.status === "clean").length,
  };
}

async function getJson(url) {
  const response = await fetch(url);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `Request failed: ${response.status}`);
  return data;
}

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `Request failed: ${response.status}`);
  return data;
}

function setSearchError(message) {
  els.searchError.hidden = !message;
  els.searchError.textContent = message;
}

function renderSkeleton(text) {
  return `<div class="empty">${escapeHtml(text)}</div>`;
}

function statusLabel(status) {
  return {
    queued: "In coda",
    running: "In corso",
    completed: "Completata",
    failed: "Fallita",
    clean: "Pulito",
    findings: "Finding",
    clone_failed: "Clone fallito",
    scan_failed: "Scan fallita",
  }[status] || status;
}

function riskLabel(level) {
  return {
    critical: "Critico",
    high: "Alto",
    medium: "Medio",
    low: "Basso",
    clean: "Pulito",
  }[level] || level;
}

function formatNumber(value) {
  return Number(value || 0).toLocaleString("it-IT");
}

function repoNameFromUrl(url) {
  try {
    const parsed = new URL(url);
    return parsed.pathname.replace(/^\/|\.git$/g, "") || url;
  } catch {
    return url;
  }
}

function providerLabel(url) {
  try {
    const parsed = new URL(url);
    if (parsed.hostname === "bitbucket.org") return "Bitbucket";
    if (parsed.hostname === "github.com") return "GitHub";
    return parsed.hostname;
  } catch {
    return "Repository";
  }
}

function formatDate(timestamp) {
  if (!timestamp) return "Data non disponibile";
  return new Date(timestamp * 1000).toLocaleString("it-IT", {
    dateStyle: "short",
    timeStyle: "medium",
  });
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

renderSelected();
loadSavedJobs();
loadDashboard();
loadDiffs();
loadGithubStatus();
loadLmStudioStatus();

<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import { getAiStatus, getJob, startScan } from '$lib/api';
  import { formatNumber, statusLabel } from '$lib/format';
  import { staging } from '$lib/staging';
  import type { AiStatus, ScanJobDetail, ScanPayload } from '$lib/types';

  const defaultSystemPrompt =
    "Sei un senior application security engineer. Analizza finding Gitleaks gia' redatti. Non inventare secret e non affermare che una credenziale sia valida se non puoi verificarlo. Scrivi in italiano, con tono operativo e conciso.";

  let mode: ScanPayload['mode'] = 'git';
  let timeout = 300;
  let autoAnalyze = true;
  let selectedModel = '';
  let systemPrompt = defaultSystemPrompt;
  let additionalInstructions = '';
  let aiStatus: AiStatus | null = null;
  let aiLoading = true;
  let aiError = '';
  let launching = false;
  let launchError = '';
  let activeJob: ScanJobDetail | null = null;
  let poller: ReturnType<typeof setInterval> | null = null;

  async function loadAiStatus() {
    aiLoading = true;
    aiError = '';
    try {
      aiStatus = await getAiStatus();
      selectedModel = aiStatus.selected_model || '';
    } catch (err) {
      aiError = err instanceof Error ? err.message : 'Errore verifica LM Studio';
    } finally {
      aiLoading = false;
    }
  }

  async function launchScan() {
    if (!$staging.length || launching) return;
    launching = true;
    launchError = '';
    try {
      activeJob = await startScan({
        urls: $staging.map((repo) => repo.url),
        mode,
        timeout: Number(timeout || 0),
        ai: {
          model: selectedModel,
          auto_analyze: autoAnalyze,
          system_prompt: systemPrompt,
          additional_instructions: additionalInstructions
        }
      });
      startPolling(activeJob.id);
    } catch (err) {
      launchError = err instanceof Error ? err.message : 'Errore avvio scansione';
    } finally {
      launching = false;
    }
  }

  function startPolling(jobId: string) {
    stopPolling();
    poller = setInterval(() => refreshJob(jobId), 1800);
    refreshJob(jobId);
  }

  async function refreshJob(jobId: string) {
    try {
      activeJob = await getJob(jobId);
      if (activeJob && ['completed', 'failed'].includes(activeJob.status) && activeJob.ai_status !== 'running') {
        stopPolling();
      }
    } catch (err) {
      launchError = err instanceof Error ? err.message : 'Errore aggiornamento job';
      stopPolling();
    }
  }

  function stopPolling() {
    if (poller) {
      clearInterval(poller);
      poller = null;
    }
  }

  onMount(loadAiStatus);
  onDestroy(stopPolling);
</script>

<section class="page-head">
  <div>
    <p class="eyebrow">Scansione</p>
    <h2>Setup Gitleaks e LM Studio</h2>
  </div>
  <button class="ghost" type="button" on:click={loadAiStatus}>Aggiorna LM Studio</button>
</section>

<section class="scan-layout">
  <div class="stack">
    <section class="panel">
      <div class="section-title">
        <h3>Modalita' Gitleaks</h3>
        <span>{formatNumber($staging.length)} repo in pitlane</span>
      </div>
      <div class="control-grid">
        <label>
          Modalita'
          <select bind:value={mode}>
            <option value="git">Storia Git completa</option>
            <option value="dir">Solo file correnti</option>
          </select>
        </label>
        <label>
          Timeout per repo
          <input bind:value={timeout} type="number" min="0" step="30" />
        </label>
      </div>
      {#if $staging.length === 0}
        <div class="empty">Aggiungi repository dalla pagina Repository prima di avviare una scansione.</div>
      {:else}
        <div class="launch-list">
          {#each $staging as repo}
            <article class="mini-row">
              <strong>{repo.name}</strong>
              <span>{repo.url}</span>
            </article>
          {/each}
        </div>
      {/if}
    </section>

    <section class="panel">
      <div class="section-title">
        <h3>LM Studio</h3>
        {#if aiLoading}
          <span>Verifica in corso</span>
        {:else if aiStatus?.available}
          <span>{aiStatus.base_url}</span>
        {:else}
          <span>Non pronto</span>
        {/if}
      </div>

      {#if aiError}
        <div class="inline-error">{aiError}</div>
      {:else if aiStatus}
        <div class:status-ok={aiStatus.available} class:status-warn={!aiStatus.available} class="lm-banner">
          {aiStatus.available
            ? `Connesso. Modello default: ${aiStatus.selected_model || 'automatico'}`
            : `LM Studio non disponibile: ${aiStatus.error || 'nessun modello chat'}`}
        </div>
      {/if}

      <div class="control-grid">
        <label>
          Modello AI
          <select bind:value={selectedModel}>
            <option value="">Automatico</option>
            {#each (aiStatus?.models || []).filter((model) => !/embed|embedding|reranker/i.test(model)) as model}
              <option value={model}>{model}</option>
            {/each}
          </select>
        </label>
        <label class="toggle-row">
          <input bind:checked={autoAnalyze} type="checkbox" />
          <span>Genera analisi AI a fine scan</span>
        </label>
      </div>

      <label class="field-stack">
        System prompt
        <textarea bind:value={systemPrompt} rows="4"></textarea>
      </label>
      <label class="field-stack">
        Specifiche addizionali
        <textarea bind:value={additionalInstructions} rows="4" placeholder="Esempio: privilegia falsi positivi, sintetizza per CTO, raggruppa per team."></textarea>
      </label>
    </section>
  </div>

  <aside class="stack">
    <section class="panel launch-panel">
      <p class="eyebrow">Lancio</p>
      <h3>Verifica lista corrente</h3>
      <p class="muted">La scansione usa i repository nella pitlane e salva il report nello storico persistente.</p>
      <button class="full-width" type="button" disabled={!$staging.length || launching} on:click={launchScan}>
        {launching ? 'Avvio in corso' : 'Avvia verifica'}
      </button>
      {#if launchError}
        <div class="inline-error">{launchError}</div>
      {/if}
    </section>

    {#if activeJob}
      <section class="panel job-card">
        <div class="section-title">
          <h3>Job attivo</h3>
          <span>{statusLabel(activeJob.status)}</span>
        </div>
        <div class="job-stats">
          <div><strong>{formatNumber(activeJob.results.length)}</strong><span>Repo conclusi</span></div>
          <div><strong>{formatNumber(activeJob.results.reduce((sum, result) => sum + Number(result.findings || 0), 0))}</strong><span>Finding</span></div>
          <div><strong>{formatNumber(activeJob.elapsed_seconds)}</strong><span>Secondi</span></div>
        </div>
        {#if activeJob.current}
          <p class="muted">In corso: {activeJob.current}</p>
        {/if}
        {#if activeJob.ai_status}
          <p class="muted">AI: {statusLabel(activeJob.ai_status)}</p>
        {/if}
        {#if activeJob.error || activeJob.ai_error}
          <div class="inline-error">{activeJob.error || activeJob.ai_error}</div>
        {/if}
        <div class="log-box">
          {#each activeJob.logs.slice(-8) as line}
            <span>{line}</span>
          {/each}
        </div>
        <a class="button-link" href="/reports">Apri archivio report</a>
      </section>
    {:else}
      <section class="panel">
        <div class="section-title">
          <h3>Ultimo step</h3>
          <span>Pronto</span>
        </div>
        <p class="muted">Quando avvii una verifica, qui vedrai avanzamento, log essenziali e link al report finale.</p>
      </section>
    {/if}
  </aside>
</section>

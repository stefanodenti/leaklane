<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import { generateAiAnalysis, getJob, getJobs } from '$lib/api';
  import { formatDate, formatNumber, statusLabel } from '$lib/format';
  import { renderMarkdown } from '$lib/markdown';
  import type { FindingDetail, JobPreview, JobResult, ScanJobDetail } from '$lib/types';

  let jobs: JobPreview[] = [];
  let selectedJob: ScanJobDetail | null = null;
  let selectedId = '';
  let loading = true;
  let detailLoading = false;
  let aiRunning = false;
  let error = '';
  let detailError = '';
  let poller: ReturnType<typeof setInterval> | null = null;

  async function loadJobs(preferredId = selectedId) {
    loading = true;
    error = '';
    try {
      jobs = await getJobs();
      const nextId = preferredId || jobs[0]?.id || '';
      if (nextId) {
        await selectJob(nextId, false);
      } else {
        selectedJob = null;
      }
    } catch (err) {
      error = err instanceof Error ? err.message : 'Errore caricamento report';
    } finally {
      loading = false;
    }
  }

  async function selectJob(jobId: string, showLoading = true) {
    selectedId = jobId;
    detailError = '';
    if (showLoading) detailLoading = true;
    try {
      selectedJob = await getJob(jobId);
      updatePolling();
    } catch (err) {
      detailError = err instanceof Error ? err.message : 'Errore caricamento dettaglio';
    } finally {
      detailLoading = false;
    }
  }

  async function refreshSelected() {
    if (!selectedId) return;
    await selectJob(selectedId, false);
  }

  async function runAi() {
    if (!selectedJob || aiRunning) return;
    aiRunning = true;
    detailError = '';
    try {
      selectedJob = await generateAiAnalysis(selectedJob.id);
      updatePolling();
    } catch (err) {
      detailError = err instanceof Error ? err.message : 'Errore generazione analisi AI';
    } finally {
      aiRunning = false;
    }
  }

  function updatePolling() {
    stopPolling();
    if (selectedJob && (['queued', 'running'].includes(selectedJob.status) || selectedJob.ai_status === 'running')) {
      poller = setInterval(refreshSelected, 2200);
    }
  }

  function stopPolling() {
    if (poller) {
      clearInterval(poller);
      poller = null;
    }
  }

  function totalFindings(job: JobPreview | ScanJobDetail) {
    return (job.results || []).reduce((sum, result) => sum + Number(result.findings || 0), 0);
  }

  function cleanCount(job: ScanJobDetail) {
    return job.results.filter((result) => result.status === 'clean').length;
  }

  function canGenerateAi(job: ScanJobDetail) {
    return totalFindings(job) > 0 && job.ai_status !== 'running';
  }

  function resultBadgeClass(result: JobResult) {
    if (result.status === 'clean') return 'status-ok';
    if (result.status === 'findings') return 'status-warn';
    return 'risk-critical';
  }

  function findingTitle(item: FindingDetail) {
    return `${item.rule || 'unknown-rule'} - ${item.file || 'unknown-file'}:${item.line || '?'}`;
  }

  function findingColumns(item: FindingDetail) {
    if (!item.start_column && !item.end_column) return '';
    return `${item.start_column || '?'}-${item.end_column || '?'}`;
  }

  onMount(() => loadJobs());
  onDestroy(stopPolling);
</script>

<section class="page-head">
  <div>
    <p class="eyebrow">Report</p>
    <h2>Archivio verifiche</h2>
  </div>
  <button class="ghost" type="button" on:click={() => loadJobs()}>Aggiorna</button>
</section>

{#if loading}
  <div class="empty">Caricamento report.</div>
{:else if error}
  <div class="inline-error">{error}</div>
{:else if jobs.length === 0}
  <div class="empty">Nessun report disponibile. Avvia una scansione per popolare l'archivio.</div>
{:else}
  <section class="report-layout">
    <aside class="report-index panel">
      <div class="section-title">
        <h3>Esecuzioni</h3>
        <span>{formatNumber(jobs.length)} job</span>
      </div>
      <div class="job-list">
        {#each jobs as job}
          <button class:active={job.id === selectedId} class="job-list-item" type="button" on:click={() => selectJob(job.id)}>
            <span>
              <strong>{formatDate(job.started_at)}</strong>
              <small>{statusLabel(job.status)} | {formatNumber(job.urls.length)} repo</small>
            </span>
            <em>{formatNumber(totalFindings(job))}</em>
          </button>
        {/each}
      </div>
    </aside>

    <div class="report-detail">
      {#if detailLoading}
        <div class="empty">Caricamento dettaglio report.</div>
      {:else if detailError}
        <div class="inline-error">{detailError}</div>
      {:else if selectedJob}
        <section class="panel report-hero">
          <div>
            <p class="eyebrow">Job {selectedJob.id}</p>
            <h3>{statusLabel(selectedJob.status)}</h3>
            <p class="muted">{formatDate(selectedJob.started_at)} | {selectedJob.mode} | {formatNumber(selectedJob.elapsed_seconds)} secondi</p>
          </div>
          <a class="button-link" href={`/api/reports/${selectedJob.id}/summary.json`}>Scarica riepilogo</a>
        </section>

        <section class="report-summary-grid">
          <div class="metric"><strong>{formatNumber(selectedJob.urls.length)}</strong><span>Repository</span></div>
          <div class="metric"><strong>{formatNumber(totalFindings(selectedJob))}</strong><span>Finding totali</span></div>
          <div class="metric"><strong>{formatNumber(cleanCount(selectedJob))}</strong><span>Repo puliti</span></div>
          <div class="metric"><strong>{statusLabel(selectedJob.ai_status)}</strong><span>Analisi AI</span></div>
        </section>

        <section class="panel ai-report-panel">
          <div class="section-title">
            <div>
              <p class="eyebrow">Analisi AI locale</p>
              <h3>Triage assistito</h3>
            </div>
            <button type="button" disabled={!canGenerateAi(selectedJob) || aiRunning} on:click={runAi}>
              {selectedJob.ai_status === 'running' || aiRunning
                ? 'Analisi in corso'
                : selectedJob.ai_analysis?.content
                  ? 'Rigenera analisi'
                  : 'Genera analisi'}
            </button>
          </div>

          {#if selectedJob.ai_analysis?.content}
            <div class="ai-meta">
              <span>{selectedJob.ai_analysis.model || 'modello locale'}</span>
              <span>{formatDate(selectedJob.ai_analysis.generated_at)}</span>
            </div>
            <article class="markdown-body">
              {@html renderMarkdown(selectedJob.ai_analysis.content)}
            </article>
          {:else if selectedJob.ai_status === 'running'}
            <div class="empty">Analisi in corso con LM Studio.</div>
          {:else if selectedJob.ai_error}
            <div class="inline-error">{selectedJob.ai_error}</div>
          {:else}
            <div class="empty">
              {totalFindings(selectedJob) > 0 ? 'Nessuna analisi AI generata per questo report.' : 'Nessun finding da analizzare.'}
            </div>
          {/if}
        </section>

        <section class="stack">
          {#each selectedJob.results as result}
            <article class="panel result-card">
              <div class="result-head">
                <div>
                  <h3>{result.name}</h3>
                  <p class="muted">{result.url}</p>
                </div>
                <div class="result-actions">
                  {#if result.report_url}
                    <a class="button-link" href={result.report_url}>Scarica JSON</a>
                  {/if}
                  <span class={resultBadgeClass(result)}>{statusLabel(result.status)} | {formatNumber(result.findings)}</span>
                </div>
              </div>

              {#if result.error}
                <div class="inline-error">{result.error}</div>
              {:else if !result.items?.length}
                <div class="empty">Nessun finding.</div>
              {:else}
                <div class="finding-list">
                  {#each result.items as item, index}
                    <details class="finding-row" open={index === 0}>
                      <summary>
                        <span>
                          <strong>{item.rule}</strong>
                          <small>{item.file}:{item.line}</small>
                        </span>
                        <em>Dettagli</em>
                      </summary>
                      <dl class="finding-details" aria-label={findingTitle(item)}>
                        {#if item.description}<div><dt>Descrizione</dt><dd>{item.description}</dd></div>{/if}
                        {#if item.author}<div><dt>Autore</dt><dd>{item.author}</dd></div>{/if}
                        {#if item.email}<div><dt>Email</dt><dd>{item.email}</dd></div>{/if}
                        {#if item.date}<div><dt>Data</dt><dd>{item.date}</dd></div>{/if}
                        {#if item.commit}<div><dt>Commit</dt><dd>{item.commit}</dd></div>{/if}
                        {#if item.fingerprint}<div><dt>Fingerprint</dt><dd>{item.fingerprint}</dd></div>{/if}
                        {#if findingColumns(item)}<div><dt>Colonne</dt><dd>{findingColumns(item)}</dd></div>{/if}
                        {#if item.link}<div><dt>Origine</dt><dd><a href={item.link} target="_blank" rel="noreferrer">Apri file alla riga</a></dd></div>{/if}
                      </dl>
                    </details>
                  {/each}
                </div>
              {/if}
            </article>
          {/each}
        </section>
      {/if}
    </div>
  </section>
{/if}

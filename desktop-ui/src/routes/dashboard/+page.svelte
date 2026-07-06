<script lang="ts">
  import { onMount } from 'svelte';
  import { getDashboard } from '$lib/api';
  import { formatDate, formatNumber, riskLabel, statusLabel } from '$lib/format';
  import type { DashboardMetric } from '$lib/types';

  let dashboard: DashboardMetric | null = null;
  let loading = true;
  let error = '';

  async function loadDashboard() {
    loading = true;
    error = '';
    try {
      dashboard = await getDashboard();
    } catch (err) {
      error = err instanceof Error ? err.message : 'Errore caricamento dashboard';
    } finally {
      loading = false;
    }
  }

  onMount(loadDashboard);
</script>

<section class="page-head">
  <div>
    <p class="eyebrow">Risk dashboard</p>
    <h2>Quadro organizzazioni</h2>
  </div>
  <button class="ghost" type="button" on:click={loadDashboard}>Aggiorna</button>
</section>

{#if loading}
  <div class="empty">Caricamento dashboard.</div>
{:else if error}
  <div class="inline-error">{error}</div>
{:else if dashboard}
  <section class="metric-grid">
    <div class="metric"><strong>{formatNumber(dashboard.summary.organizations)}</strong><span>Organizzazioni</span></div>
    <div class="metric"><strong>{formatNumber(dashboard.summary.repositories)}</strong><span>Repository</span></div>
    <div class="metric"><strong>{formatNumber(dashboard.summary.findings)}</strong><span>Finding attivi</span></div>
    <div class="metric"><strong>{formatNumber(dashboard.summary.risky_repositories)}</strong><span>Repo esposti</span></div>
    <div class="metric"><strong>{formatNumber(dashboard.summary.jobs)}</strong><span>Esecuzioni</span></div>
  </section>

  <section class="dashboard-grid">
    <div class="panel span-wide">
      <div class="section-title">
        <h3>Organizzazioni</h3>
        <span>Aggiornato {formatDate(dashboard.updated_at)}</span>
      </div>
      <div class="stack">
        {#each dashboard.organizations as org}
          <article class="org-row">
            <div class="row-head">
              <div>
                <h4>{org.name}</h4>
                <p>{org.provider} | {formatNumber(org.repositories)} repo | {formatNumber(org.findings)} finding</p>
              </div>
              <span class:risk-critical={org.risk_level === 'critical'} class:risk-high={org.risk_level === 'high'} class:risk-clean={org.risk_level === 'clean'} class="risk-pill">
                {riskLabel(org.risk_level)}
              </span>
            </div>
            <div class="severity-line">
              <span>Critici {formatNumber(org.severity.critical)}</span>
              <span>Alti {formatNumber(org.severity.high)}</span>
              <span>Medi {formatNumber(org.severity.medium)}</span>
              <span>Bassi {formatNumber(org.severity.low)}</span>
            </div>
            <div class="rule-line">
              {#each org.top_rules as rule}
                <span>{rule[0]} <strong>{formatNumber(rule[1])}</strong></span>
              {/each}
            </div>
          </article>
        {/each}
      </div>
    </div>

    <div class="panel">
      <div class="section-title">
        <h3>Hotspot</h3>
        <span>Repository piu' esposti</span>
      </div>
      <div class="stack compact">
        {#each dashboard.hotspots as repo}
          <article class="mini-row">
            <strong>{repo.name}</strong>
            <span>{repo.organization} | {formatNumber(repo.findings)} finding</span>
          </article>
        {/each}
      </div>
    </div>

    <div class="panel">
      <div class="section-title">
        <h3>Trend recente</h3>
        <span>Ultime esecuzioni</span>
      </div>
      <div class="stack compact">
        {#each dashboard.timeline as job}
          <article class="mini-row">
            <strong>{formatDate(job.started_at)}</strong>
            <span>{statusLabel(job.status)} | {formatNumber(job.repositories)} repo | {formatNumber(job.findings)} finding</span>
          </article>
        {/each}
      </div>
    </div>
  </section>
{/if}

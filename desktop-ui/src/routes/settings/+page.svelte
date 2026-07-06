<script lang="ts">
  import { onMount } from 'svelte';
  import { getPrerequisites } from '$lib/api';
  import type { CommandCheck, PrerequisitesStatus } from '$lib/types';

  let status: PrerequisitesStatus | null = null;
  let loading = true;
  let error = '';

  async function loadStatus() {
    loading = true;
    error = '';
    try {
      status = await getPrerequisites();
    } catch (err) {
      error = err instanceof Error ? err.message : 'Errore verifica configurazione locale';
    } finally {
      loading = false;
    }
  }

  function checkLabel(check: CommandCheck) {
    if (check.installed && !check.error) return 'Pronto';
    if (check.installed) return 'Da verificare';
    return check.required ? 'Richiesto' : 'Opzionale';
  }

  function checkTone(check: CommandCheck) {
    if (check.installed && !check.error) return 'status-ok';
    if (check.required) return 'risk-critical';
    return 'status-warn';
  }

  onMount(loadStatus);
</script>

<section class="page-head">
  <div>
    <p class="eyebrow">Settings</p>
    <h2>Configurazione locale</h2>
  </div>
  <button class="ghost" type="button" on:click={loadStatus}>Aggiorna controlli</button>
</section>

{#if loading}
  <div class="empty">Verifica configurazione locale.</div>
{:else if error}
  <div class="inline-error">{error}</div>
{:else if status}
  <section class="settings-hero panel">
    <div>
      <p class="eyebrow">Desktop readiness</p>
      <h3>{status.ready ? 'Ambiente pronto per le scansioni' : 'Mancano alcuni prerequisiti'}</h3>
      <p class="muted">Backend locale: {status.backend_url}</p>
      <p class="muted">Archivio report: {status.reports_dir}</p>
    </div>
    <span class:status-ok={status.ready} class:risk-critical={!status.ready} class="status-chip">
      {status.ready ? 'Pronto' : 'Attenzione'}
    </span>
  </section>

  <section class="settings-grid">
    {#each Object.entries(status.checks) as [name, check]}
      <article class="panel tool-card">
        <div class="section-title">
          <h3>{name}</h3>
          <span class={checkTone(check)}>{checkLabel(check)}</span>
        </div>
        <p class="muted">{check.version || check.error || 'Non installato'}</p>
        {#if check.path}
          <code>{check.path}</code>
        {/if}
      </article>
    {/each}
  </section>

  <section class="settings-grid two">
    <article class="panel tool-card">
      <div class="section-title">
        <h3>GitHub CLI</h3>
        <span class:status-ok={status.github.ready} class:status-warn={!status.github.ready}>
          {status.github.ready ? 'Collegata' : 'Non collegata'}
        </span>
      </div>
      <p class="muted">
        {status.github.ready
          ? `Account attivo: ${status.github.account || 'sessione locale'}`
          : status.github.message}
      </p>
      {#if !status.github.ready}
        <code>{status.github.setup_command}</code>
      {/if}
    </article>

    <article class="panel tool-card">
      <div class="section-title">
        <h3>LM Studio</h3>
        <span class:status-ok={status.lm_studio.available} class:status-warn={!status.lm_studio.available}>
          {status.lm_studio.available ? 'Raggiungibile' : 'Non pronto'}
        </span>
      </div>
      <p class="muted">{status.lm_studio.base_url}</p>
      <p class="muted">
        {status.lm_studio.available
          ? `Modello default: ${status.lm_studio.selected_model || 'automatico'}`
          : status.lm_studio.error || 'Nessun modello chat disponibile'}
      </p>
    </article>
  </section>

  <section class="panel desktop-notes">
    <div>
      <h3>Build desktop</h3>
      <p class="muted">Tauri avviera' il backend Python locale se la porta 8787 non risponde. In produzione i report saranno salvati nella cartella dati dell'app.</p>
    </div>
    <div class="note-grid">
      <span>UI statica SvelteKit</span>
      <span>Backend locale Python</span>
      <span>Gitleaks installato nel sistema</span>
      <span>LM Studio opzionale</span>
    </div>
  </section>
{/if}

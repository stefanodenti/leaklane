<script lang="ts">
  import { onMount } from 'svelte';
  import { getGithubStatus, searchRepositories } from '$lib/api';
  import { formatNumber } from '$lib/format';
  import { staging } from '$lib/staging';
  import type { GithubStatus, SearchResult } from '$lib/types';

  let status: GithubStatus | null = null;
  let statusLoading = true;
  let statusError = '';
  let query = '';
  let searching = false;
  let searchError = '';
  let results: SearchResult[] = [];
  let manualUrl = '';

  async function loadGithubStatus() {
    statusLoading = true;
    statusError = '';
    try {
      status = await getGithubStatus();
    } catch (err) {
      statusError = err instanceof Error ? err.message : 'Errore verifica GitHub CLI';
    } finally {
      statusLoading = false;
    }
  }

  async function submitSearch() {
    const cleanQuery = query.trim();
    if (!cleanQuery) return;
    searching = true;
    searchError = '';
    results = [];
    try {
      results = await searchRepositories(cleanQuery);
    } catch (err) {
      searchError = err instanceof Error ? err.message : 'Errore ricerca repository';
    } finally {
      searching = false;
    }
  }

  function addManual() {
    const url = manualUrl.trim();
    if (!url) return;
    staging.add({
      name: repoNameFromUrl(url),
      url,
      description: 'Aggiunto manualmente',
      provider: providerLabel(url)
    });
    manualUrl = '';
  }

  function alreadyStaged(url: string) {
    return $staging.some((item) => item.url === url);
  }

  function repoNameFromUrl(url: string) {
    try {
      const parsed = new URL(url);
      return parsed.pathname.replace(/^\/|\.git$/g, '') || url;
    } catch {
      return url;
    }
  }

  function providerLabel(url: string) {
    try {
      const parsed = new URL(url);
      if (parsed.hostname === 'github.com') return 'GitHub';
      if (parsed.hostname === 'bitbucket.org') return 'Bitbucket';
      return parsed.hostname;
    } catch {
      return 'Repository';
    }
  }

  onMount(() => {
    loadGithubStatus();
  });
</script>

<section class="page-head">
  <div>
    <p class="eyebrow">Repository</p>
    <h2>Pitlane e ricerca</h2>
  </div>
  <button class="ghost" type="button" on:click={loadGithubStatus}>Verifica GitHub</button>
</section>

<section class="repository-layout">
  <div class="stack">
    <section class="panel access-panel">
      <div class="row-head">
        <div>
          <p class="eyebrow">GitHub CLI</p>
          {#if statusLoading}
            <h3>Verifica in corso</h3>
            <p class="muted">Controllo sessione locale.</p>
          {:else if statusError}
            <h3>Controllo non riuscito</h3>
            <p class="muted">{statusError}</p>
          {:else if status?.ready}
            <h3>GitHub collegato{status.account ? ` come ${status.account}` : ''}</h3>
            <p class="muted">La ricerca include anche repository privati accessibili dalla CLI locale.</p>
          {:else if status?.installed}
            <h3>GitHub CLI non collegata</h3>
            <p class="muted">Per abilitare i repository privati esegui: {status.setup_command}</p>
          {:else}
            <h3>GitHub CLI non trovata</h3>
            <p class="muted">Installa GitHub CLI e poi collega l'account locale.</p>
          {/if}
        </div>
        <span class:status-ok={status?.ready} class:status-warn={!status?.ready} class="status-chip">
          {status?.ready ? 'Pronta' : 'Limitata'}
        </span>
      </div>
    </section>

    <section class="panel">
      <form class="search-panel" on:submit|preventDefault={submitSearch}>
        <label for="repoQuery">Cerca repository GitHub</label>
        <div class="input-row">
          <input id="repoQuery" bind:value={query} type="search" placeholder="owner/repo, organizzazione, framework..." autocomplete="off" />
          <button type="submit" disabled={searching}>{searching ? 'Ricerca' : 'Cerca'}</button>
        </div>
        <p class="muted">Con GitHub CLI collegata, i risultati possono includere repository privati accessibili dal tuo account.</p>
      </form>

      {#if searchError}
        <div class="inline-error">{searchError}</div>
      {/if}

      <div class="result-stack">
        {#if searching}
          <div class="empty">Ricerca in corso.</div>
        {:else if results.length === 0}
          <div class="empty">Cerca un repository per aggiungerlo alla pitlane.</div>
        {:else}
          {#each results as repo}
            <article class="repo-result">
              <div>
                <h3>{repo.name}</h3>
                <p>{repo.description || 'Nessuna descrizione disponibile.'}</p>
                <div class="repo-tags">
                  <span>{repo.language || 'Unknown'}</span>
                  <span>{repo.provider || providerLabel(repo.url)}</span>
                  {#if repo.visibility}<span>{repo.visibility}</span>{/if}
                  {#if repo.stars !== null && repo.stars !== undefined}<span>{formatNumber(repo.stars)} stelle</span>{/if}
                </div>
              </div>
              <button type="button" disabled={alreadyStaged(repo.url)} on:click={() => staging.add(repo)}>
                {alreadyStaged(repo.url) ? 'In pitlane' : 'Aggiungi'}
              </button>
            </article>
          {/each}
        {/if}
      </div>
    </section>
  </div>

  <aside class="stack">
    <section class="panel">
      <div class="section-title">
        <h3>URL manuale</h3>
        <span>GitHub o Bitbucket</span>
      </div>
      <div class="input-row single">
        <input bind:value={manualUrl} type="url" placeholder="https://github.com/owner/repo" />
        <button type="button" on:click={addManual}>Aggiungi</button>
      </div>
    </section>

    <section class="panel">
      <div class="section-title">
        <h3>Pitlane</h3>
        <span>{formatNumber($staging.length)} repository</span>
      </div>

      {#if $staging.length === 0}
        <div class="empty">Nessun repository in lista.</div>
      {:else}
        <div class="staging-list">
          {#each $staging as repo}
            <article class="staged-row">
              <div>
                <strong>{repo.name}</strong>
                <span>{repo.url}</span>
              </div>
              <button class="ghost" type="button" on:click={() => staging.remove(repo.url)}>Rimuovi</button>
            </article>
          {/each}
        </div>
        <button class="full-width ghost" type="button" on:click={() => staging.clear()}>Svuota pitlane</button>
      {/if}
    </section>
  </aside>
</section>

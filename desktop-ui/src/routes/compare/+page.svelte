<script lang="ts">
  import { onMount } from 'svelte';
  import { getDiffs } from '$lib/api';
  import { formatDate, formatNumber } from '$lib/format';
  import type { DiffResponse } from '$lib/types';

  let diffs: DiffResponse | null = null;
  let loading = true;
  let error = '';

  async function loadDiffs() {
    loading = true;
    error = '';
    try {
      diffs = await getDiffs();
    } catch (err) {
      error = err instanceof Error ? err.message : 'Errore caricamento confronti';
    } finally {
      loading = false;
    }
  }

  onMount(loadDiffs);
</script>

<section class="page-head">
  <div>
    <p class="eyebrow">Scan diff</p>
    <h2>Confronti tra scansioni</h2>
  </div>
  <button class="ghost" type="button" on:click={loadDiffs}>Aggiorna</button>
</section>

{#if loading}
  <div class="empty">Caricamento confronti.</div>
{:else if error}
  <div class="inline-error">{error}</div>
{:else if diffs}
  <section class="metric-grid">
    <div class="metric"><strong>{formatNumber(diffs.summary.repositories)}</strong><span>Repo confrontati</span></div>
    <div class="metric"><strong>{formatNumber(diffs.summary.new)}</strong><span>Nuovi finding</span></div>
    <div class="metric"><strong>{formatNumber(diffs.summary.resolved)}</strong><span>Risolti</span></div>
    <div class="metric"><strong>{formatNumber(diffs.summary.unchanged)}</strong><span>Invariati</span></div>
    <div class="metric"><strong>{formatNumber(diffs.summary.new - diffs.summary.resolved)}</strong><span>Saldo</span></div>
  </section>

  {#if diffs.comparisons.length === 0}
    <div class="empty">Serve almeno una seconda scansione dello stesso repository per calcolare il delta.</div>
  {:else}
    <div class="stack">
      {#each diffs.comparisons as item}
        <article class="panel">
          <div class="row-head">
            <div>
              <h3>{item.repository}</h3>
              <p>{item.organization} | {formatDate(item.previous_at)} -> {formatDate(item.latest_at)}</p>
            </div>
            <div class="counter-line">
              <span class="risk-critical">Nuovi {formatNumber(item.new)}</span>
              <span class="risk-clean">Risolti {formatNumber(item.resolved)}</span>
              <span>Invariati {formatNumber(item.unchanged)}</span>
            </div>
          </div>
        </article>
      {/each}
    </div>
  {/if}
{/if}

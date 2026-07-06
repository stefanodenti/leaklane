<script lang="ts">
  import { browser } from '$app/environment';
  import { page } from '$app/state';
  import { onMount } from 'svelte';
  import '../app.css';

  const navItems = [
    { href: '/dashboard', label: 'Dashboard', kicker: 'Rischio', short: 'DB' },
    { href: '/repositories', label: 'Repository', kicker: 'Pitlane', short: 'RP' },
    { href: '/scan', label: 'Scansione', kicker: 'Setup', short: 'SC' },
    { href: '/reports', label: 'Report', kicker: 'Archivio', short: 'RE' },
    { href: '/compare', label: 'Confronti', kicker: 'Delta', short: 'DF' },
    { href: '/map', label: 'Mappa Repo', kicker: 'Struttura', short: 'MP' },
    { href: '/settings', label: 'Settings', kicker: 'Locale', short: 'ST' }
  ];
  const backendUrl = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8787';
  const backendLabel = backendUrl.replace(/^https?:\/\//, '');

  let sidebarCollapsed = false;

  onMount(() => {
    sidebarCollapsed = localStorage.getItem('leaklane-sidebar') === 'collapsed';
  });

  function toggleSidebar() {
    sidebarCollapsed = !sidebarCollapsed;
    if (browser) {
      localStorage.setItem('leaklane-sidebar', sidebarCollapsed ? 'collapsed' : 'expanded');
    }
  }
</script>

<svelte:head>
  <title>LeakLane</title>
  <meta
    name="description"
    content="Local secret triage for repository fleets with Gitleaks and LM Studio."
  />
</svelte:head>

<div class:sidebar-collapsed={sidebarCollapsed} class="app-shell">
  <aside class="sidebar">
    <div class="sidebar-top">
      <div class="brand">
        <span class="brand-mark" aria-hidden="true">
          <img src="/brand/leaklane-mark.svg" alt="" />
        </span>
        <div class="brand-copy">
          <p>Local secret triage</p>
          <h1>LeakLane</h1>
        </div>
      </div>
      <button
        class="sidebar-toggle"
        type="button"
        aria-label={sidebarCollapsed ? 'Espandi navigazione' : 'Comprimi navigazione'}
        aria-pressed={sidebarCollapsed}
        title={sidebarCollapsed ? 'Espandi navigazione' : 'Comprimi navigazione'}
        on:click={toggleSidebar}
      >
        {sidebarCollapsed ? '>' : '<'}
      </button>
    </div>

    <nav aria-label="Navigazione principale">
      {#each navItems as item}
        <a
          class:active={page.url.pathname === item.href}
          href={item.href}
          aria-label={`${item.kicker} ${item.label}`}
          title={`${item.kicker} ${item.label}`}
        >
          <span class="nav-compact" aria-hidden="true">{item.short}</span>
          <span class="nav-kicker">{item.kicker}</span>
          <strong>{item.label}</strong>
        </a>
      {/each}
    </nav>

    <div class="sidebar-status">
      <i aria-hidden="true"></i>
      <span>Backend locale</span>
      <strong>{backendLabel}</strong>
    </div>
  </aside>

  <main class="page-frame">
    <slot />
  </main>
</div>

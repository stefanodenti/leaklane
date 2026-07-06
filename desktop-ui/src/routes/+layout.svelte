<script lang="ts">
  import { page } from '$app/state';
  import '../app.css';

  const navItems = [
    { href: '/dashboard', label: 'Dashboard', kicker: 'Rischio' },
    { href: '/repositories', label: 'Repository', kicker: 'Pitlane' },
    { href: '/scan', label: 'Scansione', kicker: 'Setup' },
    { href: '/reports', label: 'Report', kicker: 'Archivio' },
    { href: '/compare', label: 'Confronti', kicker: 'Delta' },
    { href: '/settings', label: 'Settings', kicker: 'Locale' }
  ];
</script>

<svelte:head>
  <title>LeakLane</title>
  <meta
    name="description"
    content="Local secret triage for repository fleets with Gitleaks and LM Studio."
  />
</svelte:head>

<div class="app-shell">
  <aside class="sidebar">
    <div class="brand">
      <span class="brand-mark" aria-hidden="true">
        <img src="/brand/leaklane-mark.svg" alt="" />
      </span>
      <div>
        <p>Local secret triage</p>
        <h1>LeakLane</h1>
      </div>
    </div>

    <nav aria-label="Navigazione principale">
      {#each navItems as item}
        <a class:active={page.url.pathname === item.href} href={item.href}>
          <span>{item.kicker}</span>
          <strong>{item.label}</strong>
        </a>
      {/each}
    </nav>

    <div class="sidebar-status">
      <span>Backend locale</span>
      <strong>127.0.0.1:8787</strong>
    </div>
  </aside>

  <main class="page-frame">
    <slot />
  </main>
</div>

<script lang="ts">
  import { onMount } from 'svelte';
  import { getJobs, getRepositoryMap } from '$lib/api';
  import { formatDate, formatNumber } from '$lib/format';
  import type {
    JobPreview,
    RepositoryMap,
    RepositoryMapBranch,
    RepositoryMapCommit,
    RepositoryMapFinding,
    RepositoryMapTag,
    RepositoryPullRequest
  } from '$lib/types';

  type RepoOption = {
    name: string;
    url: string;
    jobs: number;
  };

  type Selection =
    | { type: 'commit'; item: RepositoryMapCommit }
    | { type: 'branch'; item: RepositoryMapBranch }
    | { type: 'finding'; item: RepositoryMapFinding }
    | { type: 'tag'; item: RepositoryMapTag }
    | { type: 'pr'; item: RepositoryPullRequest }
    | null;

  let jobs: JobPreview[] = [];
  let repositories: RepoOption[] = [];
  let selectedUrl = '';
  let repoMap: RepositoryMap | null = null;
  let selected: Selection = null;
  let loadingJobs = true;
  let loadingMap = false;
  let error = '';
  let mapError = '';
  let showBranches = true;
  let showTags = true;
  let showPullRequests = true;
  let showFindings = true;
  let zoom = 1;
  let isDragging = false;
  let dragStartX = 0;
  let dragScrollLeft = 0;

  async function loadJobs() {
    loadingJobs = true;
    error = '';
    try {
      jobs = await getJobs();
      repositories = repositoryOptions(jobs);
      selectedUrl = repositories[0]?.url || '';
    } catch (err) {
      error = err instanceof Error ? err.message : 'Errore caricamento repository';
    } finally {
      loadingJobs = false;
    }
  }

  async function loadMap(refresh = false) {
    if (!selectedUrl || loadingMap) return;
    loadingMap = true;
    mapError = '';
    selected = null;
    try {
      repoMap = await getRepositoryMap(selectedUrl, refresh);
      selected = repoMap.commits[0] ? { type: 'commit', item: repoMap.commits[0] } : null;
    } catch (err) {
      repoMap = null;
      mapError = err instanceof Error ? err.message : 'Errore generazione mappa repository';
    } finally {
      loadingMap = false;
    }
  }

  function repositoryOptions(items: JobPreview[]) {
    const index = new Map<string, RepoOption>();
    for (const job of items) {
      for (const url of job.urls || []) {
        const previous = index.get(url);
        if (previous) {
          previous.jobs += 1;
        } else {
          index.set(url, { name: repoNameFromUrl(url), url, jobs: 1 });
        }
      }
    }
    return Array.from(index.values()).sort((left, right) => left.name.localeCompare(right.name));
  }

  function repoNameFromUrl(url: string) {
    try {
      const parsed = new URL(url);
      const parts = parsed.pathname.replace(/\.git$/, '').split('/').filter(Boolean);
      return parts.slice(-2).join('/') || url;
    } catch {
      return url;
    }
  }

  function selectUrl(url: string) {
    selectedUrl = url;
    repoMap = null;
    selected = null;
    mapError = '';
  }

  function graphWidth(map: RepositoryMap) {
    return Math.max(960, 120 + map.commits.length * 92);
  }

  function commitX(index: number) {
    return 72 + index * 92;
  }

  function commitLane(commit: RepositoryMapCommit, index: number) {
    if (commit.parents.length > 1) return 2;
    const marker = Number.parseInt(commit.hash.slice(-2), 16);
    return Number.isFinite(marker) ? marker % 3 : index % 3;
  }

  function commitY(commit: RepositoryMapCommit, index: number) {
    return 92 + commitLane(commit, index) * 74;
  }

  function commitIndex(hash: string, map: RepositoryMap) {
    return map.commits.findIndex((commit) => commit.hash === hash || commit.hash.startsWith(hash));
  }

  function commitByHash(hash: string, map: RepositoryMap) {
    return map.commits.find((commit) => commit.hash === hash || commit.hash.startsWith(hash));
  }

  function commitLabels(hash: string, map: RepositoryMap) {
    const branches = showBranches ? map.branches.filter((branch) => branch.commit === hash).map((branch) => branch.name) : [];
    const tags = showTags ? map.tags.filter((tag) => tag.commit === hash).map((tag) => tag.name) : [];
    return [...branches.slice(0, 2), ...tags.slice(0, 2)];
  }

  function commitFindings(commit: RepositoryMapCommit, map: RepositoryMap) {
    return map.findings.filter((finding) => finding.commit === commit.hash);
  }

  function branchForPr(pr: RepositoryPullRequest, map: RepositoryMap) {
    if (!pr.head) return null;
    return map.branches.find((branch) => branch.name === pr.head) || null;
  }

  function isSelectedCommit(commit: RepositoryMapCommit) {
    return selected?.type === 'commit' && selected.item.hash === commit.hash;
  }

  function severityClass(finding: RepositoryMapFinding) {
    if (finding.severity === 'critical') return 'risk-critical';
    if (finding.severity === 'high') return 'risk-high';
    if (finding.severity === 'low' || finding.severity === 'clean') return 'risk-clean';
    return 'status-warn';
  }

  function zoomIn() {
    zoom = Math.min(1.8, Number((zoom + 0.15).toFixed(2)));
  }

  function zoomOut() {
    zoom = Math.max(0.7, Number((zoom - 0.15).toFixed(2)));
  }

  function resetZoom() {
    zoom = 1;
  }

  function startPan(event: PointerEvent) {
    const target = event.currentTarget as HTMLElement;
    isDragging = true;
    dragStartX = event.clientX;
    dragScrollLeft = target.scrollLeft;
    target.setPointerCapture(event.pointerId);
  }

  function movePan(event: PointerEvent) {
    if (!isDragging) return;
    const target = event.currentTarget as HTMLElement;
    target.scrollLeft = dragScrollLeft - (event.clientX - dragStartX);
  }

  function stopPan(event: PointerEvent) {
    const target = event.currentTarget as HTMLElement;
    isDragging = false;
    if (target.hasPointerCapture(event.pointerId)) {
      target.releasePointerCapture(event.pointerId);
    }
  }

  function freshness(branch: RepositoryMapBranch) {
    const days = Math.floor((Date.now() / 1000 - branch.updated_at) / 86400);
    if (days > 180) return 'Stale';
    if (days > 90) return 'Da rivedere';
    return 'Attivo';
  }

  function isoDate(value?: string | null) {
    if (!value) return 'Data non disponibile';
    return new Date(value).toLocaleString('it-IT', { dateStyle: 'short', timeStyle: 'short' });
  }

  function prClass(pr: RepositoryPullRequest) {
    if (pr.is_draft) return 'status-warn';
    if (pr.state === 'OPEN') return 'status-ok';
    if (pr.state === 'MERGED') return 'risk-clean';
    return 'status-chip';
  }

  onMount(loadJobs);
</script>

<section class="page-head">
  <div>
    <p class="eyebrow">Repository intelligence</p>
    <h2>Mappa repo</h2>
  </div>
  <button class="ghost" type="button" disabled={!selectedUrl || loadingMap} on:click={() => loadMap(false)}>
    {loadingMap ? 'Analisi in corso' : 'Genera mappa'}
  </button>
</section>

{#if loadingJobs}
  <div class="empty">Caricamento repository analizzati.</div>
{:else if error}
  <div class="inline-error">{error}</div>
{:else if repositories.length === 0}
  <div class="empty">Avvia almeno una scansione per popolare la mappa repository.</div>
{:else}
  <section class="map-layout">
    <aside class="panel map-repo-panel">
      <div class="section-title">
        <div>
          <p class="eyebrow">Repository</p>
          <h3>Pitlane analizzata</h3>
        </div>
        <span>{formatNumber(repositories.length)} repo</span>
      </div>
      <div class="repo-map-list">
        {#each repositories as repository}
          <button
            class:active={repository.url === selectedUrl}
            class="repo-map-item"
            type="button"
            on:click={() => selectUrl(repository.url)}
          >
            <strong>{repository.name}</strong>
            <span>{repository.jobs} scan | {repository.url}</span>
          </button>
        {/each}
      </div>
    </aside>

    <div class="map-main">
      {#if mapError}
        <div class="inline-error">{mapError}</div>
      {/if}

      {#if loadingMap}
        <section class="panel map-loading">
          <div class="skeleton-line wide"></div>
          <div class="skeleton-graph">
            <span></span><span></span><span></span><span></span>
          </div>
          <p>Clone temporaneo, lettura branch/tag/commit e overlay finding.</p>
        </section>
      {:else if repoMap}
        <section class="metric-grid map-metrics">
          <div class="metric"><strong>{formatNumber(repoMap.summary.branches)}</strong><span>Branch</span></div>
          <div class="metric"><strong>{formatNumber(repoMap.summary.tags)}</strong><span>Tag</span></div>
          <div class="metric"><strong>{formatNumber(repoMap.summary.pull_requests)}</strong><span>PR</span></div>
          <div class="metric"><strong>{formatNumber(repoMap.summary.commits)}</strong><span>Commit letti</span></div>
          <div class="metric"><strong>{formatNumber(repoMap.summary.findings)}</strong><span>Finding overlay</span></div>
        </section>

        <section class="repo-map-grid">
          <div class="panel graph-panel">
            <div class="section-title">
              <div>
                <p class="eyebrow">{repoMap.repository.provider}</p>
                <h3>{repoMap.repository.name}</h3>
              </div>
              <span>
                {repoMap.repository.default_branch || 'default branch n/d'}
                {repoMap.cache?.hit ? ' | cache' : ''}
              </span>
            </div>

            <div class="map-toolbar" aria-label="Controlli mappa repository">
              <div class="segmented-control">
                <button type="button" on:click={zoomOut}>-</button>
                <button type="button" on:click={resetZoom}>{Math.round(zoom * 100)}%</button>
                <button type="button" on:click={zoomIn}>+</button>
              </div>
              <label><input type="checkbox" bind:checked={showBranches} /> Branch</label>
              <label><input type="checkbox" bind:checked={showTags} /> Tag</label>
              <label><input type="checkbox" bind:checked={showPullRequests} /> PR</label>
              <label><input type="checkbox" bind:checked={showFindings} /> Finding</label>
              <button class="ghost" type="button" disabled={loadingMap} on:click={() => loadMap(true)}>Aggiorna clone</button>
            </div>

            <div
              class:dragging={isDragging}
              class="graph-scroll"
              aria-label="Grafo commit repository"
              role="region"
              on:pointerdown={startPan}
              on:pointermove={movePan}
              on:pointerup={stopPan}
              on:pointercancel={stopPan}
            >
              <svg
                class="commit-graph"
                style={`width: ${graphWidth(repoMap) * zoom}px;`}
                viewBox={`0 0 ${graphWidth(repoMap)} 360`}
                role="img"
              >
                <title>Commit graph for {repoMap.repository.name}</title>
                {#each repoMap.commits as commit, index}
                  {#each commit.parents as parent}
                    {@const parentIndex = commitIndex(parent, repoMap)}
                    {#if parentIndex >= 0}
                      {@const parentCommit = repoMap.commits[parentIndex]}
                      <line
                        class="graph-edge"
                        x1={commitX(index)}
                        y1={commitY(commit, index)}
                        x2={commitX(parentIndex)}
                        y2={commitY(parentCommit, parentIndex)}
                      />
                    {/if}
                  {/each}
                {/each}

                {#if showTags}
                  {#each repoMap.tags as tag, index}
                    {@const tagIndex = commitIndex(tag.commit, repoMap)}
                    {#if tagIndex >= 0}
                      <line class="tag-line" x1={commitX(tagIndex)} y1="298" x2={commitX(tagIndex)} y2="330" />
                      <text class="tag-label" x={commitX(tagIndex) - 28} y={326 + (index % 2) * 16}>{tag.name}</text>
                    {/if}
                  {/each}
                {/if}

                {#if showBranches}
                  {#each repoMap.branches as branch, index}
                    {@const branchIndex = commitIndex(branch.commit, repoMap)}
                    {#if branchIndex >= 0}
                      <line class="branch-line" x1={commitX(branchIndex)} y1="28" x2={commitX(branchIndex)} y2="58" />
                      <text class:default-branch={branch.is_default} class="branch-label" x={commitX(branchIndex) - 34} y={26 + (index % 2) * 16}>{branch.name}</text>
                    {/if}
                  {/each}
                {/if}

                {#if showPullRequests}
                  {#each repoMap.pull_requests as pr, index}
                    {@const branch = branchForPr(pr, repoMap)}
                    {#if branch}
                      {@const prIndex = commitIndex(branch.commit, repoMap)}
                      {#if prIndex >= 0}
                        <line class="pr-line" x1={commitX(prIndex)} y1="54" x2={commitX(prIndex) + 34} y2={78 + (index % 3) * 18} />
                        <text class="pr-label" x={commitX(prIndex) + 38} y={82 + (index % 3) * 18}>PR #{pr.number}</text>
                      {/if}
                    {/if}
                  {/each}
                {/if}

                {#each repoMap.commits as commit, index}
                  <g
                    class:selected-commit={isSelectedCommit(commit)}
                    class:hot-commit={commit.findings > 0}
                    class="commit-node"
                    role="button"
                    tabindex="0"
                    on:click={() => (selected = { type: 'commit', item: commit })}
                    on:keydown={(event) => event.key === 'Enter' && (selected = { type: 'commit', item: commit })}
                  >
                    <circle cx={commitX(index)} cy={commitY(commit, index)} r={commit.findings > 0 ? 13 : 10} />
                    <text x={commitX(index) - 22} y={commitY(commit, index) + 31}>{commit.short}</text>
                    {#if showFindings && commit.findings > 0}
                      <text class="finding-count" x={commitX(index) - 4} y={commitY(commit, index) + 4}>{commit.findings}</text>
                    {/if}
                    {#each commitLabels(commit.hash, repoMap) as label, labelIndex}
                      <text class="mini-label" x={commitX(index) - 28} y={commitY(commit, index) - 24 - labelIndex * 14}>{label}</text>
                    {/each}
                  </g>
                {/each}
              </svg>
            </div>
          </div>

          <aside class="panel map-detail-panel">
            <div class="section-title">
              <div>
                <p class="eyebrow">Dettaglio</p>
                <h3>Elemento selezionato</h3>
              </div>
            </div>

            {#if selected?.type === 'commit'}
              <div class="detail-stack">
                <strong>{selected.item.short}</strong>
                <p>{selected.item.subject}</p>
                <span>{selected.item.author} | {formatDate(selected.item.timestamp)}</span>
                <code>{selected.item.hash}</code>
                <div class="counter-line">
                  <span>Parent {formatNumber(selected.item.parents.length)}</span>
                  <span class:risk-critical={selected.item.findings > 0}>Finding {formatNumber(selected.item.findings)}</span>
                </div>
                {#if repoMap && commitFindings(selected.item, repoMap).length}
                  <div class="commit-finding-stack">
                    <span class="eyebrow">Finding sul commit</span>
                    {#each commitFindings(selected.item, repoMap) as finding}
                      <button class="finding-chip-row" type="button" on:click={() => (selected = { type: 'finding', item: finding })}>
                        <span class={severityClass(finding)}>{finding.severity || 'finding'}</span>
                        <strong>{finding.rule || 'unknown-rule'}</strong>
                        <em>{finding.file}:{finding.line || '?'}</em>
                      </button>
                    {/each}
                  </div>
                {/if}
              </div>
            {:else if selected?.type === 'finding'}
              <div class="detail-stack">
                <strong>{selected.item.rule || 'unknown-rule'}</strong>
                <p>{selected.item.description || 'Finding collegato all ultima scansione Gitleaks.'}</p>
                <span>{selected.item.file}:{selected.item.line || '?'}</span>
                {#if selected.item.commit}<code>{selected.item.commit}</code>{/if}
                <div class="counter-line">
                  <span class={severityClass(selected.item)}>{selected.item.severity || 'finding'}</span>
                  {#if selected.item.fingerprint}<span>Fingerprint presente</span>{/if}
                </div>
                {#if selected.item.link}
                  <a class="button-link" href={selected.item.link} target="_blank" rel="noreferrer">Apri origine</a>
                {/if}
              </div>
            {:else if selected?.type === 'branch'}
              <div class="detail-stack">
                <strong>{selected.item.name}</strong>
                <p>{selected.item.subject}</p>
                <span>{freshness(selected.item)} | {formatDate(selected.item.updated_at)}</span>
                <code>{selected.item.commit}</code>
              </div>
            {:else if selected?.type === 'tag'}
              <div class="detail-stack">
                <strong>{selected.item.name}</strong>
                <p>{selected.item.subject || 'Tag senza messaggio.'}</p>
                <span>{formatDate(selected.item.created_at)}</span>
                <code>{selected.item.commit}</code>
              </div>
            {:else if selected?.type === 'pr'}
              <div class="detail-stack">
                <strong>PR #{selected.item.number}</strong>
                <p>{selected.item.title}</p>
                <span>{selected.item.head} -> {selected.item.base}</span>
                <span>Aggiornata {isoDate(selected.item.updated_at)}</span>
                {#if selected.item.url}<a class="button-link" href={selected.item.url} target="_blank" rel="noreferrer">Apri PR</a>{/if}
              </div>
            {:else}
              <div class="empty">Seleziona un commit, branch, tag o PR per vedere i dettagli.</div>
            {/if}
          </aside>
        </section>

        <section class="repo-secondary-grid">
          <div class="panel">
            <div class="section-title">
              <h3>Branch</h3>
              <span>{formatNumber(repoMap.summary.stale_branches)} da rivedere</span>
            </div>
            <div class="branch-stack">
              {#each repoMap.branches.slice(0, 12) as branch}
                <button class="branch-row" type="button" on:click={() => (selected = { type: 'branch', item: branch })}>
                  <span class:default-dot={branch.is_default}></span>
                  <strong>{branch.name}</strong>
                  <em>{freshness(branch)}</em>
                </button>
              {/each}
            </div>
          </div>

          <div class="panel">
            <div class="section-title">
              <h3>Tag</h3>
              <span>{formatNumber(repoMap.tags.length)} release marker</span>
            </div>
            {#if repoMap.tags.length === 0}
              <div class="empty">Nessun tag trovato nel repository.</div>
            {:else}
              <div class="branch-stack">
                {#each repoMap.tags.slice(0, 10) as tag}
                  <button class="branch-row" type="button" on:click={() => (selected = { type: 'tag', item: tag })}>
                    <span></span>
                    <strong>{tag.name}</strong>
                    <em>{formatDate(tag.created_at)}</em>
                  </button>
                {/each}
              </div>
            {/if}
          </div>

          <div class="panel">
            <div class="section-title">
              <h3>Pull request</h3>
              <span>{repoMap.pull_requests.length ? 'Da GitHub CLI' : 'Nessun dato PR'}</span>
            </div>
            {#if repoMap.pull_requests.length === 0}
              <div class="empty">Collega GitHub CLI o usa un repository GitHub per visualizzare le PR.</div>
            {:else}
              <div class="pr-stack">
                {#each repoMap.pull_requests.slice(0, 8) as pr}
                  <button class="pr-row" type="button" on:click={() => (selected = { type: 'pr', item: pr })}>
                    <span class={prClass(pr)}>{pr.state}</span>
                    <strong>#{pr.number} {pr.title}</strong>
                    <em>{pr.head} -> {pr.base}</em>
                  </button>
                {/each}
              </div>
            {/if}
          </div>
        </section>

        {#if repoMap.findings.length}
          <section class="panel map-findings-panel">
            <div class="section-title">
              <div>
                <p class="eyebrow">Security overlay</p>
                <h3>Finding recenti</h3>
              </div>
              <span>{formatNumber(repoMap.findings.length)} evidenze</span>
            </div>
            <div class="map-finding-grid">
              {#each repoMap.findings.slice(0, 12) as finding}
                <button class="finding-chip-row" type="button" on:click={() => (selected = { type: 'finding', item: finding })}>
                  <span class={severityClass(finding)}>{finding.severity || 'finding'}</span>
                  <strong>{finding.rule || 'unknown-rule'}</strong>
                  <em>{finding.file}:{finding.line || '?'}</em>
                </button>
              {/each}
            </div>
          </section>
        {/if}
      {:else}
        <section class="panel map-intro">
          <p class="eyebrow">MVP locale</p>
          <h3>Genera una mappa strutturale del repository</h3>
          <p>
            LeakLane usera' un clone temporaneo per leggere branch, tag, ultimi commit e PR GitHub.
            I finding dell'ultima scansione vengono sovrapposti ai commit quando il report contiene l'hash.
          </p>
          <button type="button" disabled={!selectedUrl} on:click={() => loadMap(false)}>Genera mappa repository</button>
        </section>
      {/if}
    </div>
  </section>
{/if}

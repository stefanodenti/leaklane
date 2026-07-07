<script lang="ts">
  import { browser } from '$app/environment';
  import { onMount, tick } from 'svelte';
  import { generateRepositoryMapAiAnalysis, getJobs, getRepositoryMap } from '$lib/api';
  import { formatDate, formatNumber } from '$lib/format';
  import { renderMarkdown } from '$lib/markdown';
  import type {
    JobPreview,
    RepositoryMap,
    RepositoryMapAiAnalysis,
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
    latestFindings: number;
    latestStatus: string;
    lastScanAt: number;
  };

  type MapSort = 'recent' | 'risk' | 'name';

  type Selection =
    | { type: 'commit'; item: RepositoryMapCommit }
    | { type: 'branch'; item: RepositoryMapBranch }
    | { type: 'finding'; item: RepositoryMapFinding }
    | { type: 'tag'; item: RepositoryMapTag }
    | { type: 'pr'; item: RepositoryPullRequest }
    | null;

  let jobs: JobPreview[] = [];
  let repositories: RepoOption[] = [];
  let filteredRepositories: RepoOption[] = [];
  let selectedUrl = '';
  let repoSearch = '';
  let repoSort: MapSort = 'recent';
  let repoMap: RepositoryMap | null = null;
  let selected: Selection = null;
  let loadingJobs = true;
  let loadingMap = false;
  let error = '';
  let mapError = '';
  let mapAiAnalysis: RepositoryMapAiAnalysis | null = null;
  let mapAiLoading = false;
  let mapAiError = '';
  let selectedAiAnalysis: RepositoryMapAiAnalysis | null = null;
  let selectedAiLoading = false;
  let selectedAiError = '';
  let selectionKey = '';
  let showBranches = true;
  let showTags = true;
  let showPullRequests = true;
  let showFindings = true;
  let zoom = 1;
  let isDragging = false;
  let dragStartX = 0;
  let dragScrollLeft = 0;
  let laneMap = new Map<string, number>();
  let graphViewport: HTMLDivElement | null = null;
  let mapStateReady = false;

  const MAP_STATE_KEY = 'leaklane-map-state';
  const graphLanes = [0, 1, 2, 3, 4];
  const lanePalette = ['#2f8ab7', '#7a70c8', '#4fa46c', '#c47a3f', '#c45c73'];

  $: filteredRepositories = repositoryDisplayOptions(repositories, repoSearch, repoSort);

  $: if (browser && mapStateReady) {
    selectedUrl;
    repoSearch;
    repoSort;
    showBranches;
    showTags;
    showPullRequests;
    showFindings;
    zoom;
    saveMapState();
  }

  $: {
    const nextSelectionKey = selectedIdentity(selected);
    if (nextSelectionKey !== selectionKey) {
      selectionKey = nextSelectionKey;
      selectedAiAnalysis = null;
      selectedAiError = '';
    }
  }

  async function loadJobs() {
    loadingJobs = true;
    error = '';
    try {
      jobs = await getJobs();
      repositories = repositoryOptions(jobs);
      if (!selectedUrl || !repositories.some((repository) => repository.url === selectedUrl)) {
        selectedUrl = repositories[0]?.url || '';
      }
    } catch (err) {
      error = err instanceof Error ? err.message : 'Errore caricamento repository';
    } finally {
      loadingJobs = false;
    }
  }

  async function loadMap(mode: 'stored' | 'delta' | 'force' = 'stored') {
    if (!selectedUrl || loadingMap) return;
    loadingMap = true;
    mapError = '';
    mapAiError = '';
    mapAiAnalysis = null;
    selected = null;
    try {
      repoMap = await getRepositoryMap(selectedUrl, mode);
      laneMap = buildLaneMap(repoMap);
      selected = repoMap.commits[0] ? { type: 'commit', item: repoMap.commits[0] } : null;
      await tick();
      fitGraphToViewport();
    } catch (err) {
      repoMap = null;
      laneMap = new Map();
      mapError = err instanceof Error ? err.message : 'Errore generazione mappa repository';
    } finally {
      loadingMap = false;
    }
  }

  function repositoryOptions(items: JobPreview[]) {
    const index = new Map<string, RepoOption>();
    for (const job of items) {
      for (const [urlIndex, url] of (job.urls || []).entries()) {
        const previous = index.get(url);
        const result = resultForUrl(job, url, urlIndex);
        const findings = Number(result?.findings || 0);
        const scanAt = Number(job.finished_at || job.started_at || 0);
        if (previous) {
          previous.jobs += 1;
          if (scanAt >= previous.lastScanAt) {
            previous.latestFindings = findings;
            previous.latestStatus = result?.status || job.status;
            previous.lastScanAt = scanAt;
          }
        } else {
          index.set(url, {
            name: repoNameFromUrl(url),
            url,
            jobs: 1,
            latestFindings: findings,
            latestStatus: result?.status || job.status,
            lastScanAt: scanAt
          });
        }
      }
    }
    return Array.from(index.values());
  }

  function resultForUrl(job: JobPreview, url: string, index: number) {
    return (
      job.results?.[index] ||
      job.results?.find((result) => result.name === repoNameFromUrl(url) || repoNameFromUrl(url).endsWith(result.name)) ||
      null
    );
  }

  function repositoryDisplayOptions(items: RepoOption[], query: string, sort: MapSort) {
    const needle = query.trim().toLowerCase();
    const filtered = needle
      ? items.filter((repository) => `${repository.name} ${repository.url}`.toLowerCase().includes(needle))
      : [...items];
    return filtered.sort((left, right) => {
      if (sort === 'risk') {
        return (
          right.latestFindings - left.latestFindings ||
          right.lastScanAt - left.lastScanAt ||
          left.name.localeCompare(right.name)
        );
      }
      if (sort === 'name') return left.name.localeCompare(right.name);
      return right.lastScanAt - left.lastScanAt || left.name.localeCompare(right.name);
    });
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
    laneMap = new Map();
    mapAiAnalysis = null;
    mapAiError = '';
    mapError = '';
  }

  function restoreMapState() {
    if (!browser) return;
    try {
      const raw = localStorage.getItem(MAP_STATE_KEY);
      if (!raw) return;
      const state = JSON.parse(raw);
      selectedUrl = typeof state.selectedUrl === 'string' ? state.selectedUrl : '';
      repoSearch = typeof state.repoSearch === 'string' ? state.repoSearch : '';
      repoSort = state.repoSort === 'risk' || state.repoSort === 'name' ? state.repoSort : 'recent';
      showBranches = state.showBranches !== false;
      showTags = state.showTags !== false;
      showPullRequests = state.showPullRequests !== false;
      showFindings = state.showFindings !== false;
      zoom = typeof state.zoom === 'number' ? Math.min(1.8, Math.max(0.7, state.zoom)) : 1;
    } catch {
      selectedUrl = '';
    }
  }

  function saveMapState() {
    localStorage.setItem(
      MAP_STATE_KEY,
      JSON.stringify({
        selectedUrl,
        repoSearch,
        repoSort,
        showBranches,
        showTags,
        showPullRequests,
        showFindings,
        zoom
      })
    );
  }

  async function runMapAiAnalysis() {
    if (!selectedUrl || !repoMap || mapAiLoading) return;
    mapAiLoading = true;
    mapAiError = '';
    try {
      mapAiAnalysis = await generateRepositoryMapAiAnalysis(selectedUrl, repoMap);
    } catch (err) {
      mapAiError = err instanceof Error ? err.message : 'Errore generazione analisi AI mappa';
    } finally {
      mapAiLoading = false;
    }
  }

  async function runSelectedAiAnalysis() {
    if (!selectedUrl || !repoMap || !selected || selectedAiLoading) return;
    selectedAiLoading = true;
    selectedAiError = '';
    try {
      selectedAiAnalysis = await generateRepositoryMapAiAnalysis(selectedUrl, repoMap, selectionFocus(selected, repoMap));
    } catch (err) {
      selectedAiError = err instanceof Error ? err.message : 'Errore analisi AI elemento';
    } finally {
      selectedAiLoading = false;
    }
  }

  function graphWidth(map: RepositoryMap) {
    return Math.max(960, 120 + map.commits.length * 92);
  }

  function commitX(index: number) {
    return 72 + index * 92;
  }

  function graphHeight() {
    return 520;
  }

  function buildLaneMap(map: RepositoryMap) {
    const next = new Map<string, number>();
    const commitIndexByHash = new Map(map.commits.map((commit, index) => [commit.hash, index]));
    const commitByFullHash = new Map(map.commits.map((commit) => [commit.hash, commit]));
    const defaultBranch = map.branches.find((branch) => branch.is_default) || map.branches[0];
    const sideLanes = [0, 4, 1, 3];

    function walk(head: string | undefined, lane: number, overwrite = false) {
      let current = head;
      let guard = 0;
      while (current && guard < map.commits.length) {
        const commit = commitByFullHash.get(current);
        if (!commit) break;
        if (overwrite || !next.has(commit.hash)) {
          next.set(commit.hash, lane);
        }
        current = commit.parents[0];
        guard += 1;
      }
    }

    if (defaultBranch) {
      walk(defaultBranch.commit, 2, true);
    }

    map.branches
      .filter((branch) => !branch.is_default && commitIndexByHash.has(branch.commit))
      .slice(0, sideLanes.length)
      .forEach((branch, index) => walk(branch.commit, sideLanes[index]));

    for (const commit of map.commits) {
      if (!next.has(commit.hash)) {
        next.set(commit.hash, commit.parents.length > 1 ? 2 : 1 + (commitIndexByHash.get(commit.hash) || 0) % 3);
      }
    }

    return next;
  }

  function commitLane(commit: RepositoryMapCommit, index: number) {
    return laneMap.get(commit.hash) ?? (commit.parents.length > 1 ? 2 : index % graphLanes.length);
  }

  function laneColor(lane: number) {
    return lanePalette[((lane % lanePalette.length) + lanePalette.length) % lanePalette.length];
  }

  function commitColor(commit: RepositoryMapCommit, index: number) {
    return laneColor(commitLane(commit, index));
  }

  function branchLane(branch: RepositoryMapBranch) {
    return laneMap.get(branch.commit) ?? (branch.is_default ? 2 : 1);
  }

  function branchColor(branch: RepositoryMapBranch) {
    return laneColor(branchLane(branch));
  }

  function tagColor(tag: RepositoryMapTag, map: RepositoryMap) {
    const commit = commitByHash(tag.commit, map);
    const index = commit ? map.commits.findIndex((item) => item.hash === commit.hash) : -1;
    return commit && index >= 0 ? commitColor(commit, index) : 'var(--warn-ink)';
  }

  function edgePath(startX: number, startY: number, endX: number, endY: number) {
    const controlOffset = Math.max(34, Math.abs(endX - startX) * 0.45);
    const direction = endX >= startX ? 1 : -1;
    const firstControlX = startX + controlOffset * direction;
    const secondControlX = endX - controlOffset * direction;
    return `M ${startX} ${startY} C ${firstControlX} ${startY}, ${secondControlX} ${endY}, ${endX} ${endY}`;
  }

  function branchLabelWidth(label: string) {
    return Math.min(180, Math.max(74, 30 + label.length * 7));
  }

  function visibleBranchLegend(map: RepositoryMap) {
    return [...map.branches]
      .sort((left, right) => Number(right.is_default) - Number(left.is_default) || left.name.localeCompare(right.name))
      .slice(0, 7);
  }

  function commitY(commit: RepositoryMapCommit, index: number) {
    return laneY(commitLane(commit, index));
  }

  function laneY(lane: number) {
    return 94 + lane * 78;
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

  function branchesForCommit(commit: RepositoryMapCommit, map: RepositoryMap) {
    return map.branches.filter((branch) => branch.commit === commit.hash);
  }

  function tagsForCommit(commit: RepositoryMapCommit, map: RepositoryMap) {
    return map.tags.filter((tag) => tag.commit === commit.hash);
  }

  function pullRequestsForBranch(branch: RepositoryMapBranch, map: RepositoryMap) {
    return map.pull_requests.filter((pr) => pr.head === branch.name || pr.base === branch.name);
  }

  function commitPosition(commit: RepositoryMapCommit, map: RepositoryMap) {
    const index = map.commits.findIndex((item) => item.hash === commit.hash);
    if (index < 0) return 'Non in vista';
    return `#${index + 1} di ${formatNumber(map.commits.length)}`;
  }

  function commitLaneNumber(commit: RepositoryMapCommit, map: RepositoryMap) {
    const index = map.commits.findIndex((item) => item.hash === commit.hash);
    return commitLane(commit, Math.max(0, index)) + 1;
  }

  function selectCommitByHash(hash: string | null | undefined, map: RepositoryMap | null) {
    if (!hash || !map) return;
    const commit = commitByHash(hash, map);
    if (commit) {
      selected = { type: 'commit', item: commit };
    }
  }

  function selectedTitle(selection: Selection) {
    if (!selection) return 'Elemento selezionato';
    if (selection.type === 'commit') return selection.item.short;
    if (selection.type === 'branch') return selection.item.name;
    if (selection.type === 'finding') return selection.item.rule || 'unknown-rule';
    if (selection.type === 'tag') return selection.item.name;
    return `PR #${selection.item.number}`;
  }

  function selectedIdentity(selection: Selection) {
    if (!selection) return '';
    if (selection.type === 'commit') return `commit:${selection.item.hash}`;
    if (selection.type === 'branch') return `branch:${selection.item.name}`;
    if (selection.type === 'finding') return `finding:${selection.item.fingerprint || selection.item.rule || selection.item.file}`;
    if (selection.type === 'tag') return `tag:${selection.item.name}`;
    return `pr:${selection.item.number}`;
  }

  function selectionFocus(selection: Selection, map: RepositoryMap): Record<string, unknown> | undefined {
    if (!selection) return undefined;
    const base = {
      type: selectedKind(selection),
      title: selectedTitle(selection)
    };
    if (selection.type === 'commit') {
      return {
        ...base,
        item: selection.item,
        related_branches: branchesForCommit(selection.item, map).map((branch) => branch.name),
        related_tags: tagsForCommit(selection.item, map).map((tag) => tag.name),
        related_findings: commitFindings(selection.item, map).slice(0, 8)
      };
    }
    if (selection.type === 'branch') {
      return {
        ...base,
        item: selection.item,
        related_pull_requests: pullRequestsForBranch(selection.item, map).slice(0, 8),
        head_commit: commitByHash(selection.item.commit, map)
      };
    }
    if (selection.type === 'finding') {
      return {
        ...base,
        item: selection.item,
        related_commit: selection.item.commit ? commitByHash(selection.item.commit, map) : null
      };
    }
    if (selection.type === 'tag') {
      return {
        ...base,
        item: selection.item,
        related_commit: commitByHash(selection.item.commit, map)
      };
    }
    return {
      ...base,
      item: selection.item,
      head_branch: selection.item.head ? map.branches.find((branch) => branch.name === selection.item.head) : null,
      base_branch: selection.item.base ? map.branches.find((branch) => branch.name === selection.item.base) : null
    };
  }

  function selectedKind(selection: Selection) {
    if (!selection) return 'Dettaglio';
    if (selection.type === 'commit') return 'Commit';
    if (selection.type === 'branch') return 'Branch';
    if (selection.type === 'finding') return 'Finding Gitleaks';
    if (selection.type === 'tag') return 'Tag';
    return 'Pull request';
  }

  function selectedColor(selection: Selection, map: RepositoryMap) {
    if (!selection) return 'var(--accent)';
    if (selection.type === 'commit') {
      const index = map.commits.findIndex((commit) => commit.hash === selection.item.hash);
      return commitColor(selection.item, Math.max(0, index));
    }
    if (selection.type === 'branch') return branchColor(selection.item);
    if (selection.type === 'tag') return tagColor(selection.item, map);
    if (selection.type === 'pr') {
      const branch = branchForPr(selection.item, map);
      return branch ? branchColor(branch) : 'var(--clean-ink)';
    }
    if (selection.item.severity === 'critical' || selection.item.severity === 'high') return 'var(--danger-ink)';
    if (selection.item.severity === 'low' || selection.item.severity === 'clean') return 'var(--clean-ink)';
    return 'var(--warn-ink)';
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

  function fitGraphToViewport() {
    if (!repoMap || !graphViewport) return;
    const available = Math.max(320, graphViewport.clientWidth - 28);
    const nextZoom = available / graphWidth(repoMap);
    zoom = Math.min(1.8, Math.max(0.7, Number(nextZoom.toFixed(2))));
  }

  function mapCoverageLabel(map: RepositoryMap) {
    const partial = map.truncated || {
      commits: false,
      branches: false,
      tags: false,
      pull_requests: false
    };
    const parts = [];
    if (partial.commits) parts.push(`${formatNumber(map.limits?.commits || map.commits.length)} commit`);
    if (partial.branches) parts.push(`${formatNumber(map.limits?.branches || map.branches.length)} branch`);
    if (partial.tags) parts.push(`${formatNumber(map.limits?.tags || map.tags.length)} tag`);
    if (partial.pull_requests) parts.push(`${formatNumber(map.limits?.pull_requests || map.pull_requests.length)} PR`);
    return parts.length ? `Vista parziale: ultimi ${parts.join(', ')}` : 'Vista completa entro i limiti letti';
  }

  function mapStorageLabel(map: RepositoryMap) {
    if (map.storage?.mode === 'stored') return `Salvata ${formatDate(map.storage.saved_at || map.updated_at)}`;
    if (map.storage?.mode === 'delta') return `Delta aggiornato ${formatDate(map.storage.saved_at || map.updated_at)}`;
    if (map.storage?.mode === 'force') return `Rigenerata ${formatDate(map.storage.saved_at || map.updated_at)}`;
    if (map.storage?.mode === 'memory') return `Salvata ${formatDate(map.storage.saved_at || map.updated_at)} | cache`;
    if (map.cache?.hit) return 'Cache memoria';
    return `Generata ${formatDate(map.updated_at)}`;
  }

  function hasMapDelta(map: RepositoryMap) {
    const delta = map.delta;
    if (!delta) return false;
    return (
      delta.commits.new > 0 ||
      delta.commits.removed > 0 ||
      delta.branches.new > 0 ||
      delta.branches.removed > 0 ||
      delta.branches.changed > 0 ||
      delta.tags.new > 0 ||
      delta.tags.removed > 0 ||
      delta.pull_requests.new > 0 ||
      delta.pull_requests.removed > 0 ||
      delta.pull_requests.changed > 0 ||
      delta.findings.new > 0 ||
      delta.findings.resolved > 0 ||
      delta.default_branch_changed
    );
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

  function stopGraphInteraction(event: PointerEvent) {
    event.stopPropagation();
  }

  function selectCommit(commit: RepositoryMapCommit) {
    selected = { type: 'commit', item: commit };
  }

  function selectBranch(branch: RepositoryMapBranch) {
    selected = { type: 'branch', item: branch };
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

  onMount(() => {
    restoreMapState();
    mapStateReady = true;
    loadJobs();
  });
</script>

<section class="page-head">
  <div>
    <p class="eyebrow">Repository intelligence</p>
    <h2>Mappa repo</h2>
  </div>
  <button class="ghost" type="button" disabled={!selectedUrl || loadingMap} on:click={() => loadMap('stored')}>
    {loadingMap ? 'Analisi in corso' : 'Apri mappa'}
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
        <span>{formatNumber(filteredRepositories.length)} / {formatNumber(repositories.length)} repo</span>
      </div>
      <div class="map-repo-tools">
        <label>
          <span>Cerca repo</span>
          <input type="search" bind:value={repoSearch} placeholder="owner/name o URL" />
        </label>
        <label>
          <span>Ordina</span>
          <select bind:value={repoSort}>
            <option value="recent">Ultima scansione</option>
            <option value="risk">Finding</option>
            <option value="name">Nome</option>
          </select>
        </label>
      </div>
      <div class="repo-map-list">
        {#if filteredRepositories.length === 0}
          <div class="empty compact">Nessun repository corrisponde al filtro.</div>
        {/if}
        {#each filteredRepositories as repository}
          <button
            class:active={repository.url === selectedUrl}
            class:risky={repository.latestFindings > 0}
            class="repo-map-item"
            type="button"
            on:click={() => selectUrl(repository.url)}
          >
            <span class="repo-map-item-head">
              <strong>{repository.name}</strong>
              <em>{formatNumber(repository.latestFindings)}</em>
            </span>
            <span>{repository.jobs} scan | {repository.lastScanAt ? formatDate(repository.lastScanAt) : 'mai'} | {repository.url}</span>
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
            <div class="map-coverage-strip" class:partial={repoMap.truncated && Object.values(repoMap.truncated).some(Boolean)}>
              <span>{mapCoverageLabel(repoMap)}</span>
              <span>{mapStorageLabel(repoMap)}</span>
            </div>

            <div class="map-toolbar" aria-label="Controlli mappa repository">
              <div class="segmented-control">
                <button type="button" on:click={zoomOut}>-</button>
                <button type="button" on:click={resetZoom}>{Math.round(zoom * 100)}%</button>
                <button type="button" on:click={zoomIn}>+</button>
              </div>
              <button class="ghost" type="button" on:click={fitGraphToViewport}>Adatta</button>
              <label><input type="checkbox" bind:checked={showBranches} /> Branch</label>
              <label><input type="checkbox" bind:checked={showTags} /> Tag</label>
              <label><input type="checkbox" bind:checked={showPullRequests} /> PR</label>
              <label><input type="checkbox" bind:checked={showFindings} /> Finding</label>
              <button class="ghost" type="button" disabled={loadingMap} on:click={() => loadMap('delta')}>Aggiorna delta</button>
              <button class="ghost" type="button" disabled={loadingMap} on:click={() => loadMap('force')}>Rigenera tutto</button>
              <button class="ghost ai-map-action" type="button" disabled={mapAiLoading} on:click={runMapAiAnalysis}>
                {mapAiLoading ? 'AI in corso' : mapAiAnalysis ? 'Rigenera analisi AI' : 'Analizza con AI'}
              </button>
            </div>

            {#if showBranches}
              <div class="branch-color-legend" aria-label="Legenda colori branch">
                {#each visibleBranchLegend(repoMap) as branch}
                  <button
                    class:default-branch={branch.is_default}
                    class="branch-legend-chip"
                    style={`--branch-color: ${branchColor(branch)}`}
                    type="button"
                    on:click={() => (selected = { type: 'branch', item: branch })}
                  >
                    <span></span>
                    <strong>{branch.name}</strong>
                  </button>
                {/each}
              </div>
            {/if}

            <div
              bind:this={graphViewport}
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
                viewBox={`0 0 ${graphWidth(repoMap)} ${graphHeight()}`}
                role="img"
              >
                <title>Commit graph for {repoMap.repository.name}</title>
                {#each graphLanes as lane}
                  <line
                    class:default-lane={lane === 2}
                    class="lane-guide"
                    style={`--lane-color: ${laneColor(lane)}`}
                    x1="36"
                    y1={laneY(lane)}
                    x2={graphWidth(repoMap) - 40}
                    y2={laneY(lane)}
                  />
                  <text
                    class:default-lane={lane === 2}
                    class="lane-name"
                    style={`--lane-color: ${laneColor(lane)}`}
                    x="38"
                    y={laneY(lane) - 12}
                  >
                    {lane === 2 ? 'main lane' : `lane ${lane + 1}`}
                  </text>
                {/each}
                {#each repoMap.commits as commit, index}
                  {#each commit.parents as parent}
                    {@const parentIndex = commitIndex(parent, repoMap)}
                    {#if parentIndex >= 0}
                      {@const parentCommit = repoMap.commits[parentIndex]}
                      <path
                        class="graph-edge"
                        d={edgePath(commitX(index), commitY(commit, index), commitX(parentIndex), commitY(parentCommit, parentIndex))}
                        style={`--branch-color: ${commitColor(commit, index)}`}
                      />
                    {/if}
                  {/each}
                {/each}

                {#if showTags}
                  {#each repoMap.tags as tag, index}
                    {@const tagIndex = commitIndex(tag.commit, repoMap)}
                    {#if tagIndex >= 0}
                      <line
                        class="tag-line"
                        style={`--branch-color: ${tagColor(tag, repoMap)}`}
                        x1={commitX(tagIndex)}
                        y1={graphHeight() - 72}
                        x2={commitX(tagIndex)}
                        y2={graphHeight() - 40}
                      />
                      <text
                        class="tag-label"
                        style={`--branch-color: ${tagColor(tag, repoMap)}`}
                        x={commitX(tagIndex) - 28}
                        y={graphHeight() - 44 + (index % 2) * 16}
                      >
                        {tag.name}
                      </text>
                    {/if}
                  {/each}
                {/if}

                {#if showBranches}
                  {#each repoMap.branches as branch, index}
                    {@const branchIndex = commitIndex(branch.commit, repoMap)}
                    {#if branchIndex >= 0}
                      <g
                        class="branch-marker"
                        role="button"
                        tabindex="0"
                        aria-label={`Seleziona branch ${branch.name}`}
                        style={`--branch-color: ${branchColor(branch)}`}
                        on:pointerdown={stopGraphInteraction}
                        on:click={() => selectBranch(branch)}
                        on:keydown={(event) => event.key === 'Enter' && selectBranch(branch)}
                      >
                        <line class="branch-line" x1={commitX(branchIndex)} y1="28" x2={commitX(branchIndex)} y2="58" />
                        <rect
                          class:default-branch={branch.is_default}
                          class="branch-pill"
                          x={commitX(branchIndex) - branchLabelWidth(branch.name) / 2}
                          y={10 + (index % 2) * 20}
                          width={branchLabelWidth(branch.name)}
                          height="18"
                          rx="9"
                          ry="9"
                        />
                        <text
                          class:default-branch={branch.is_default}
                          class="branch-label"
                          x={commitX(branchIndex) - branchLabelWidth(branch.name) / 2 + 10}
                          y={23 + (index % 2) * 20}
                        >
                          {branch.name}
                        </text>
                      </g>
                    {/if}
                  {/each}
                {/if}

                {#if showPullRequests}
                  {#each repoMap.pull_requests as pr, index}
                    {@const branch = branchForPr(pr, repoMap)}
                    {#if branch}
                      {@const prIndex = commitIndex(branch.commit, repoMap)}
                      {#if prIndex >= 0}
                        <line
                          class="pr-line"
                          style={`--branch-color: ${branchColor(branch)}`}
                          x1={commitX(prIndex)}
                          y1="54"
                          x2={commitX(prIndex) + 34}
                          y2={78 + (index % 3) * 18}
                        />
                        <text class="pr-label" style={`--branch-color: ${branchColor(branch)}`} x={commitX(prIndex) + 38} y={82 + (index % 3) * 18}>PR #{pr.number}</text>
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
                    aria-label={`Seleziona commit ${commit.short}`}
                    style={`--branch-color: ${commitColor(commit, index)}`}
                    on:pointerdown={stopGraphInteraction}
                    on:click={() => selectCommit(commit)}
                    on:keydown={(event) => event.key === 'Enter' && selectCommit(commit)}
                  >
                    <rect
                      class="commit-hitbox"
                      x={commitX(index) - 36}
                      y={commitY(commit, index) - 30}
                      width="72"
                      height="74"
                      rx="12"
                      ry="12"
                    />
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

        </section>

        {#if repoMap.delta}
          <section class="panel map-delta-panel">
            <div class="section-title">
              <div>
                <p class="eyebrow">Delta mappa</p>
                <h3>{hasMapDelta(repoMap) ? "Cambiamenti dall'ultimo snapshot" : 'Nessuna variazione rilevante'}</h3>
              </div>
              <span>{formatDate(repoMap.delta.generated_at)}</span>
            </div>
            <div class="map-delta-grid">
              <div>
                <strong>{formatNumber(repoMap.delta.commits.new)}</strong>
                <span>Commit nuovi</span>
              </div>
              <div>
                <strong>{formatNumber(repoMap.delta.branches.changed + repoMap.delta.branches.new)}</strong>
                <span>Branch mossi/nuovi</span>
              </div>
              <div>
                <strong>{formatNumber(repoMap.delta.pull_requests.changed + repoMap.delta.pull_requests.new)}</strong>
                <span>PR cambiate/nuove</span>
              </div>
              <div>
                <strong class:risk-critical={repoMap.delta.findings.delta > 0} class:risk-clean={repoMap.delta.findings.delta < 0}>
                  {repoMap.delta.findings.delta > 0 ? '+' : ''}{formatNumber(repoMap.delta.findings.delta)}
                </strong>
                <span>Delta finding</span>
              </div>
            </div>
            {#if repoMap.delta.branches.changed_items.length}
              <div class="map-delta-list">
                {#each repoMap.delta.branches.changed_items as branch}
                  <span>{branch.name}: {branch.previous} -> {branch.current}</span>
                {/each}
              </div>
            {/if}
          </section>
        {/if}

        <section class="panel map-ai-panel">
          <div class="section-title">
            <div>
              <p class="eyebrow">LM Studio</p>
              <h3>Analisi AI della mappa</h3>
            </div>
            {#if mapAiAnalysis}
              <span>{mapAiAnalysis.model} | {formatDate(mapAiAnalysis.generated_at)}</span>
            {:else}
              <span>Locale</span>
            {/if}
          </div>

          {#if mapAiLoading}
            <div class="map-ai-loading">
              <div class="skeleton-line wide"></div>
              <p>LM Studio sta leggendo branch, tag, PR, commit e finding redatti.</p>
            </div>
          {:else if mapAiError}
            <div class="inline-error">{mapAiError}</div>
          {:else if mapAiAnalysis?.content}
            <div class="ai-meta">
              <span>{mapAiAnalysis.input.commits_sent} commit inviati</span>
              <span>{mapAiAnalysis.input.findings_sent} finding inviati</span>
              <span>{mapAiAnalysis.input.branches} branch</span>
            </div>
            <article class="markdown-body map-ai-markdown">
              {@html renderMarkdown(mapAiAnalysis.content)}
            </article>
          {:else}
            <div class="map-ai-empty">
              <p>
                Genera una lettura locale della struttura: branch stale, flusso PR, tag/release,
                commit con finding e priorita' operative.
              </p>
              <button type="button" on:click={runMapAiAnalysis}>Analizza mappa con LM Studio</button>
            </div>
          {/if}
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

        {#if selected}
          <aside
            class="selection-drawer"
            style={`--selection-color: ${selectedColor(selected, repoMap)}`}
            aria-label="Dettaglio elemento selezionato"
          >
            <div class="selection-drawer-handle"></div>
            <div class="selection-drawer-head">
              <div>
                <p class="eyebrow">{selectedKind(selected)}</p>
                <h3>{selectedTitle(selected)}</h3>
              </div>
              <div class="selection-drawer-actions">
                <button class="ghost ai-map-action" type="button" disabled={selectedAiLoading} on:click={runSelectedAiAnalysis}>
                  {selectedAiLoading ? 'AI in corso' : selectedAiAnalysis ? 'Rigenera AI' : 'Analizza nodo'}
                </button>
                <button class="ghost close-drawer" type="button" aria-label="Chiudi dettaglio selezione" on:click={() => (selected = null)}>
                  Chiudi
                </button>
              </div>
            </div>

            {#if selected.type === 'commit'}
              <div class="drawer-grid">
                <div class="drawer-primary">
                  <p>{selected.item.subject}</p>
                  <div class="drawer-meta-grid">
                    <span><strong>Autore</strong>{selected.item.author}</span>
                    <span><strong>Data</strong>{formatDate(selected.item.timestamp)}</span>
                    <span><strong>Posizione</strong>{commitPosition(selected.item, repoMap)}</span>
                    <span><strong>Lane</strong>{commitLaneNumber(selected.item, repoMap)}</span>
                  </div>
                  <code>{selected.item.hash}</code>
                </div>
                <div class="drawer-side">
                  <div class="drawer-stat-row">
                    <span>Parent</span>
                    <strong>{formatNumber(selected.item.parents.length)}</strong>
                  </div>
                  <div class="drawer-stat-row">
                    <span>Finding</span>
                    <strong class:risk-critical={selected.item.findings > 0}>{formatNumber(selected.item.findings)}</strong>
                  </div>
                  <div class="drawer-chip-list">
                    {#each branchesForCommit(selected.item, repoMap) as branch}
                      <button type="button" on:click={() => (selected = { type: 'branch', item: branch })}>{branch.name}</button>
                    {/each}
                    {#each tagsForCommit(selected.item, repoMap) as tag}
                      <button type="button" on:click={() => (selected = { type: 'tag', item: tag })}>{tag.name}</button>
                    {/each}
                    {#if branchesForCommit(selected.item, repoMap).length === 0 && tagsForCommit(selected.item, repoMap).length === 0}
                      <span>Nessuna label diretta</span>
                    {/if}
                  </div>
                </div>
              </div>

              {#if commitFindings(selected.item, repoMap).length}
                <div class="drawer-section">
                  <p class="eyebrow">Finding sul commit</p>
                  <div class="map-finding-grid compact">
                    {#each commitFindings(selected.item, repoMap) as finding}
                      <button class="finding-chip-row" type="button" on:click={() => (selected = { type: 'finding', item: finding })}>
                        <span class={severityClass(finding)}>{finding.severity || 'finding'}</span>
                        <strong>{finding.rule || 'unknown-rule'}</strong>
                        <em>{finding.file}:{finding.line || '?'}</em>
                      </button>
                    {/each}
                  </div>
                </div>
              {/if}
            {:else if selected.type === 'branch'}
              <div class="drawer-grid">
                <div class="drawer-primary">
                  <p>{selected.item.subject || 'Branch senza messaggio recente.'}</p>
                  <div class="drawer-meta-grid">
                    <span><strong>Stato</strong>{freshness(selected.item)}</span>
                    <span><strong>Ultimo update</strong>{formatDate(selected.item.updated_at)}</span>
                    <span><strong>Remote</strong>{selected.item.remote_name || 'n/d'}</span>
                    <span><strong>Default</strong>{selected.item.is_default ? 'Si' : 'No'}</span>
                  </div>
                  <code>{selected.item.commit}</code>
                </div>
                <div class="drawer-side">
                  <div class="drawer-stat-row">
                    <span>Finding</span>
                    <strong class:risk-critical={selected.item.findings > 0}>{formatNumber(selected.item.findings)}</strong>
                  </div>
                  <div class="drawer-stat-row">
                    <span>PR collegate</span>
                    <strong>{formatNumber(pullRequestsForBranch(selected.item, repoMap).length)}</strong>
                  </div>
                  <button class="button-link" type="button" on:click={() => selectCommitByHash(selected?.type === 'branch' ? selected.item.commit : null, repoMap)}>
                    Apri commit head
                  </button>
                </div>
              </div>
              {#if pullRequestsForBranch(selected.item, repoMap).length}
                <div class="drawer-section">
                  <p class="eyebrow">Pull request collegate</p>
                  <div class="pr-stack compact">
                    {#each pullRequestsForBranch(selected.item, repoMap) as pr}
                      <button class="pr-row" type="button" on:click={() => (selected = { type: 'pr', item: pr })}>
                        <span class={prClass(pr)}>{pr.state}</span>
                        <strong>#{pr.number} {pr.title}</strong>
                        <em>{pr.head} -> {pr.base}</em>
                      </button>
                    {/each}
                  </div>
                </div>
              {/if}
            {:else if selected.type === 'finding'}
              <div class="drawer-grid">
                <div class="drawer-primary">
                  <p>{selected.item.description || 'Finding collegato all ultima scansione Gitleaks.'}</p>
                  <div class="drawer-meta-grid">
                    <span><strong>Severita</strong>{selected.item.severity || 'finding'}</span>
                    <span><strong>File</strong>{selected.item.file || 'n/d'}</span>
                    <span><strong>Linea</strong>{selected.item.line || '?'}</span>
                    <span><strong>Fingerprint</strong>{selected.item.fingerprint ? 'Presente' : 'n/d'}</span>
                  </div>
                  {#if selected.item.commit}<code>{selected.item.commit}</code>{/if}
                </div>
                <div class="drawer-side">
                  <span class={severityClass(selected.item)}>{selected.item.severity || 'finding'}</span>
                  {#if selected.item.link}
                    <a class="button-link" href={selected.item.link} target="_blank" rel="noreferrer">Apri origine</a>
                  {/if}
                  {#if selected.item.commit && commitByHash(selected.item.commit, repoMap)}
                    <button class="button-link" type="button" on:click={() => selectCommitByHash(selected?.type === 'finding' ? selected.item.commit : null, repoMap)}>
                      Apri commit
                    </button>
                  {/if}
                </div>
              </div>
            {:else if selected.type === 'tag'}
              <div class="drawer-grid">
                <div class="drawer-primary">
                  <p>{selected.item.subject || 'Tag senza messaggio.'}</p>
                  <div class="drawer-meta-grid">
                    <span><strong>Creato</strong>{formatDate(selected.item.created_at)}</span>
                    <span><strong>Commit breve</strong>{selected.item.short}</span>
                    <span><strong>Commit in vista</strong>{commitIndex(selected.item.commit, repoMap) >= 0 ? 'Si' : 'No'}</span>
                    <span><strong>Tipo</strong>Release marker</span>
                  </div>
                  <code>{selected.item.commit}</code>
                </div>
                <div class="drawer-side">
                  {#if commitByHash(selected.item.commit, repoMap)}
                    <button class="button-link" type="button" on:click={() => selectCommitByHash(selected?.type === 'tag' ? selected.item.commit : null, repoMap)}>
                      Apri commit taggato
                    </button>
                  {/if}
                </div>
              </div>
            {:else if selected.type === 'pr'}
              <div class="drawer-grid">
                <div class="drawer-primary">
                  <p>{selected.item.title}</p>
                  <div class="drawer-meta-grid">
                    <span><strong>Stato</strong>{selected.item.state}{selected.item.is_draft ? ' draft' : ''}</span>
                    <span><strong>Autore</strong>{selected.item.author || 'n/d'}</span>
                    <span><strong>Creata</strong>{isoDate(selected.item.created_at)}</span>
                    <span><strong>Aggiornata</strong>{isoDate(selected.item.updated_at)}</span>
                  </div>
                  <code>{selected.item.head || 'head n/d'} -> {selected.item.base || 'base n/d'}</code>
                </div>
                <div class="drawer-side">
                  <span class={prClass(selected.item)}>{selected.item.state}</span>
                  {#if selected.item.merged_at}<span>Merged {isoDate(selected.item.merged_at)}</span>{/if}
                  {#if selected.item.url}<a class="button-link" href={selected.item.url} target="_blank" rel="noreferrer">Apri PR</a>{/if}
                </div>
              </div>
            {/if}

            {#if selectedAiLoading}
              <div class="drawer-ai-panel">
                <div class="skeleton-line wide"></div>
                <p>LM Studio sta analizzando il nodo selezionato nel contesto della mappa.</p>
              </div>
            {:else if selectedAiError}
              <div class="inline-error">{selectedAiError}</div>
            {:else if selectedAiAnalysis?.content}
              <div class="drawer-ai-panel">
                <div class="ai-meta">
                  <span>{selectedAiAnalysis.model}</span>
                  <span>{formatDate(selectedAiAnalysis.generated_at)}</span>
                  {#if selectedAiAnalysis.input.focus}<span>{selectedAiAnalysis.input.focus}</span>{/if}
                </div>
                <article class="markdown-body map-ai-markdown compact">
                  {@html renderMarkdown(selectedAiAnalysis.content)}
                </article>
              </div>
            {/if}
          </aside>
        {/if}
      {:else}
        <section class="panel map-intro">
          <p class="eyebrow">MVP locale</p>
          <h3>Genera una mappa strutturale del repository</h3>
          <p>
            LeakLane usera' un clone temporaneo per leggere branch, tag, ultimi commit e PR GitHub.
            I finding dell'ultima scansione vengono sovrapposti ai commit quando il report contiene l'hash.
          </p>
          <button type="button" disabled={!selectedUrl} on:click={() => loadMap('stored')}>Apri mappa repository</button>
        </section>
      {/if}
    </div>
  </section>
{/if}

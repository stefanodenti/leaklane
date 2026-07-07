import type {
  AiStatus,
  DashboardMetric,
  DiffResponse,
  GithubStatus,
  HealthStatus,
  JobPreview,
  PrerequisitesStatus,
  RepositoryMap,
  RepositoryMapAiAnalysis,
  ScanJobDetail,
  ScanPayload,
  SearchResult
} from './types';

const API_BASE = import.meta.env.VITE_API_BASE_URL || defaultApiBase();

function defaultApiBase() {
  if (typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window) {
    return 'http://127.0.0.1:8787';
  }
  return '';
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error ?? `Request failed: ${response.status}`);
  }
  return payload as T;
}

export function getDashboard() {
  return request<DashboardMetric>('/api/dashboard');
}

export function getGithubStatus() {
  return request<GithubStatus>('/api/github/status');
}

export function getAiStatus() {
  return request<AiStatus>('/api/ai/status');
}

export function getHealth() {
  return request<HealthStatus>('/api/health');
}

export function getPrerequisites() {
  return request<PrerequisitesStatus>('/api/prerequisites');
}

export async function searchRepositories(query: string) {
  const payload = await request<{ items: SearchResult[] }>(`/api/search?q=${encodeURIComponent(query)}`);
  return payload.items;
}

export function getDiffs() {
  return request<DiffResponse>('/api/diffs');
}

export function getRepositoryMap(url: string, mode: 'stored' | 'delta' | 'force' = 'stored') {
  const query = new URLSearchParams({ url });
  query.set('mode', mode);
  return request<RepositoryMap>(`/api/repository-map?${query.toString()}`);
}

export async function generateRepositoryMapAiAnalysis(
  url: string,
  map: RepositoryMap,
  focus?: Record<string, unknown>
) {
  const payload = await request<{ analysis: RepositoryMapAiAnalysis }>('/api/repository-map/ai-analysis', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ url, map, focus, ai: {} })
  });
  return payload.analysis;
}

export async function getJobs() {
  const payload = await request<{ jobs: JobPreview[] }>('/api/jobs');
  return payload.jobs;
}

export async function getJob(id: string) {
  const payload = await request<{ job: ScanJobDetail }>(`/api/jobs/${encodeURIComponent(id)}`);
  return payload.job;
}

export async function startScan(payload: ScanPayload) {
  const data = await request<{ job: ScanJobDetail }>('/api/scan', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(payload)
  });
  return data.job;
}

export async function generateAiAnalysis(id: string) {
  const data = await request<{ job: ScanJobDetail }>(`/api/jobs/${encodeURIComponent(id)}/ai-analysis`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ ai: {} })
  });
  return data.job;
}

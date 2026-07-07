export type RiskLevel = 'critical' | 'high' | 'medium' | 'low' | 'clean';

export type DashboardSummary = {
  organizations: number;
  repositories: number;
  findings: number;
  risky_repositories: number;
  jobs: number;
};

export type DashboardMetric = {
  updated_at: number;
  summary: DashboardSummary;
  organizations: OrganizationRisk[];
  hotspots: Hotspot[];
  timeline: TimelineItem[];
};

export type OrganizationRisk = {
  name: string;
  provider: string;
  repositories: number;
  clean: number;
  findings: number;
  risk_score: number;
  risk_level: RiskLevel;
  last_scan: number;
  severity: Record<'critical' | 'high' | 'medium' | 'low', number>;
  repos: RepoRisk[];
  top_rules: [string, number][];
};

export type RepoRisk = {
  name: string;
  url: string;
  status: string;
  findings: number;
  risk_score: number;
  risk_level: RiskLevel;
  last_scan: number;
  top_rules: [string, number][];
  job_id: string;
};

export type Hotspot = {
  organization: string;
  name: string;
  url: string;
  findings: number;
  risk_score: number;
  risk_level: RiskLevel;
  top_rules: [string, number][];
  last_scan: number;
  job_id: string;
};

export type TimelineItem = {
  id: string;
  started_at: number;
  status: string;
  repositories: number;
  findings: number;
};

export type DiffSummary = {
  repositories: number;
  new: number;
  resolved: number;
  unchanged: number;
};

export type DiffResponse = {
  updated_at: number;
  summary: DiffSummary;
  comparisons: DiffComparison[];
};

export type DiffComparison = {
  repository: string;
  url: string;
  organization: string;
  latest_job_id: string;
  previous_job_id: string;
  latest_at: number;
  previous_at: number;
  latest_findings: number;
  previous_findings: number;
  new: number;
  resolved: number;
  unchanged: number;
  delta: number;
  new_items: FindingPreview[];
  resolved_items: FindingPreview[];
};

export type FindingPreview = {
  rule?: string;
  file?: string;
  line?: string | number;
  commit?: string;
};

export type JobPreview = {
  id: string;
  urls: string[];
  mode: string;
  status: string;
  started_at: number;
  finished_at?: number;
  results: Array<{ name: string; status: string; findings: number }>;
  ai_status: string;
  ai_error?: string;
  elapsed_seconds: number;
};

export type JobResult = {
  name: string;
  url?: string;
  status: string;
  findings: number;
  report_url?: string | null;
  items?: FindingDetail[];
  error?: string | null;
};

export type FindingDetail = {
  rule?: string;
  description?: string | null;
  file?: string;
  line?: string | number;
  end_line?: string | number | null;
  start_column?: string | number | null;
  end_column?: string | number | null;
  commit?: string | null;
  author?: string | null;
  email?: string | null;
  date?: string | null;
  fingerprint?: string | null;
  link?: string | null;
};

export type AiAnalysisPreview = {
  model?: string;
  generated_at?: number;
  content?: string;
};

export type ScanJobDetail = {
  id: string;
  urls: string[];
  mode: string;
  status: string;
  started_at: number;
  finished_at?: number | null;
  current?: string | null;
  logs: string[];
  results: JobResult[];
  error?: string | null;
  ai_status: string;
  ai_error?: string | null;
  ai_analysis?: AiAnalysisPreview | null;
  elapsed_seconds: number;
};

export type AiStatus = {
  available: boolean;
  base_url: string;
  models: string[];
  selected_model?: string | null;
  error?: string | null;
};

export type HealthStatus = {
  ok: boolean;
  service: string;
  version: string;
  docs_url?: string;
  openapi_url?: string;
  reports_dir: string;
  jobs: number;
  time: number;
};

export type CommandCheck = {
  installed: boolean;
  required: boolean;
  path?: string | null;
  version?: string | null;
  error?: string | null;
};

export type PrerequisitesStatus = {
  ready: boolean;
  checks: Record<'python' | 'git' | 'gitleaks' | 'gh', CommandCheck>;
  github: GithubStatus;
  lm_studio: AiStatus;
  reports_dir: string;
  backend_url: string;
  backend_version?: string;
  docs_url?: string;
  openapi_url?: string;
};

export type ScanPayload = {
  urls: string[];
  mode: 'git' | 'dir';
  timeout: number;
  ai: {
    model: string;
    auto_analyze: boolean;
    system_prompt: string;
    additional_instructions: string;
  };
};

export type GithubStatus = {
  installed: boolean;
  authenticated: boolean;
  ready: boolean;
  account?: string | null;
  message: string;
  setup_command: string;
};

export type SearchResult = {
  name: string;
  url: string;
  description?: string;
  stars?: number | null;
  language?: string;
  updated_at?: string;
  visibility?: string;
  provider?: string;
};

export type StagedRepository = {
  name: string;
  url: string;
  description?: string;
  provider?: string;
  language?: string;
  stars?: number | null;
};

export type RepositoryMapSummary = {
  branches: number;
  tags: number;
  pull_requests: number;
  commits: number;
  findings: number;
  stale_branches: number;
};

export type RepositoryMapFinding = FindingPreview & {
  description?: string | null;
  fingerprint?: string | null;
  link?: string | null;
  severity?: RiskLevel | string;
};

export type RepositoryMapCommit = {
  hash: string;
  short: string;
  parents: string[];
  timestamp: number;
  author: string;
  subject: string;
  findings: number;
};

export type RepositoryMapBranch = {
  name: string;
  remote_name: string;
  commit: string;
  short: string;
  updated_at: number;
  subject: string;
  is_default: boolean;
  findings: number;
};

export type RepositoryMapTag = {
  name: string;
  commit: string;
  short: string;
  created_at: number;
  subject: string;
};

export type RepositoryPullRequest = {
  number: number;
  title: string;
  state: string;
  author?: string | null;
  head?: string | null;
  base?: string | null;
  url?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  merged_at?: string | null;
  is_draft?: boolean | null;
};

export type RepositoryMap = {
  repository: {
    name: string;
    url: string;
    provider: string;
    default_branch?: string | null;
    latest_job_id?: string | null;
    latest_findings: number;
  };
  summary: RepositoryMapSummary;
  branches: RepositoryMapBranch[];
  tags: RepositoryMapTag[];
  pull_requests: RepositoryPullRequest[];
  commits: RepositoryMapCommit[];
  findings: RepositoryMapFinding[];
  limits?: {
    commits: number;
    branches: number;
    tags: number;
    pull_requests: number;
  };
  truncated?: {
    commits: boolean;
    branches: boolean;
    tags: boolean;
    pull_requests: boolean;
  };
  cache?: {
    hit: boolean;
    generated_at: number;
    ttl_seconds: number;
  };
  updated_at: number;
};

export type RepositoryMapAiAnalysis = {
  generated_at: number;
  base_url: string;
  model: string;
  content: string;
  input: {
    repository: string;
    branches: number;
    tags: number;
    pull_requests: number;
    commits_sent: number;
    findings_sent: number;
    requested_model: string;
    focus?: string | null;
  };
};

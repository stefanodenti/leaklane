#!/usr/bin/env python3
"""Local web UI for scanning public GitHub repositories with Gitleaks."""

from __future__ import annotations

import json
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import asdict, dataclass, field
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

from scan_public_repos import (
    ScanResult,
    clone_repo,
    load_findings,
    normalize_repo_url,
    repo_name_from_url,
    require_command,
    scan_repo,
    write_summary,
)


ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "web"
REPORT_ROOT = Path(os.environ.get("REPO_SCANNER_REPORT_ROOT", ROOT / "gitleaks-web-reports")).expanduser()
REPOSITORY_MAP_ROOT = REPORT_ROOT / "repository-maps"
BACKEND_VERSION = "0.3.1-alpha.1"
LM_STUDIO_BASE_URL = "http://127.0.0.1:1234/v1"
AI_ANALYSIS_FINDING_LIMIT = 6
AI_ANALYSIS_MAX_TOKENS = 4096
AI_ANALYSIS_TIMEOUT_SECONDS = 600
jobs_lock = threading.Lock()
jobs: dict[str, "ScanJob"] = {}
repository_map_cache: dict[str, tuple[float, dict]] = {}
REPOSITORY_MAP_CACHE_SECONDS = 600
REPOSITORY_MAP_COMMIT_LIMIT = 120
REPOSITORY_MAP_BRANCH_LIMIT = 40
REPOSITORY_MAP_TAG_LIMIT = 30
REPOSITORY_MAP_PR_LIMIT = 30


class EmptyModelResponse(RuntimeError):
    """Raised when LM Studio returns only internal reasoning and no final content."""


@dataclass
class ScanJob:
    id: str
    urls: list[str]
    mode: str
    status: str = "queued"
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    current: str | None = None
    logs: list[str] = field(default_factory=list)
    results: list[dict] = field(default_factory=list)
    reports_dir: str | None = None
    summary_path: str | None = None
    error: str | None = None
    ai_status: str = "not_started"
    ai_analysis: dict | None = None
    ai_error: str | None = None
    ai_config: dict = field(default_factory=dict)

    def log(self, message: str) -> None:
        with jobs_lock:
            self.logs.append(message)

    def to_dict(self) -> dict:
        data = asdict(self)
        data["elapsed_seconds"] = round((self.finished_at or time.time()) - self.started_at, 1)
        return data

    def to_preview_dict(self) -> dict:
        return {
            "id": self.id,
            "urls": self.urls,
            "mode": self.mode,
            "status": self.status,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "results": [
                {
                    "name": result.get("name"),
                    "status": result.get("status"),
                    "findings": result.get("findings", 0),
                }
                for result in self.results
            ],
            "error": self.error,
            "ai_status": self.ai_status,
            "ai_error": self.ai_error,
            "ai_analysis": {
                "model": self.ai_analysis.get("model"),
                "generated_at": self.ai_analysis.get("generated_at"),
            }
            if self.ai_analysis
            else None,
            "elapsed_seconds": round((self.finished_at or time.time()) - self.started_at, 1),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ScanJob":
        return cls(
            id=data["id"],
            urls=data.get("urls", []),
            mode=data.get("mode", "git"),
            status=data.get("status", "completed"),
            started_at=data.get("started_at", time.time()),
            finished_at=data.get("finished_at"),
            current=data.get("current"),
            logs=data.get("logs", []),
            results=data.get("results", []),
            reports_dir=data.get("reports_dir"),
            summary_path=data.get("summary_path"),
            error=data.get("error"),
            ai_status=data.get("ai_status", "not_started"),
            ai_analysis=data.get("ai_analysis"),
            ai_error=data.get("ai_error"),
            ai_config=data.get("ai_config") or {},
        )


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/":
            self.serve_file(STATIC_DIR / "index.html", "text/html; charset=utf-8")
            return
        if parsed.path == "/styles.css":
            self.serve_file(STATIC_DIR / "styles.css", "text/css; charset=utf-8")
            return
        if parsed.path == "/app.js":
            self.serve_file(STATIC_DIR / "app.js", "application/javascript; charset=utf-8")
            return
        if parsed.path == "/brand/leaklane-mark.svg":
            self.serve_file(STATIC_DIR / "brand" / "leaklane-mark.svg", "image/svg+xml; charset=utf-8")
            return
        if parsed.path == "/docs":
            self.serve_openapi_docs()
            return
        if parsed.path == "/openapi.json":
            self.send_json(openapi_spec())
            return
        if parsed.path == "/api/search":
            self.handle_search(parsed)
            return
        if parsed.path == "/api/health":
            self.send_json(health_status())
            return
        if parsed.path == "/api/prerequisites":
            self.send_json(prerequisites_status())
            return
        if parsed.path == "/api/github/status":
            self.send_json(github_cli_status())
            return
        if parsed.path == "/api/jobs":
            self.send_json(list_jobs())
            return
        if parsed.path == "/api/dashboard":
            self.send_json(risk_dashboard())
            return
        if parsed.path == "/api/repository-map":
            self.handle_repository_map(parsed)
            return
        if parsed.path == "/api/diffs":
            self.send_json(scan_diffs())
            return
        if parsed.path == "/api/ai/status":
            self.send_json(lm_studio_status())
            return
        if parsed.path.startswith("/api/reports/"):
            self.handle_report(parsed.path)
            return
        if parsed.path.startswith("/api/jobs/"):
            self.handle_job(parsed.path)
            return

        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/scan":
            self.handle_scan()
            return
        if parsed.path == "/api/repository-map/ai-analysis":
            self.handle_repository_map_ai_analysis()
            return
        if parsed.path.startswith("/api/jobs/") and parsed.path.endswith("/ai-analysis/content"):
            self.handle_ai_content(parsed.path)
            return
        if parsed.path.startswith("/api/jobs/") and parsed.path.endswith("/ai-analysis"):
            self.handle_ai_analysis(parsed.path)
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.end_headers()

    def handle_search(self, parsed: urllib.parse.ParseResult) -> None:
        query = urllib.parse.parse_qs(parsed.query).get("q", [""])[0].strip()
        provider = urllib.parse.parse_qs(parsed.query).get("provider", ["github"])[0].strip()
        if not query:
            self.send_json({"items": []})
            return
        if provider == "bitbucket":
            self.send_json(
                {
                    "error": (
                        "Bitbucket public repository search is no longer available through the public API. "
                        "Paste a public bitbucket.org repository URL manually."
                    )
                },
                HTTPStatus.BAD_GATEWAY,
            )
            return
        if provider != "github":
            self.send_json({"error": "Invalid search provider."}, HTTPStatus.BAD_REQUEST)
            return

        gh_status = github_cli_status()
        if gh_status.get("ready"):
            try:
                self.send_json({"items": github_cli_search(query), "source": "gh"})
            except Exception as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.BAD_GATEWAY)
            return

        github_query = urllib.parse.urlencode(
            {
                "q": query,
                "sort": "stars",
                "order": "desc",
                "per_page": "10",
            }
        )
        request = urllib.request.Request(
            f"https://api.github.com/search/repositories?{github_query}",
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "local-gitleaks-repo-scanner",
            },
        )

        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            self.send_json({"error": f"GitHub search failed: {detail}"}, HTTPStatus.BAD_GATEWAY)
            return
        except Exception as exc:
            self.send_json({"error": f"GitHub search failed: {exc}"}, HTTPStatus.BAD_GATEWAY)
            return

        items = [
            {
                "name": item.get("full_name"),
                "url": item.get("html_url"),
                "description": truncate(item.get("description") or "", 220),
                "stars": item.get("stargazers_count", 0),
                "language": item.get("language") or "Unknown",
                "updated_at": item.get("updated_at"),
            }
            for item in payload.get("items", [])
        ]
        self.send_json({"items": items})

    def handle_bitbucket_search(self, query: str) -> None:
        bitbucket_query = urllib.parse.urlencode(
            {
                "q": f'name~"{query}" OR full_name~"{query}"',
                "pagelen": "10",
                "fields": "values.full_name,values.links.html.href,values.description,values.language,values.updated_on",
            }
        )
        request = urllib.request.Request(
            f"https://api.bitbucket.org/2.0/repositories?{bitbucket_query}",
            headers={
                "Accept": "application/json",
                "User-Agent": "local-gitleaks-repo-scanner",
            },
        )

        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            self.send_json({"error": f"Bitbucket search failed: {detail}"}, HTTPStatus.BAD_GATEWAY)
            return
        except Exception as exc:
            self.send_json({"error": f"Bitbucket search failed: {exc}"}, HTTPStatus.BAD_GATEWAY)
            return

        items = [
            {
                "name": item.get("full_name"),
                "url": item.get("links", {}).get("html", {}).get("href"),
                "description": truncate(item.get("description") or "", 220),
                "stars": None,
                "language": item.get("language") or "Unknown",
                "updated_at": item.get("updated_on"),
                "provider": "Bitbucket",
            }
            for item in payload.get("values", [])
            if item.get("links", {}).get("html", {}).get("href")
        ]
        self.send_json({"items": items})

    def handle_scan(self) -> None:
        try:
            body = self.read_json()
            raw_urls = body.get("urls", [])
            mode = body.get("mode", "git")
            timeout = int(body.get("timeout") or 0)
            max_target_megabytes = body.get("maxTargetMegabytes")
            max_target_megabytes = int(max_target_megabytes) if max_target_megabytes else None
            urls = [normalize_repo_url(url) for url in raw_urls]
            ai_config = normalize_ai_config(body.get("ai") or {})
        except Exception as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return

        if mode not in {"git", "dir"}:
            self.send_json({"error": "Invalid scan mode."}, HTTPStatus.BAD_REQUEST)
            return
        if not urls:
            self.send_json({"error": "Add at least one repository."}, HTTPStatus.BAD_REQUEST)
            return

        job_id = f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
        job = ScanJob(id=job_id, urls=dedupe(urls), mode=mode, ai_config=ai_config)
        with jobs_lock:
            jobs[job_id] = job
        save_job(job)

        args = SimpleNamespace(
            mode=mode,
            redact=100,
            timeout=timeout,
            max_target_megabytes=max_target_megabytes,
            config=None,
        )
        thread = threading.Thread(target=run_scan_job, args=(job, args), daemon=True)
        thread.start()
        self.send_json({"job": job.to_dict()}, HTTPStatus.ACCEPTED)

    def handle_repository_map(self, parsed: urllib.parse.ParseResult) -> None:
        query = urllib.parse.parse_qs(parsed.query)
        url = query.get("url", [""])[0].strip()
        refresh = query.get("refresh", ["0"])[0].strip() in {"1", "true", "yes"}
        force = query.get("force", ["0"])[0].strip() in {"1", "true", "yes"}
        mode = query.get("mode", ["stored"])[0].strip()
        if force:
            mode = "force"
        elif refresh:
            mode = "delta"
        if not url:
            self.send_json({"error": "Repository URL is required."}, HTTPStatus.BAD_REQUEST)
            return
        try:
            payload = repository_map(normalize_repo_url(url), mode=mode)
        except Exception as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_GATEWAY)
            return
        self.send_json(payload)

    def handle_job(self, path: str) -> None:
        job_id = path.removeprefix("/api/jobs/").strip("/")
        with jobs_lock:
            job = jobs.get(job_id)
        if not job:
            self.send_json({"error": "Job not found."}, HTTPStatus.NOT_FOUND)
            return
        self.send_json({"job": job.to_dict()})

    def handle_ai_analysis(self, path: str) -> None:
        job_id = path.removeprefix("/api/jobs/").removesuffix("/ai-analysis").strip("/")
        try:
            body = self.read_json()
            ai_config = normalize_ai_config(body.get("ai") or {})
        except Exception as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        with jobs_lock:
            job = jobs.get(job_id)
            if job and job.ai_status == "running":
                self.send_json({"job": job.to_dict()}, HTTPStatus.ACCEPTED)
                return
        if not job:
            self.send_json({"error": "Job not found."}, HTTPStatus.NOT_FOUND)
            return
        thread = threading.Thread(target=generate_ai_analysis, args=(job, ai_config), daemon=True)
        thread.start()
        self.send_json({"job": job.to_dict()}, HTTPStatus.ACCEPTED)

    def handle_ai_content(self, path: str) -> None:
        job_id = path.removeprefix("/api/jobs/").removesuffix("/ai-analysis/content").strip("/")
        try:
            body = self.read_json()
            content = str(body.get("content") or "").strip()
        except Exception as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if not content:
            self.send_json({"error": "Markdown content is empty."}, HTTPStatus.BAD_REQUEST)
            return
        with jobs_lock:
            job = jobs.get(job_id)
        if not job:
            self.send_json({"error": "Job not found."}, HTTPStatus.NOT_FOUND)
            return
        if not job.ai_analysis:
            job.ai_analysis = {
                "generated_at": time.time(),
                "base_url": LM_STUDIO_BASE_URL,
                "model": "manual-edit",
                "input": {},
            }
        job.ai_analysis["content"] = content
        job.ai_analysis["edited_at"] = time.time()
        job.ai_status = "completed"
        job.ai_error = None
        save_ai_analysis(job)
        save_job(job)
        self.send_json({"job": job.to_dict()})

    def handle_repository_map_ai_analysis(self) -> None:
        try:
            body = self.read_json()
            raw_url = str(body.get("url") or "").strip()
            if not raw_url:
                self.send_json({"error": "Repository URL is required."}, HTTPStatus.BAD_REQUEST)
                return
            try:
                url = normalize_repo_url(raw_url)
            except SystemExit as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            map_payload = body.get("map") if isinstance(body.get("map"), dict) else None
            focus_payload = body.get("focus") if isinstance(body.get("focus"), dict) else None
            ai_config = normalize_ai_config(body.get("ai") or {})
        except Exception as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        try:
            analysis = generate_repository_map_ai_analysis(url, map_payload, ai_config, focus_payload)
        except Exception as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_GATEWAY)
            return
        self.send_json({"analysis": analysis})

    def handle_report(self, path: str) -> None:
        parts = path.removeprefix("/api/reports/").strip("/").split("/")
        if len(parts) != 2:
            self.send_json({"error": "Invalid report path."}, HTTPStatus.BAD_REQUEST)
            return

        job_id, report_name = parts
        report_path = (REPORT_ROOT / job_id / report_name).resolve()
        report_root = REPORT_ROOT.resolve()
        if report_root not in report_path.parents or not report_path.name.endswith(".json"):
            self.send_json({"error": "Invalid report path."}, HTTPStatus.BAD_REQUEST)
            return
        if not report_path.exists():
            self.send_json({"error": "Report not found."}, HTTPStatus.NOT_FOUND)
            return

        data = report_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="{report_path.name}"')
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def serve_file(self, path: Path, content_type: str) -> None:
        if not path.exists():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def serve_openapi_docs(self) -> None:
        data = openapi_docs_html().encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def send_json(self, payload: dict | list, status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "86400")
        super().end_headers()

    def log_message(self, format: str, *args: object) -> None:
        return


def dedupe(urls: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for url in urls:
        if url not in seen:
            output.append(url)
            seen.add(url)
    return output


def truncate(value: str, limit: int) -> str:
    value = " ".join(value.split())
    if len(value) <= limit:
        return value
    return f"{value[: limit - 1].rstrip()}..."


def run_local_command(command: list[str], timeout: int | None = 20) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=timeout,
    )


def github_cli_status() -> dict:
    if shutil.which("gh") is None:
        return {
            "installed": False,
            "authenticated": False,
            "ready": False,
            "account": None,
            "message": "GitHub CLI non e' installata.",
            "setup_command": "brew install gh && gh auth login -h github.com",
        }

    try:
        result = run_local_command(["gh", "auth", "status", "-h", "github.com"], timeout=12)
    except Exception as exc:
        return {
            "installed": True,
            "authenticated": False,
            "ready": False,
            "account": None,
            "message": f"Impossibile verificare GitHub CLI: {exc}",
            "setup_command": "gh auth login -h github.com",
        }

    output = "\n".join(part for part in [result.stdout.strip(), result.stderr.strip()] if part)
    account = github_cli_current_account()
    ready = result.returncode == 0
    return {
        "installed": True,
        "authenticated": ready,
        "ready": ready,
        "account": account,
        "message": "GitHub CLI collegata." if ready else first_status_line(output, "GitHub CLI non autenticata."),
        "setup_command": "gh auth login -h github.com",
    }


def github_cli_current_account() -> str | None:
    try:
        result = run_local_command(["gh", "api", "user", "--jq", ".login"], timeout=12)
    except Exception:
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def health_status() -> dict:
    return {
        "ok": True,
        "service": "leaklane",
        "version": BACKEND_VERSION,
        "docs_url": "http://127.0.0.1:8787/docs",
        "openapi_url": "http://127.0.0.1:8787/openapi.json",
        "reports_dir": str(REPORT_ROOT),
        "jobs": len(jobs),
        "time": time.time(),
    }


def openapi_docs_html() -> str:
    return """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>LeakLane API Docs</title>
    <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css" />
    <style>
      body { margin: 0; background: #f6f7f4; }
      .topbar { display: none; }
      .swagger-ui .info { margin: 28px 0; }
    </style>
  </head>
  <body>
    <div id="swagger-ui"></div>
    <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
    <script>
      window.ui = SwaggerUIBundle({
        url: '/openapi.json',
        dom_id: '#swagger-ui',
        deepLinking: true,
        layout: 'BaseLayout',
        presets: [SwaggerUIBundle.presets.apis]
      });
    </script>
  </body>
</html>"""


def openapi_spec() -> dict:
    error_schema = {
        "type": "object",
        "properties": {
            "error": {"type": "string"},
        },
    }
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "LeakLane Backend API",
            "version": BACKEND_VERSION,
            "description": "Local-first APIs for repository leak scanning, reports, repository maps, and LM Studio analysis.",
        },
        "servers": [{"url": "http://127.0.0.1:8787", "description": "Local backend"}],
        "tags": [
            {"name": "System"},
            {"name": "Repositories"},
            {"name": "Scans"},
            {"name": "Reports"},
            {"name": "Repository map"},
            {"name": "AI"},
        ],
        "paths": {
            "/api/health": {
                "get": {
                    "tags": ["System"],
                    "summary": "Backend health and version",
                    "responses": {"200": {"description": "Backend status"}},
                }
            },
            "/api/prerequisites": {
                "get": {
                    "tags": ["System"],
                    "summary": "Local dependency status",
                    "responses": {"200": {"description": "Git, Gitleaks, GitHub CLI, and LM Studio status"}},
                }
            },
            "/api/github/status": {
                "get": {
                    "tags": ["System"],
                    "summary": "GitHub CLI authentication status",
                    "responses": {"200": {"description": "GitHub CLI status"}},
                }
            },
            "/api/search": {
                "get": {
                    "tags": ["Repositories"],
                    "summary": "Search public repositories",
                    "parameters": [
                        {"name": "q", "in": "query", "required": True, "schema": {"type": "string"}},
                        {
                            "name": "provider",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "string", "enum": ["github", "bitbucket"], "default": "github"},
                        },
                    ],
                    "responses": {
                        "200": {"description": "Repository search results"},
                        "502": {"description": "Provider search error", "content": {"application/json": {"schema": error_schema}}},
                    },
                }
            },
            "/api/scan": {
                "post": {
                    "tags": ["Scans"],
                    "summary": "Start a Gitleaks scan job",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["urls"],
                                    "properties": {
                                        "urls": {"type": "array", "items": {"type": "string"}},
                                        "mode": {"type": "string", "enum": ["git", "dir"], "default": "git"},
                                        "timeout": {"type": "integer", "default": 0},
                                        "maxTargetMegabytes": {"type": ["integer", "null"]},
                                        "ai": {"type": "object"},
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "202": {"description": "Scan queued"},
                        "400": {"description": "Invalid scan request", "content": {"application/json": {"schema": error_schema}}},
                    },
                }
            },
            "/api/jobs": {
                "get": {
                    "tags": ["Scans"],
                    "summary": "List scan jobs",
                    "responses": {"200": {"description": "Job previews"}},
                }
            },
            "/api/jobs/{jobId}": {
                "get": {
                    "tags": ["Scans"],
                    "summary": "Get scan job detail",
                    "parameters": [{"name": "jobId", "in": "path", "required": True, "schema": {"type": "string"}}],
                    "responses": {
                        "200": {"description": "Scan job detail"},
                        "404": {"description": "Job not found", "content": {"application/json": {"schema": error_schema}}},
                    },
                }
            },
            "/api/dashboard": {
                "get": {
                    "tags": ["Reports"],
                    "summary": "Risk dashboard summary",
                    "responses": {"200": {"description": "Aggregated risk data"}},
                }
            },
            "/api/diffs": {
                "get": {
                    "tags": ["Reports"],
                    "summary": "Scan deltas across repository executions",
                    "responses": {"200": {"description": "Repository diff summary"}},
                }
            },
            "/api/reports/{jobId}/{reportName}": {
                "get": {
                    "tags": ["Reports"],
                    "summary": "Download raw JSON report",
                    "parameters": [
                        {"name": "jobId", "in": "path", "required": True, "schema": {"type": "string"}},
                        {"name": "reportName", "in": "path", "required": True, "schema": {"type": "string"}},
                    ],
                    "responses": {
                        "200": {"description": "Report JSON file"},
                        "404": {"description": "Report not found", "content": {"application/json": {"schema": error_schema}}},
                    },
                }
            },
            "/api/repository-map": {
                "get": {
                    "tags": ["Repository map"],
                    "summary": "Read, update, or force-regenerate a persisted repository structure map",
                    "parameters": [
                        {"name": "url", "in": "query", "required": True, "schema": {"type": "string"}},
                        {
                            "name": "mode",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "string", "enum": ["stored", "delta", "force"], "default": "stored"},
                            "description": "stored reads the saved map or creates one; delta regenerates and compares with the saved map; force regenerates without delta.",
                        },
                        {"name": "refresh", "in": "query", "required": False, "schema": {"type": "boolean"}, "deprecated": True},
                        {"name": "force", "in": "query", "required": False, "schema": {"type": "boolean"}, "deprecated": True},
                    ],
                    "responses": {
                        "200": {"description": "Persisted repository branch, tag, PR, commit, finding overlay, and optional delta"},
                        "502": {"description": "Map generation error", "content": {"application/json": {"schema": error_schema}}},
                    },
                }
            },
            "/api/repository-map/ai-analysis": {
                "post": {
                    "tags": ["Repository map", "AI"],
                    "summary": "Generate local LM Studio analysis for a repository map",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["url"],
                                    "properties": {
                                        "url": {"type": "string"},
                                        "map": {"type": "object"},
                                        "focus": {"type": "object"},
                                        "ai": {"type": "object"},
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": {"description": "AI map analysis"},
                        "502": {"description": "LM Studio or map analysis error", "content": {"application/json": {"schema": error_schema}}},
                    },
                }
            },
            "/api/ai/status": {
                "get": {
                    "tags": ["AI"],
                    "summary": "LM Studio status and available models",
                    "responses": {"200": {"description": "LM Studio status"}},
                }
            },
            "/api/jobs/{jobId}/ai-analysis": {
                "post": {
                    "tags": ["AI"],
                    "summary": "Generate LM Studio report triage for a scan job",
                    "parameters": [{"name": "jobId", "in": "path", "required": True, "schema": {"type": "string"}}],
                    "responses": {
                        "202": {"description": "AI analysis queued"},
                        "404": {"description": "Job not found", "content": {"application/json": {"schema": error_schema}}},
                    },
                }
            },
            "/api/jobs/{jobId}/ai-analysis/content": {
                "post": {
                    "tags": ["AI"],
                    "summary": "Save edited Markdown AI analysis content",
                    "parameters": [{"name": "jobId", "in": "path", "required": True, "schema": {"type": "string"}}],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["content"],
                                    "properties": {"content": {"type": "string"}},
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": {"description": "AI analysis content saved"},
                        "404": {"description": "Job not found", "content": {"application/json": {"schema": error_schema}}},
                    },
                }
            },
            "/openapi.json": {
                "get": {
                    "tags": ["System"],
                    "summary": "OpenAPI document",
                    "responses": {"200": {"description": "OpenAPI specification"}},
                }
            },
        },
    }


def prerequisites_status() -> dict:
    checks = {
        "python": command_status([sys.executable, "--version"], required=True),
        "git": command_status(["git", "--version"], required=True),
        "gitleaks": command_status(["gitleaks", "--version"], required=True),
        "gh": command_status(["gh", "--version"], required=False),
    }
    github = github_cli_status()
    lm_studio = lm_studio_status()
    ready = all(item["installed"] for item in checks.values() if item["required"])
    return {
        "ready": ready,
        "checks": checks,
        "github": github,
        "lm_studio": lm_studio,
        "reports_dir": str(REPORT_ROOT),
        "backend_url": "http://127.0.0.1:8787",
        "backend_version": BACKEND_VERSION,
        "docs_url": "http://127.0.0.1:8787/docs",
        "openapi_url": "http://127.0.0.1:8787/openapi.json",
    }


def command_status(command: list[str], required: bool) -> dict:
    executable = command[0]
    path = shutil.which(executable) if executable != sys.executable else sys.executable
    if not path:
        return {
            "installed": False,
            "required": required,
            "path": None,
            "version": None,
            "error": "Command not found.",
        }
    try:
        result = run_local_command(command, timeout=8)
    except Exception as exc:
        return {
            "installed": True,
            "required": required,
            "path": path,
            "version": None,
            "error": str(exc),
        }
    output = (result.stdout or result.stderr).strip().splitlines()
    return {
        "installed": True,
        "required": required,
        "path": path,
        "version": output[0] if output else None,
        "error": None if result.returncode == 0 else (result.stderr.strip() or result.stdout.strip()),
    }


def first_status_line(output: str, fallback: str) -> str:
    for line in output.splitlines():
        clean = line.strip(" -")
        if clean and not clean.startswith("github.com"):
            return clean
    return fallback


def github_cli_search(query: str) -> list[dict]:
    command = [
        "gh",
        "search",
        "repos",
        query,
        "--limit",
        "10",
        "--json",
        "fullName,url,description,stargazersCount,language,updatedAt,visibility",
    ]
    try:
        result = run_local_command(command, timeout=25)
    except Exception as exc:
        raise RuntimeError(f"GitHub CLI search failed: {exc}") from exc
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "errore sconosciuto"
        raise RuntimeError(f"GitHub CLI search failed: {detail}")

    payload = json.loads(result.stdout or "[]")
    return [
        {
            "name": item.get("fullName"),
            "url": item.get("url"),
            "description": truncate(item.get("description") or "", 220),
            "stars": item.get("stargazersCount", 0),
            "language": item.get("language") or "Unknown",
            "updated_at": item.get("updatedAt"),
            "visibility": item.get("visibility"),
            "provider": "GitHub CLI",
        }
        for item in payload
        if item.get("url") and item.get("fullName")
    ]


def clone_repo_for_job(url: str, target: Path, mode: str) -> subprocess.CompletedProcess[str]:
    if is_github_url(url) and github_cli_status().get("ready"):
        spec = github_repo_spec(url)
        if spec:
            command = ["gh", "repo", "clone", spec, str(target), "--", "--quiet"]
            if mode == "dir":
                command.extend(["--depth", "1"])
            return run_local_command(command, timeout=None)
    return clone_repo(url, target, mode)


def is_github_url(url: str) -> bool:
    return urllib.parse.urlparse(url).netloc.lower() == "github.com"


def github_repo_spec(url: str) -> str | None:
    parsed = urllib.parse.urlparse(url)
    parts = parsed.path.strip("/").removesuffix(".git").split("/")
    if len(parts) < 2:
        return None
    return f"{parts[0]}/{parts[1]}"


def normalize_ai_config(config: dict) -> dict:
    model = str(config.get("model") or "").strip()
    system_prompt = str(config.get("system_prompt") or "").strip()
    additional_instructions = str(config.get("additional_instructions") or "").strip()
    auto_analyze = bool(config.get("auto_analyze", True))
    return {
        "model": model,
        "system_prompt": system_prompt,
        "additional_instructions": additional_instructions,
        "auto_analyze": auto_analyze,
    }


def list_jobs() -> dict:
    with jobs_lock:
        ordered = sorted(jobs.values(), key=lambda job: job.started_at, reverse=True)
        return {"jobs": [job.to_preview_dict() for job in ordered[:20]]}


def risk_dashboard() -> dict:
    with jobs_lock:
        snapshot = [job.to_dict() for job in jobs.values()]

    completed = [job for job in snapshot if job.get("results")]
    latest_repos: dict[str, dict] = {}
    timeline = []

    for job in sorted(completed, key=lambda item: item.get("started_at") or 0, reverse=True):
        job_findings = sum(int(result.get("findings") or 0) for result in job.get("results", []))
        timeline.append(
            {
                "id": job.get("id"),
                "started_at": job.get("started_at"),
                "status": job.get("status"),
                "repositories": len(job.get("urls", [])),
                "findings": job_findings,
            }
        )

        timestamp = job.get("finished_at") or job.get("started_at") or 0
        for result in job.get("results", []):
            url = result.get("url") or ""
            key = normalize_repo_key(url, result.get("name"))
            previous = latest_repos.get(key)
            if previous and previous.get("last_scan", 0) >= timestamp:
                continue
            latest_repos[key] = {
                "organization": organization_from_url(url),
                "provider": provider_from_url(url),
                "name": result.get("name") or key,
                "url": url,
                "status": result.get("status"),
                "findings": int(result.get("findings") or 0),
                "last_scan": timestamp,
                "items": result.get("items") or [],
                "job_id": job.get("id"),
            }

    organizations: dict[str, dict] = {}
    for repo in latest_repos.values():
        org_name = repo["organization"]
        org = organizations.setdefault(
            org_name,
            {
                "name": org_name,
                "provider": repo["provider"],
                "repositories": 0,
                "clean": 0,
                "findings": 0,
                "risk_score": 0,
                "risk_level": "clean",
                "last_scan": 0,
                "severity": {"critical": 0, "high": 0, "medium": 0, "low": 0},
                "rules": {},
                "repos": [],
            },
        )
        severity = severity_counts(repo["items"])
        score = risk_score(severity)
        level = risk_level(score, repo["findings"])
        repo_payload = {
            "name": repo["name"],
            "url": repo["url"],
            "status": repo["status"],
            "findings": repo["findings"],
            "risk_score": score,
            "risk_level": level,
            "last_scan": repo["last_scan"],
            "top_rules": top_rules(repo["items"], 3),
            "job_id": repo["job_id"],
        }
        org["repositories"] += 1
        org["clean"] += 1 if repo["status"] == "clean" else 0
        org["findings"] += repo["findings"]
        org["risk_score"] += score
        org["last_scan"] = max(org["last_scan"], repo["last_scan"])
        org["repos"].append(repo_payload)
        for severity_name, count in severity.items():
            org["severity"][severity_name] += count
        for rule, count in top_rules(repo["items"], 100):
            org["rules"][rule] = org["rules"].get(rule, 0) + count

    org_payloads = []
    for org in organizations.values():
        org["risk_level"] = risk_level(org["risk_score"], org["findings"])
        org["top_rules"] = sorted(org["rules"].items(), key=lambda item: item[1], reverse=True)[:5]
        del org["rules"]
        org["repos"] = sorted(
            org["repos"],
            key=lambda item: (item["risk_score"], item["findings"], item["last_scan"]),
            reverse=True,
        )[:6]
        org_payloads.append(org)

    org_payloads.sort(key=lambda item: (item["risk_score"], item["findings"], item["last_scan"]), reverse=True)
    hotspots = sorted(
        [
            {
                "organization": repo["organization"],
                "name": repo["name"],
                "url": repo["url"],
                "findings": repo["findings"],
                "risk_score": risk_score(severity_counts(repo["items"])),
                "risk_level": risk_level(risk_score(severity_counts(repo["items"])), repo["findings"]),
                "top_rules": top_rules(repo["items"], 3),
                "last_scan": repo["last_scan"],
                "job_id": repo["job_id"],
            }
            for repo in latest_repos.values()
            if repo["findings"] > 0
        ],
        key=lambda item: (item["risk_score"], item["findings"], item["last_scan"]),
        reverse=True,
    )[:8]

    total_findings = sum(org["findings"] for org in org_payloads)
    return {
        "updated_at": time.time(),
        "summary": {
            "organizations": len(org_payloads),
            "repositories": len(latest_repos),
            "findings": total_findings,
            "risky_repositories": sum(1 for repo in latest_repos.values() if repo["findings"] > 0),
            "jobs": len(completed),
        },
        "organizations": org_payloads,
        "hotspots": hotspots,
        "timeline": timeline[:8],
    }


def scan_diffs() -> dict:
    with jobs_lock:
        snapshot = [job.to_dict() for job in jobs.values()]

    histories: dict[str, list[dict]] = {}
    for job in snapshot:
        timestamp = job.get("finished_at") or job.get("started_at") or 0
        for result in job.get("results", []):
            url = result.get("url") or ""
            key = normalize_repo_key(url, result.get("name"))
            histories.setdefault(key, []).append(
                {
                    "job_id": job.get("id"),
                    "started_at": job.get("started_at"),
                    "finished_at": job.get("finished_at"),
                    "timestamp": timestamp,
                    "url": url,
                    "name": result.get("name") or key,
                    "status": result.get("status"),
                    "findings": int(result.get("findings") or 0),
                    "items": result.get("items") or [],
                }
            )

    comparisons = []
    for history in histories.values():
        ordered = sorted(history, key=lambda item: item.get("timestamp") or 0, reverse=True)
        if len(ordered) < 2:
            continue
        latest, previous = ordered[0], ordered[1]
        latest_map = finding_map(latest["items"])
        previous_map = finding_map(previous["items"])
        latest_keys = set(latest_map)
        previous_keys = set(previous_map)
        new_keys = latest_keys - previous_keys
        resolved_keys = previous_keys - latest_keys
        unchanged_keys = latest_keys & previous_keys
        comparisons.append(
            {
                "repository": latest["name"],
                "url": latest["url"],
                "organization": organization_from_url(latest["url"]),
                "latest_job_id": latest["job_id"],
                "previous_job_id": previous["job_id"],
                "latest_at": latest.get("timestamp"),
                "previous_at": previous.get("timestamp"),
                "latest_findings": latest["findings"],
                "previous_findings": previous["findings"],
                "new": len(new_keys),
                "resolved": len(resolved_keys),
                "unchanged": len(unchanged_keys),
                "delta": len(new_keys) - len(resolved_keys),
                "new_items": [finding_preview(latest_map[key]) for key in sorted(new_keys)[:5]],
                "resolved_items": [finding_preview(previous_map[key]) for key in sorted(resolved_keys)[:5]],
            }
        )

    comparisons.sort(
        key=lambda item: (item["new"], item["resolved"], item["latest_findings"], item["latest_at"] or 0),
        reverse=True,
    )
    return {
        "updated_at": time.time(),
        "summary": {
            "repositories": len(comparisons),
            "new": sum(item["new"] for item in comparisons),
            "resolved": sum(item["resolved"] for item in comparisons),
            "unchanged": sum(item["unchanged"] for item in comparisons),
        },
        "comparisons": comparisons,
    }


def repository_map(url: str, mode: str = "stored") -> dict:
    if mode not in {"stored", "delta", "force"}:
        raise RuntimeError("Invalid repository map mode.")
    if not urllib.parse.urlparse(url).scheme.startswith("http"):
        raise RuntimeError("Only HTTP(S) repository URLs are supported.")

    cache_key = normalize_repo_key(url)
    cached = repository_map_cache.get(cache_key)
    if mode == "stored" and cached and time.time() - cached[0] < REPOSITORY_MAP_CACHE_SECONDS:
        payload = json.loads(json.dumps(cached[1]))
        payload["cache"] = {
            "hit": True,
            "generated_at": cached[0],
            "ttl_seconds": REPOSITORY_MAP_CACHE_SECONDS,
        }
        payload["storage"] = {
            **payload.get("storage", {}),
            "hit": bool(payload.get("storage", {}).get("saved_at")),
            "mode": "memory",
        }
        return payload

    previous = load_repository_map(url)
    if mode == "stored" and previous:
        payload = json.loads(json.dumps(previous))
        payload["cache"] = {
            "hit": False,
            "generated_at": payload.get("updated_at") or payload.get("storage", {}).get("saved_at") or time.time(),
            "ttl_seconds": REPOSITORY_MAP_CACHE_SECONDS,
        }
        payload["storage"] = {
            **payload.get("storage", {}),
            "hit": True,
            "mode": "stored",
        }
        repository_map_cache[cache_key] = (time.time(), payload)
        return payload

    require_command("git")
    latest = latest_repo_result(url)
    with tempfile.TemporaryDirectory(prefix="leaklane-repo-map-") as tmp:
        repo_path = Path(tmp) / repo_name_from_url(url)
        clone = clone_repo_for_map(url, repo_path)
        if clone.returncode != 0:
            detail = clone.stderr.strip() or clone.stdout.strip() or "clone failed"
            raise RuntimeError(f"Unable to clone repository for map: {detail}")

        commits = git_commit_graph(repo_path, latest["items"])
        branches = git_branches(repo_path, commits)
        tags = git_tags(repo_path)
        prs = github_pull_requests(url)
        default_branch = git_default_branch(repo_path)

    stale_threshold = time.time() - (90 * 24 * 60 * 60)
    stale_branches = sum(1 for branch in branches if branch.get("updated_at") and branch["updated_at"] < stale_threshold)
    generated_at = time.time()
    map_path = repository_map_path(url)
    payload = {
        "repository": {
            "name": repo_name_from_url(url),
            "url": url,
            "provider": provider_from_url(url),
            "default_branch": default_branch,
            "latest_job_id": latest.get("job_id"),
            "latest_findings": latest.get("findings", 0),
        },
        "summary": {
            "branches": len(branches),
            "tags": len(tags),
            "pull_requests": len(prs),
            "commits": len(commits),
            "findings": latest.get("findings", 0),
            "stale_branches": stale_branches,
        },
        "branches": branches,
        "tags": tags,
        "pull_requests": prs,
        "commits": commits,
        "findings": repository_map_findings(latest["items"]),
        "limits": {
            "commits": REPOSITORY_MAP_COMMIT_LIMIT,
            "branches": REPOSITORY_MAP_BRANCH_LIMIT,
            "tags": REPOSITORY_MAP_TAG_LIMIT,
            "pull_requests": REPOSITORY_MAP_PR_LIMIT,
        },
        "truncated": {
            "commits": len(commits) >= REPOSITORY_MAP_COMMIT_LIMIT,
            "branches": len(branches) >= REPOSITORY_MAP_BRANCH_LIMIT,
            "tags": len(tags) >= REPOSITORY_MAP_TAG_LIMIT,
            "pull_requests": len(prs) >= REPOSITORY_MAP_PR_LIMIT,
        },
        "delta": repository_map_delta(previous, {
            "branches": branches,
            "tags": tags,
            "pull_requests": prs,
            "commits": commits,
            "findings": repository_map_findings(latest["items"]),
            "repository": {
                "default_branch": default_branch,
            },
            "updated_at": generated_at,
        }) if previous and mode == "delta" else None,
        "storage": {
            "hit": False,
            "mode": mode,
            "path": str(map_path),
            "saved_at": generated_at,
            "previous_saved_at": previous.get("storage", {}).get("saved_at") or previous.get("updated_at") if previous else None,
        },
        "cache": {
            "hit": False,
            "generated_at": generated_at,
            "ttl_seconds": REPOSITORY_MAP_CACHE_SECONDS,
        },
        "updated_at": generated_at,
    }
    save_repository_map(payload)
    repository_map_cache[cache_key] = (generated_at, payload)
    return payload


def repository_map_path(url: str) -> Path:
    key = normalize_repo_key(url)
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]
    slug = "".join(character if character.isalnum() else "-" for character in key.lower()).strip("-")
    slug = "-".join(part for part in slug.split("-") if part)[:88] or "repository"
    return REPOSITORY_MAP_ROOT / f"{slug}-{digest}.json"


def load_repository_map(url: str) -> dict | None:
    path = repository_map_path(url)
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        payload.setdefault("storage", {})
        payload["storage"] = {
            **payload["storage"],
            "hit": True,
            "path": str(path),
            "saved_at": payload["storage"].get("saved_at") or payload.get("updated_at") or path.stat().st_mtime,
        }
        return payload
    except Exception:
        return None


def save_repository_map(payload: dict) -> None:
    url = payload.get("repository", {}).get("url") or ""
    if not url:
        return
    path = repository_map_path(url)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".json.tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")
    tmp_path.replace(path)


def repository_map_delta(previous: dict | None, current: dict) -> dict | None:
    if not previous:
        return None
    previous_commits = {item.get("hash"): item for item in previous.get("commits", []) if item.get("hash")}
    current_commits = {item.get("hash"): item for item in current.get("commits", []) if item.get("hash")}
    previous_branches = {item.get("name"): item for item in previous.get("branches", []) if item.get("name")}
    current_branches = {item.get("name"): item for item in current.get("branches", []) if item.get("name")}
    previous_tags = {item.get("name"): item for item in previous.get("tags", []) if item.get("name")}
    current_tags = {item.get("name"): item for item in current.get("tags", []) if item.get("name")}
    previous_prs = {str(item.get("number")): item for item in previous.get("pull_requests", []) if item.get("number") is not None}
    current_prs = {str(item.get("number")): item for item in current.get("pull_requests", []) if item.get("number") is not None}
    previous_findings = finding_map(previous.get("findings", []))
    current_findings = finding_map(current.get("findings", []))

    changed_branches = [
        name for name in sorted(set(previous_branches) & set(current_branches))
        if previous_branches[name].get("commit") != current_branches[name].get("commit")
    ]
    changed_prs = [
        number for number in sorted(set(previous_prs) & set(current_prs))
        if (
            previous_prs[number].get("state"),
            previous_prs[number].get("head"),
            previous_prs[number].get("base"),
            previous_prs[number].get("is_draft"),
        )
        != (
            current_prs[number].get("state"),
            current_prs[number].get("head"),
            current_prs[number].get("base"),
            current_prs[number].get("is_draft"),
        )
    ]
    new_finding_keys = sorted(set(current_findings) - set(previous_findings))
    resolved_finding_keys = sorted(set(previous_findings) - set(current_findings))

    return {
        "generated_at": time.time(),
        "previous_map_at": previous.get("updated_at"),
        "current_map_at": current.get("updated_at"),
        "default_branch_changed": previous.get("repository", {}).get("default_branch") != current.get("repository", {}).get("default_branch"),
        "commits": {
            "new": len(set(current_commits) - set(previous_commits)),
            "removed": len(set(previous_commits) - set(current_commits)),
            "new_items": [commit_preview(current_commits[key]) for key in sorted(set(current_commits) - set(previous_commits))[:8]],
        },
        "branches": {
            "new": len(set(current_branches) - set(previous_branches)),
            "removed": len(set(previous_branches) - set(current_branches)),
            "changed": len(changed_branches),
            "changed_items": [branch_delta_preview(previous_branches[name], current_branches[name]) for name in changed_branches[:8]],
        },
        "tags": {
            "new": len(set(current_tags) - set(previous_tags)),
            "removed": len(set(previous_tags) - set(current_tags)),
            "new_items": [tag_preview(current_tags[key]) for key in sorted(set(current_tags) - set(previous_tags))[:8]],
        },
        "pull_requests": {
            "new": len(set(current_prs) - set(previous_prs)),
            "removed": len(set(previous_prs) - set(current_prs)),
            "changed": len(changed_prs),
            "changed_items": [pr_delta_preview(previous_prs[number], current_prs[number]) for number in changed_prs[:8]],
        },
        "findings": {
            "new": len(new_finding_keys),
            "resolved": len(resolved_finding_keys),
            "unchanged": len(set(current_findings) & set(previous_findings)),
            "delta": len(new_finding_keys) - len(resolved_finding_keys),
            "new_items": [finding_preview(current_findings[key]) for key in new_finding_keys[:8]],
            "resolved_items": [finding_preview(previous_findings[key]) for key in resolved_finding_keys[:8]],
        },
    }


def commit_preview(item: dict) -> dict:
    return {
        "short": item.get("short"),
        "timestamp": item.get("timestamp"),
        "author": item.get("author"),
        "subject": item.get("subject"),
        "findings": item.get("findings", 0),
    }


def branch_delta_preview(previous: dict, current: dict) -> dict:
    return {
        "name": current.get("name"),
        "previous": previous.get("short") or str(previous.get("commit") or "")[:8],
        "current": current.get("short") or str(current.get("commit") or "")[:8],
        "findings": current.get("findings", 0),
    }


def tag_preview(item: dict) -> dict:
    return {
        "name": item.get("name"),
        "short": item.get("short"),
        "created_at": item.get("created_at"),
    }


def pr_delta_preview(previous: dict, current: dict) -> dict:
    return {
        "number": current.get("number"),
        "title": current.get("title"),
        "previous_state": previous.get("state"),
        "current_state": current.get("state"),
        "head": current.get("head"),
        "base": current.get("base"),
    }


def clone_repo_for_map(url: str, target: Path) -> subprocess.CompletedProcess[str]:
    if is_github_url(url) and github_cli_status().get("ready"):
        spec = github_repo_spec(url)
        if spec:
            command = ["gh", "repo", "clone", spec, str(target), "--", "--quiet", "--filter=blob:none", "--no-checkout"]
            return run_local_command(command, timeout=180)
    command = ["git", "clone", "--quiet", "--filter=blob:none", "--no-checkout", url, str(target)]
    return run_local_command(command, timeout=180)


def git_local(command: list[str], cwd: Path, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *command],
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=timeout,
    )


def git_default_branch(repo_path: Path) -> str | None:
    result = git_local(["symbolic-ref", "--short", "refs/remotes/origin/HEAD"], repo_path)
    if result.returncode == 0:
        value = result.stdout.strip()
        if value.startswith("origin/"):
            return value.removeprefix("origin/")
        return value or None
    return None


def git_commit_graph(repo_path: Path, findings: list[dict]) -> list[dict]:
    result = git_local(
        [
            "log",
            "--all",
            "--topo-order",
            "--date=unix",
            "--pretty=format:%H%x09%P%x09%ct%x09%an%x09%s",
            "-n",
            str(REPOSITORY_MAP_COMMIT_LIMIT),
        ],
        repo_path,
        timeout=45,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "git log failed"
        raise RuntimeError(detail)

    finding_counts = findings_by_commit(findings)
    commits = []
    for line in result.stdout.splitlines():
        parts = line.split("\t", 4)
        if len(parts) < 5:
            continue
        commit_hash, parents, timestamp, author, subject = parts
        commits.append(
            {
                "hash": commit_hash,
                "short": commit_hash[:8],
                "parents": parents.split() if parents else [],
                "timestamp": int(timestamp or 0),
                "author": author,
                "subject": subject,
                "findings": finding_counts.get(commit_hash, 0),
            }
        )
    return commits


def git_branches(repo_path: Path, commits: list[dict]) -> list[dict]:
    result = git_local(
        [
            "for-each-ref",
            "--sort=-committerdate",
            "--format=%(refname:short)%09%(objectname)%09%(committerdate:unix)%09%(subject)",
            "refs/remotes/origin",
        ],
        repo_path,
    )
    if result.returncode != 0:
        return []

    default_branch = git_default_branch(repo_path)
    commit_findings = {commit["hash"]: commit.get("findings", 0) for commit in commits}
    branches = []
    for line in result.stdout.splitlines():
        parts = line.split("\t", 3)
        if len(parts) < 4:
            continue
        name, commit_hash, timestamp, subject = parts
        if name == "origin/HEAD":
            continue
        clean_name = name.removeprefix("origin/")
        branches.append(
            {
                "name": clean_name,
                "remote_name": name,
                "commit": commit_hash,
                "short": commit_hash[:8],
                "updated_at": int(timestamp or 0),
                "subject": subject,
                "is_default": clean_name == default_branch,
                "findings": commit_findings.get(commit_hash, 0),
            }
        )
    return branches[:REPOSITORY_MAP_BRANCH_LIMIT]


def git_tags(repo_path: Path) -> list[dict]:
    result = git_local(
        [
            "for-each-ref",
            "--sort=-creatordate",
            f"--count={REPOSITORY_MAP_TAG_LIMIT}",
            "--format=%(refname:short)%09%(objectname)%09%(creatordate:unix)%09%(subject)",
            "refs/tags",
        ],
        repo_path,
    )
    if result.returncode != 0:
        return []

    tags = []
    for line in result.stdout.splitlines():
        parts = line.split("\t", 3)
        if len(parts) < 4:
            continue
        name, commit_hash, timestamp, subject = parts
        tags.append(
            {
                "name": name,
                "commit": commit_hash,
                "short": commit_hash[:8],
                "created_at": int(timestamp or 0),
                "subject": subject,
            }
        )
    return tags


def github_pull_requests(url: str) -> list[dict]:
    spec = github_repo_spec(url) if is_github_url(url) else None
    if not spec or not github_cli_status().get("ready"):
        return []
    command = [
        "gh",
        "pr",
        "list",
        "--repo",
        spec,
        "--state",
        "all",
        "--limit",
        str(REPOSITORY_MAP_PR_LIMIT),
        "--json",
        "number,title,state,author,headRefName,baseRefName,updatedAt,createdAt,mergedAt,url,isDraft",
    ]
    try:
        result = run_local_command(command, timeout=30)
    except Exception:
        return []
    if result.returncode != 0:
        return []
    try:
        payload = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        return []
    return [
        {
            "number": item.get("number"),
            "title": item.get("title"),
            "state": item.get("state"),
            "author": (item.get("author") or {}).get("login"),
            "head": item.get("headRefName"),
            "base": item.get("baseRefName"),
            "url": item.get("url"),
            "created_at": item.get("createdAt"),
            "updated_at": item.get("updatedAt"),
            "merged_at": item.get("mergedAt"),
            "is_draft": item.get("isDraft"),
        }
        for item in payload
    ]


def latest_repo_result(url: str) -> dict:
    key = normalize_repo_key(url)
    with jobs_lock:
        snapshot = [job.to_dict() for job in jobs.values()]
    ordered = sorted(snapshot, key=lambda job: job.get("finished_at") or job.get("started_at") or 0, reverse=True)
    for job in ordered:
        for result in job.get("results", []):
            if normalize_repo_key(result.get("url") or "", result.get("name")) == key:
                return {
                    "job_id": job.get("id"),
                    "findings": int(result.get("findings") or 0),
                    "items": result.get("items") or [],
                }
    return {"job_id": None, "findings": 0, "items": []}


def findings_by_commit(items: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        commit = str(item.get("commit") or "").strip()
        if not commit:
            continue
        counts[commit] = counts.get(commit, 0) + 1
    return counts


def repository_map_findings(items: list[dict]) -> list[dict]:
    output = []
    for item in items:
        output.append(
            {
                "rule": item.get("rule"),
                "description": item.get("description"),
                "file": item.get("file"),
                "line": item.get("line"),
                "commit": item.get("commit"),
                "fingerprint": item.get("fingerprint"),
                "link": item.get("link"),
                "severity": severity_for_finding(item),
            }
        )
    return output


def finding_map(items: list[dict]) -> dict[str, dict]:
    return {finding_key(item): item for item in items}


def finding_key(item: dict) -> str:
    return str(
        item.get("fingerprint")
        or "|".join(
            str(part or "")
            for part in [item.get("rule"), item.get("file"), item.get("line"), item.get("commit")]
        )
    )


def finding_preview(item: dict) -> dict:
    return {
        "rule": item.get("rule"),
        "file": item.get("file"),
        "line": item.get("line"),
        "commit": item.get("commit"),
    }


def normalize_repo_key(url: str, fallback: str | None = None) -> str:
    if not url:
        return fallback or "unknown"
    parsed = urllib.parse.urlparse(url)
    return f"{parsed.netloc.lower()}/{parsed.path.strip('/').removesuffix('.git')}"


def organization_from_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if parts:
        return parts[0]
    return parsed.netloc or "unknown"


def provider_from_url(url: str) -> str:
    host = urllib.parse.urlparse(url).netloc.lower()
    if host == "github.com":
        return "GitHub"
    if host == "bitbucket.org":
        return "Bitbucket"
    return host or "Repository"


def severity_counts(items: list[dict]) -> dict[str, int]:
    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for item in items:
        counts[severity_for_finding(item)] += 1
    return counts


def severity_for_finding(item: dict) -> str:
    value = " ".join(
        str(part or "")
        for part in [item.get("rule"), item.get("description"), item.get("file")]
    ).lower()
    critical_markers = (
        "private-key",
        "password",
        "secret",
        "token",
        "aws",
        "github-pat",
        "slack",
        "stripe",
        "jwt",
    )
    high_markers = ("api-key", "auth-header", "credential", "bearer", "certificate", "curl-auth")
    if any(marker in value for marker in critical_markers):
        return "critical"
    if any(marker in value for marker in high_markers):
        return "high"
    if value:
        return "medium"
    return "low"


def risk_score(severity: dict[str, int]) -> int:
    return (
        severity.get("critical", 0) * 8
        + severity.get("high", 0) * 5
        + severity.get("medium", 0) * 2
        + severity.get("low", 0)
    )


def risk_level(score: int, findings: int) -> str:
    if findings <= 0:
        return "clean"
    if score >= 80:
        return "critical"
    if score >= 25:
        return "high"
    if score >= 8:
        return "medium"
    return "low"


def top_rules(items: list[dict], limit: int) -> list[list[object]]:
    counts: dict[str, int] = {}
    for item in items:
        rule = item.get("rule") or "unknown-rule"
        counts[rule] = counts.get(rule, 0) + 1
    return [[rule, count] for rule, count in sorted(counts.items(), key=lambda item: item[1], reverse=True)[:limit]]


def lm_studio_status() -> dict:
    try:
        models = lm_studio_models()
    except Exception as exc:
        return {
            "available": False,
            "base_url": LM_STUDIO_BASE_URL,
            "models": [],
            "selected_model": None,
            "error": str(exc),
        }
    selected = select_chat_model(models)
    return {
        "available": bool(selected),
        "base_url": LM_STUDIO_BASE_URL,
        "models": models,
        "selected_model": selected,
        "error": None if selected else "No chat model found.",
    }


def lm_studio_models() -> list[str]:
    request = urllib.request.Request(
        f"{LM_STUDIO_BASE_URL}/models",
        headers={"Accept": "application/json", "User-Agent": "local-gitleaks-repo-scanner"},
    )
    with urllib.request.urlopen(request, timeout=8) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return [
        item.get("id")
        for item in payload.get("data", [])
        if isinstance(item, dict) and item.get("id")
    ]


def select_chat_model(models: list[str]) -> str | None:
    blocked = ("embedding", "embed", "reranker", "medgemma", "functiongemma")
    preferred = (
        "google/gemma-3-12b",
        "qwen/qwen3-14b",
        "openai/gpt-oss-20b",
        "qwen/qwen3-30b-a3b",
        "bytedance/seed-oss-36b",
    )
    for candidate in preferred:
        if candidate in models:
            return candidate
    for model in models:
        lowered = model.lower()
        if not any(word in lowered for word in blocked):
            return model
    return None


def save_job(job: ScanJob) -> None:
    job_dir = REPORT_ROOT / job.id
    job_dir.mkdir(parents=True, exist_ok=True)
    payload = job.to_dict()
    tmp_path = job_dir / "job.json.tmp"
    final_path = job_dir / "job.json"
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")
    tmp_path.replace(final_path)


def save_ai_analysis(job: ScanJob) -> None:
    if not job.ai_analysis:
        return
    job_dir = REPORT_ROOT / job.id
    job_dir.mkdir(parents=True, exist_ok=True)
    path = job_dir / "ai_analysis.json"
    tmp_path = job_dir / "ai_analysis.json.tmp"
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(job.ai_analysis, handle, indent=2)
        handle.write("\n")
    tmp_path.replace(path)


def load_ai_analysis(job_dir: Path) -> dict | None:
    path = job_dir / "ai_analysis.json"
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return None


def load_persisted_jobs() -> None:
    loaded: dict[str, ScanJob] = {}
    if not REPORT_ROOT.exists():
        return

    for job_dir in sorted(REPORT_ROOT.iterdir(), reverse=True):
        if not job_dir.is_dir():
            continue

        job = load_job_file(job_dir) or load_legacy_summary(job_dir)
        if not job:
            continue
        if job.status in {"queued", "running"}:
            job.status = "failed"
            job.error = job.error or "Server stopped before the scan completed."
            job.finished_at = job.finished_at or time.time()
            job.current = None
            job.logs.append("Scan marked as failed after server restart.")
            save_job(job)
        if job.ai_status == "running":
            job.ai_status = "failed"
            job.ai_error = job.ai_error or "Server stopped before the AI analysis completed."
            job.logs.append("AI analysis marked as failed after server restart.")
            save_job(job)
        loaded[job.id] = job

    with jobs_lock:
        jobs.update(loaded)


def load_job_file(job_dir: Path) -> ScanJob | None:
    path = job_dir / "job.json"
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as handle:
            job = ScanJob.from_dict(json.load(handle))
        saved_analysis = load_ai_analysis(job_dir)
        if saved_analysis:
            job.ai_analysis = saved_analysis
            if job.ai_status in {"not_started", "failed"}:
                job.ai_status = "completed"
                job.ai_error = None
        hydrate_job(job)
        return job
    except Exception:
        return None


def load_legacy_summary(job_dir: Path) -> ScanJob | None:
    summary_path = job_dir / "summary.json"
    if not summary_path.exists():
        return None
    try:
        with summary_path.open("r", encoding="utf-8") as handle:
            summary = json.load(handle)
    except Exception:
        return None

    if not isinstance(summary, list):
        return None

    results = [result_payload_from_summary(item, job_dir.name) for item in summary if isinstance(item, dict)]
    urls = [item["url"] for item in summary if isinstance(item, dict) and item.get("url")]
    stat = summary_path.stat()
    job = ScanJob(
        id=job_dir.name,
        urls=urls,
        mode="dir",
        status="completed",
        started_at=stat.st_mtime,
        finished_at=stat.st_mtime,
        logs=["Loaded from saved summary."],
        results=results,
        reports_dir=str(job_dir),
        summary_path=str(summary_path),
    )
    saved_analysis = load_ai_analysis(job_dir)
    if saved_analysis:
        job.ai_analysis = saved_analysis
        job.ai_status = "completed"
    save_job(job)
    return job


def result_payload_from_summary(item: dict, job_id: str) -> dict:
    report_path = item.get("report_path")
    findings = load_findings(Path(report_path)) if report_path else []
    result = ScanResult(
        url=item.get("url", ""),
        name=item.get("name", "unknown"),
        status=item.get("status", "completed"),
        findings=item.get("findings", len(findings)),
        report_path=Path(report_path) if report_path else None,
        error=item.get("error"),
    )
    payload_holder = ScanJob(id=job_id, urls=[], mode="git")
    append_result(payload_holder, result, findings)
    return payload_holder.results[0]


def hydrate_job(job: ScanJob) -> None:
    hydrated_results = []
    changed = False
    for result in job.results:
        report_path = result.get("report_path")
        if report_path and Path(report_path).exists():
            findings = load_findings(Path(report_path))
            scan_result = ScanResult(
                url=result.get("url", ""),
                name=result.get("name", "unknown"),
                status=result.get("status", "completed"),
                findings=result.get("findings", len(findings)),
                report_path=Path(report_path),
                error=result.get("error"),
            )
            payload_holder = ScanJob(id=job.id, urls=[], mode=job.mode)
            append_result(payload_holder, scan_result, findings)
            hydrated = payload_holder.results[0]
            hydrated_results.append(hydrated)
            if not result.get("report_url") or result.get("items") != hydrated.get("items"):
                changed = True
        else:
            hydrated_results.append(result)

    if changed:
        job.results = hydrated_results
        save_job(job)


def run_scan_job(job: ScanJob, args: SimpleNamespace) -> None:
    try:
        require_command("git")
        require_command("gitleaks")
        report_dir = REPORT_ROOT / job.id
        report_dir.mkdir(parents=True, exist_ok=True)
        job.reports_dir = str(report_dir)
        save_job(job)

        with tempfile.TemporaryDirectory(prefix="gitleaks-web-repos-") as tmp:
            work_dir = Path(tmp)
            results: list[ScanResult] = []

            with jobs_lock:
                job.status = "running"
            save_job(job)

            for url in job.urls:
                name = repo_name_from_url(url)
                repo_path = work_dir / name
                report_path = report_dir / f"{name}.json"

                with jobs_lock:
                    job.current = name
                job.log(f"Clone {url}")
                save_job(job)

                clone = clone_repo_for_job(url, repo_path, args.mode)
                if clone.returncode != 0:
                    error = clone.stderr.strip() or clone.stdout.strip() or "clone failed"
                    result = ScanResult(url, name, "clone_failed", 0, None, error)
                    results.append(result)
                    append_result(job, result, [])
                    job.log(f"{name}: clone failed")
                    save_job(job)
                    continue

                job.log(f"Scan {name} with gitleaks {args.mode}")
                save_job(job)
                scan = scan_repo(repo_path, report_path, args)
                findings = load_findings(report_path)

                if scan.returncode == 0:
                    result = ScanResult(url, name, "clean", len(findings), report_path)
                elif scan.returncode == 2:
                    result = ScanResult(url, name, "findings", len(findings), report_path)
                else:
                    error = scan.stderr.strip() or scan.stdout.strip() or "scan failed"
                    result = ScanResult(url, name, "scan_failed", 0, report_path, error)

                results.append(result)
                append_result(job, result, findings)
                job.log(f"{name}: {result.status} ({result.findings} finding(s))")
                save_job(job)
                shutil.rmtree(repo_path, ignore_errors=True)

        summary_path = write_summary(report_dir, results)
        with jobs_lock:
            job.summary_path = str(summary_path)
            job.current = None
            job.status = "completed"
            job.finished_at = time.time()
        job.log("Scan completed")
        save_job(job)
        if any(result.findings > 0 for result in results) and job.ai_config.get("auto_analyze", True):
            threading.Thread(target=generate_ai_analysis, args=(job,), daemon=True).start()
    except Exception as exc:
        with jobs_lock:
            job.status = "failed"
            job.error = str(exc)
            job.finished_at = time.time()
        job.log(f"Scan failed: {exc}")
        save_job(job)


def generate_ai_analysis(job: ScanJob, ai_config: dict | None = None) -> None:
    with jobs_lock:
        if ai_config:
            job.ai_config = {**job.ai_config, **ai_config}
        job.ai_status = "running"
        job.ai_error = None
    job.log("AI analysis started")
    save_job(job)

    try:
        status = lm_studio_status()
        requested_model = (job.ai_config or {}).get("model")
        available_models = status.get("models") or []
        model = requested_model if requested_model in available_models else status.get("selected_model")
        if not status.get("available") or not model:
            raise RuntimeError(status.get("error") or "LM Studio is not available.")

        prompt_payload = build_ai_prompt_payload(job)
        content, used_model = call_lm_studio_with_fallback(
            model,
            available_models,
            prompt_payload,
            job.ai_config,
            job,
        )
        analysis = {
            "generated_at": time.time(),
            "base_url": LM_STUDIO_BASE_URL,
            "model": used_model,
            "content": content,
            "input": {
                "repositories": len(job.urls),
                "results": len(job.results),
                "findings_total": sum(int(result.get("findings") or 0) for result in job.results),
                "findings_sent": prompt_payload["findings_sent"],
                "truncated": prompt_payload["truncated"],
                "requested_model": requested_model or "automatic",
            },
        }
        with jobs_lock:
            job.ai_analysis = analysis
            job.ai_status = "completed"
            job.ai_error = None
        save_ai_analysis(job)
        job.log("AI analysis completed")
        save_job(job)
    except Exception as exc:
        with jobs_lock:
            job.ai_status = "failed"
            job.ai_error = str(exc)
        job.log(f"AI analysis failed: {exc}")
        save_job(job)


def build_ai_prompt_payload(job: ScanJob) -> dict:
    findings = []
    for result in job.results:
        for item in result.get("items", []):
            findings.append(
                {
                    "repository": result.get("name"),
                    "rule": item.get("rule"),
                    "description": truncate(item.get("description") or "", 120),
                    "file": item.get("file"),
                    "line": item.get("line"),
                    "commit": item.get("commit"),
                    "date": item.get("date"),
                }
            )

    findings = findings[:AI_ANALYSIS_FINDING_LIMIT]
    return {
        "job_id": job.id,
        "mode": job.mode,
        "repositories": [
            {
                "url": result.get("url"),
                "name": result.get("name"),
                "status": result.get("status"),
                "findings": result.get("findings"),
            }
            for result in job.results
        ],
        "findings": findings,
        "findings_sent": len(findings),
        "truncated": sum(int(result.get("findings") or 0) for result in job.results) > len(findings),
    }


def generate_repository_map_ai_analysis(
    url: str,
    map_payload: dict | None,
    ai_config: dict | None = None,
    focus_payload: dict | None = None,
) -> dict:
    status = lm_studio_status()
    requested_model = (ai_config or {}).get("model")
    available_models = status.get("models") or []
    model = requested_model if requested_model in available_models else status.get("selected_model")
    if not status.get("available") or not model:
        raise RuntimeError(status.get("error") or "LM Studio is not available.")

    source_map = map_payload if map_payload else repository_map(url)
    prompt_payload = build_repository_map_ai_prompt_payload(source_map, focus_payload)
    content, used_model = call_lm_studio_with_fallback(
        model,
        available_models,
        prompt_payload,
        ai_config,
        None,
        prompt_kind="repository_map",
    )
    return {
        "generated_at": time.time(),
        "base_url": LM_STUDIO_BASE_URL,
        "model": used_model,
        "content": content,
        "input": {
            "repository": prompt_payload["repository"]["name"],
            "branches": prompt_payload["summary"]["branches"],
            "tags": prompt_payload["summary"]["tags"],
            "pull_requests": prompt_payload["summary"]["pull_requests"],
            "commits_sent": len(prompt_payload["commits"]),
            "findings_sent": len(prompt_payload["findings"]),
            "requested_model": requested_model or "automatic",
            "focus": (prompt_payload.get("focus") or {}).get("title"),
        },
    }


def build_repository_map_ai_prompt_payload(map_payload: dict, focus_payload: dict | None = None) -> dict:
    branches = sorted(
        map_payload.get("branches", []),
        key=lambda item: (not item.get("is_default"), -(int(item.get("updated_at") or 0))),
    )
    commits = map_payload.get("commits", [])
    findings = map_payload.get("findings", [])
    pull_requests = map_payload.get("pull_requests", [])
    tags = map_payload.get("tags", [])
    stale_cutoff = time.time() - (90 * 24 * 60 * 60)

    return {
        "repository": map_payload.get("repository", {}),
        "summary": map_payload.get("summary", {}),
        "default_branch": (map_payload.get("repository") or {}).get("default_branch"),
        "focus": focus_payload or None,
        "branches": [
            {
                "name": branch.get("name"),
                "remote_name": branch.get("remote_name"),
                "is_default": branch.get("is_default"),
                "updated_at": branch.get("updated_at"),
                "stale": bool(branch.get("updated_at") and int(branch.get("updated_at")) < stale_cutoff),
                "head": branch.get("short"),
                "subject": truncate(branch.get("subject") or "", 140),
                "findings": branch.get("findings", 0),
            }
            for branch in branches[:16]
        ],
        "pull_requests": [
            {
                "number": pr.get("number"),
                "title": truncate(pr.get("title") or "", 160),
                "state": pr.get("state"),
                "is_draft": pr.get("is_draft"),
                "author": pr.get("author"),
                "head": pr.get("head"),
                "base": pr.get("base"),
                "updated_at": pr.get("updated_at"),
            }
            for pr in pull_requests[:12]
        ],
        "tags": [
            {
                "name": tag.get("name"),
                "created_at": tag.get("created_at"),
                "commit": tag.get("short"),
                "subject": truncate(tag.get("subject") or "", 120),
            }
            for tag in tags[:10]
        ],
        "commits": [
            {
                "short": commit.get("short"),
                "parents": len(commit.get("parents") or []),
                "timestamp": commit.get("timestamp"),
                "author": commit.get("author"),
                "subject": truncate(commit.get("subject") or "", 150),
                "findings": commit.get("findings", 0),
            }
            for commit in commits[:30]
        ],
        "findings": [
            {
                "rule": finding.get("rule"),
                "file": finding.get("file"),
                "line": finding.get("line"),
                "commit": str(finding.get("commit") or "")[:12],
                "severity": finding.get("severity"),
                "description": truncate(finding.get("description") or "", 120),
            }
            for finding in findings[:AI_ANALYSIS_FINDING_LIMIT]
        ],
        "truncated": {
            "branches": len(branches) > 16,
            "pull_requests": len(pull_requests) > 12,
            "tags": len(tags) > 10,
            "commits": len(commits) > 30,
            "findings": len(findings) > AI_ANALYSIS_FINDING_LIMIT,
        },
    }


def call_lm_studio_with_fallback(
    model: str,
    available_models: list[str],
    prompt_payload: dict,
    ai_config: dict | None,
    job: ScanJob | None,
    prompt_kind: str = "scan",
) -> tuple[str, str]:
    attempted: set[str] = set()
    candidates = [model, *fallback_chat_models(available_models, exclude={model})]
    last_error: Exception | None = None

    for candidate in candidates:
        if not candidate or candidate in attempted:
            continue
        attempted.add(candidate)
        try:
            content = call_lm_studio(candidate, prompt_payload, ai_config, prompt_kind=prompt_kind)
            if candidate != model:
                if job:
                    job.log(f"AI model fallback used: {candidate}")
                    save_job(job)
            return content, candidate
        except EmptyModelResponse as exc:
            last_error = exc
            if job:
                job.log(f"{candidate}: empty AI response, trying fallback model")
                save_job(job)
            continue

    if last_error:
        raise RuntimeError(f"LM Studio returned an empty response after fallback: {last_error}") from last_error
    raise RuntimeError("No usable LM Studio chat model found.")


def fallback_chat_models(models: list[str], exclude: set[str] | None = None) -> list[str]:
    exclude = exclude or set()
    preferred = (
        "google/gemma-3-12b",
        "qwen/qwen3-14b",
        "openai/gpt-oss-20b",
        "qwen/qwen3-30b-a3b",
        "bytedance/seed-oss-36b",
        "codeqwen1.5-7b-chat",
    )
    blocked = ("embedding", "embed", "reranker", "medgemma", "functiongemma")
    ordered = [model for model in preferred if model in models and model not in exclude]
    ordered.extend(
        model
        for model in models
        if model not in exclude
        and model not in ordered
        and not any(word in model.lower() for word in blocked)
    )
    return ordered


def call_lm_studio(
    model: str,
    prompt_payload: dict,
    ai_config: dict | None = None,
    prompt_kind: str = "scan",
) -> str:
    if prompt_kind == "repository_map":
        default_system_prompt = (
            "Sei un senior application security engineer con esperienza in repository governance. "
            "Analizza una mappa Git gia' estratta: branch, tag, commit, PR e finding Gitleaks redatti. "
            "Non inventare secret, non affermare che credenziali siano valide e non chiedere accesso al codice. "
            "Scrivi in italiano, con tono operativo e conciso. Devi sempre produrre una risposta finale in Markdown."
        )
        default_user_prompt = (
            "Genera una analisi intelligente della struttura del repository.\n"
            "Restituisci Markdown con queste sezioni: Sintesi operativa, Segnali sulla struttura Git, "
            "Rischio security overlay, Branch e PR da rivedere, Azioni consigliate.\n"
            "Evidenzia stale branch, PR aperte/draft, assenza o presenza di tag, commit con finding e possibili colli di bottiglia. "
            "Se il JSON contiene un campo focus, apri con una lettura mirata di quell'elemento prima della visione generale. "
            "Se i dati sono insufficienti, dillo chiaramente e suggerisci cosa raccogliere.\n"
            "Cita nomi di branch, PR, tag, rule, file e commit breve quando disponibili."
        )
    else:
        default_system_prompt = (
            "Sei un senior application security engineer. Analizza finding Gitleaks gia' redatti. "
            "Non inventare secret e non affermare che una credenziale sia valida se non puoi verificarlo. "
            "Scrivi in italiano, con tono operativo e conciso. Devi sempre produrre una risposta finale in Markdown."
        )
        default_user_prompt = (
            "Genera una analisi breve di triage per questo report Gitleaks.\n"
            "Restituisci Markdown con queste sezioni: Sintesi, Priorita', Possibili falsi positivi, "
            "Azioni consigliate, Note operative.\n"
            "Per ogni priorita' cita rule, file e riga quando disponibili."
        )
    system_prompt = (ai_config or {}).get("system_prompt") or default_system_prompt
    additional = (ai_config or {}).get("additional_instructions") or ""
    user_prompt = (
        f"{default_user_prompt}\n\n"
        f"Specifiche addizionali utente:\n{additional or 'Nessuna'}\n\n"
        f"Dati JSON:\n{json.dumps(prompt_payload, ensure_ascii=True, separators=(',', ':'))}"
    )
    request_body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
        "max_tokens": AI_ANALYSIS_MAX_TOKENS,
        "stream": False,
    }
    request = urllib.request.Request(
        f"{LM_STUDIO_BASE_URL}/chat/completions",
        data=json.dumps(request_body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "local-gitleaks-repo-scanner",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=AI_ANALYSIS_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"LM Studio HTTP {exc.code}: {detail}") from exc
    choices = payload.get("choices") or []
    if not choices:
        raise RuntimeError("LM Studio returned no choices.")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if not content:
        reasoning = message.get("reasoning_content")
        finish_reason = choices[0].get("finish_reason")
        if reasoning:
            raise EmptyModelResponse(
                f"{model} returned internal reasoning without final content"
                f" (finish_reason={finish_reason or 'unknown'})."
            )
        raise EmptyModelResponse(f"{model} returned no final content.")
    return content.strip()


def append_result(job: ScanJob, result: ScanResult, findings: list[dict]) -> None:
    clean_findings = [
        {
            "rule": item.get("RuleID") or item.get("Description") or "unknown-rule",
            "description": item.get("Description"),
            "file": item.get("File") or "unknown-file",
            "line": item.get("StartLine") or item.get("Line") or "?",
            "end_line": item.get("EndLine"),
            "start_column": item.get("StartColumn"),
            "end_column": item.get("EndColumn"),
            "commit": item.get("Commit"),
            "author": item.get("Author"),
            "email": item.get("Email"),
            "date": item.get("Date"),
            "fingerprint": item.get("Fingerprint"),
            "link": github_blob_link(result.url, item),
        }
        for item in findings
    ]
    report_url = None
    if result.report_path:
        report_url = f"/api/reports/{job.id}/{Path(result.report_path).name}"
    payload = {
        "url": result.url,
        "name": result.name,
        "status": result.status,
        "findings": result.findings,
        "report_path": str(result.report_path) if result.report_path else None,
        "report_url": report_url,
        "error": result.error,
        "items": clean_findings,
    }
    with jobs_lock:
        job.results.append(payload)


def github_blob_link(repo_url: str, finding: dict) -> str | None:
    parsed = urllib.parse.urlparse(repo_url)
    parts = parsed.path.strip("/").removesuffix(".git").split("/")
    if len(parts) < 2:
        return None

    commit = finding.get("Commit")
    file_path = finding.get("File")
    line = finding.get("StartLine") or finding.get("Line")
    if not commit or not file_path:
        return None

    owner, repo = parts[0], parts[1]
    encoded_file = "/".join(urllib.parse.quote(part) for part in str(file_path).split("/"))
    if parsed.netloc == "github.com":
        suffix = f"#L{line}" if line else ""
        return f"https://github.com/{owner}/{repo}/blob/{commit}/{encoded_file}{suffix}"
    if parsed.netloc == "bitbucket.org":
        suffix = f"#lines-{line}" if line else ""
        return f"https://bitbucket.org/{owner}/{repo}/src/{commit}/{encoded_file}{suffix}"
    return None


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8787
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    load_persisted_jobs()
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"LeakLane backend running at http://127.0.0.1:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

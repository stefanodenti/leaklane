#!/usr/bin/env python3
"""Scan public Git repositories with Gitleaks."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


@dataclass
class ScanResult:
    url: str
    name: str
    status: str
    findings: int
    report_path: Path | None = None
    error: str | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Clone public Git repositories and scan them with Gitleaks."
    )
    parser.add_argument("urls", nargs="*", help="Repository URLs to scan.")
    parser.add_argument(
        "-f",
        "--file",
        type=Path,
        help="Text file containing one repository URL per line.",
    )
    parser.add_argument(
        "--mode",
        choices=("git", "dir"),
        default="git",
        help=(
            "Scan full git history with 'git' or only the current files with 'dir'. "
            "Default: git."
        ),
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        help="Directory used for cloned repositories. Defaults to a temporary folder.",
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=Path("gitleaks-reports"),
        help="Directory where JSON reports are saved. Default: gitleaks-reports.",
    )
    parser.add_argument(
        "--keep-clones",
        action="store_true",
        help="Keep cloned repositories after the scan.",
    )
    parser.add_argument(
        "--redact",
        type=int,
        default=100,
        choices=range(0, 101),
        metavar="0-100",
        help="Secret redaction percentage passed to Gitleaks. Default: 100.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=0,
        help="Gitleaks timeout in seconds. Default: 0, no timeout.",
    )
    parser.add_argument(
        "--max-target-megabytes",
        type=int,
        help="Skip files larger than this size in MB.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="Optional custom .gitleaks.toml config file.",
    )
    return parser.parse_args()


def require_command(command: str) -> None:
    if shutil.which(command) is None:
        raise SystemExit(f"Missing required command: {command}")


def load_urls(args: argparse.Namespace) -> list[str]:
    urls = list(args.urls)
    if args.file:
        with args.file.open("r", encoding="utf-8") as handle:
            urls.extend(
                line.strip()
                for line in handle
                if line.strip() and not line.lstrip().startswith("#")
            )

    unique_urls: list[str] = []
    seen: set[str] = set()
    for url in urls:
        normalized = normalize_repo_url(url)
        if normalized not in seen:
            unique_urls.append(normalized)
            seen.add(normalized)

    if not unique_urls:
        raise SystemExit("Provide at least one GitHub repository URL.")
    return unique_urls


def normalize_repo_url(url: str) -> str:
    if url.startswith("git@github.com:"):
        repo = url.removeprefix("git@github.com:").removesuffix(".git")
        return f"https://github.com/{repo}.git"
    if url.startswith("git@bitbucket.org:"):
        repo = url.removeprefix("git@bitbucket.org:").removesuffix(".git")
        return f"https://bitbucket.org/{repo}.git"

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise SystemExit(f"Only http and https repository URLs are supported: {url}")

    host = parsed.netloc.lower()
    if host not in {"github.com", "bitbucket.org"}:
        raise SystemExit(f"Only github.com and bitbucket.org repository URLs are supported: {url}")

    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(parts) < 2:
        raise SystemExit(f"Invalid repository URL: {url}")

    owner, repo = parts[0], parts[1].removesuffix(".git")
    return f"https://{host}/{owner}/{repo}.git"


def normalize_github_url(url: str) -> str:
    return normalize_repo_url(url)


def repo_name_from_url(url: str) -> str:
    parsed = urlparse(url)
    owner, repo = parsed.path.strip("/").removesuffix(".git").split("/")[:2]
    safe = "".join(char if char.isalnum() or char in "._-" else "_" for char in f"{owner}_{repo}")
    return safe


def run(command: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def clone_repo(url: str, target: Path, mode: str) -> subprocess.CompletedProcess[str]:
    command = ["git", "clone", "--quiet"]
    if mode == "dir":
        command.extend(["--depth", "1"])
    command.extend([url, str(target)])
    return run(command)


def scan_repo(
    repo_path: Path,
    report_path: Path,
    args: argparse.Namespace,
) -> subprocess.CompletedProcess[str]:
    command = [
        "gitleaks",
        args.mode,
        "--no-banner",
        "--no-color",
        f"--redact={args.redact}",
        "--exit-code",
        "2",
        "--report-format",
        "json",
        "--report-path",
        str(report_path),
    ]

    if args.timeout:
        command.extend(["--timeout", str(args.timeout)])
    if args.max_target_megabytes:
        command.extend(["--max-target-megabytes", str(args.max_target_megabytes)])
    if args.config:
        command.extend(["--config", str(args.config)])

    command.append(str(repo_path))
    return run(command)


def load_findings(report_path: Path) -> list[dict]:
    if not report_path.exists() or report_path.stat().st_size == 0:
        return []
    with report_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return data if isinstance(data, list) else []


def print_findings(repo_name: str, findings: list[dict]) -> None:
    if not findings:
        print(f"\n{repo_name}: no findings")
        return

    print(f"\n{repo_name}: {len(findings)} finding(s)")
    for index, finding in enumerate(findings, start=1):
        rule = finding.get("RuleID") or finding.get("Description") or "unknown-rule"
        file_path = finding.get("File") or "unknown-file"
        line = finding.get("StartLine") or finding.get("Line") or "?"
        commit = finding.get("Commit")
        fingerprint = finding.get("Fingerprint")

        print(f"  {index}. {rule} in {file_path}:{line}")
        if commit:
            print(f"     commit: {commit}")
        if fingerprint:
            print(f"     fingerprint: {fingerprint}")


def write_summary(report_dir: Path, results: list[ScanResult]) -> Path:
    summary_path = report_dir / "summary.json"
    payload = [
        {
            "url": result.url,
            "name": result.name,
            "status": result.status,
            "findings": result.findings,
            "report_path": str(result.report_path) if result.report_path else None,
            "error": result.error,
        }
        for result in results
    ]
    with summary_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")
    return summary_path


def main() -> int:
    args = parse_args()
    require_command("git")
    require_command("gitleaks")

    urls = load_urls(args)
    args.report_dir.mkdir(parents=True, exist_ok=True)

    temp_context = None
    if args.work_dir:
        work_dir = args.work_dir
        work_dir.mkdir(parents=True, exist_ok=True)
    elif args.keep_clones:
        work_dir = Path("gitleaks-clones")
        work_dir.mkdir(parents=True, exist_ok=True)
    else:
        temp_context = tempfile.TemporaryDirectory(prefix="gitleaks-public-repos-")
        work_dir = Path(temp_context.name)

    results: list[ScanResult] = []

    try:
        for url in urls:
            name = repo_name_from_url(url)
            repo_path = work_dir / name
            report_path = args.report_dir / f"{name}.json"

            if repo_path.exists():
                shutil.rmtree(repo_path)

            print(f"\nCloning {url}")
            clone = clone_repo(url, repo_path, args.mode)
            if clone.returncode != 0:
                error = clone.stderr.strip() or clone.stdout.strip() or "clone failed"
                print(f"{name}: clone failed")
                results.append(ScanResult(url, name, "clone_failed", 0, None, error))
                continue

            print(f"Scanning {name} with gitleaks {args.mode}")
            scan = scan_repo(repo_path, report_path, args)
            findings = load_findings(report_path)

            if scan.returncode == 0:
                status = "clean"
            elif scan.returncode == 2:
                status = "findings"
            else:
                error = scan.stderr.strip() or scan.stdout.strip() or "scan failed"
                print(f"{name}: scan failed")
                results.append(ScanResult(url, name, "scan_failed", 0, report_path, error))
                continue

            print_findings(name, findings)
            results.append(ScanResult(url, name, status, len(findings), report_path))

            if not args.keep_clones and args.work_dir:
                shutil.rmtree(repo_path)

    finally:
        if temp_context is not None:
            temp_context.cleanup()

    summary_path = write_summary(args.report_dir, results)

    print("\nSummary")
    for result in results:
        print(f"- {result.name}: {result.status} ({result.findings} finding(s))")
    print(f"\nReports saved in: {args.report_dir}")
    print(f"Summary saved in: {summary_path}")

    has_scan_errors = any(result.status.endswith("_failed") for result in results)
    has_findings = any(result.findings > 0 for result in results)
    if has_scan_errors:
        return 3
    return 2 if has_findings else 0


if __name__ == "__main__":
    sys.exit(main())

# Changelog

## Unreleased

### Added

- Local LM Studio analysis for Repository Intelligence maps, including full-map summaries and selected-node context readings.

## v0.2.0-alpha.1 - 2026-07-07

### Added

- Repository Intelligence view with branch, tag, commit, pull request, and Gitleaks finding overlay.
- Read-only repository map API using temporary filtered clones that are removed after analysis.
- Repository map cache, graph zoom controls, branch/tag/PR/finding filters, drag-to-pan, and finding detail drill-down.
- Expanded Repository Intelligence graph workspace with larger canvas, stable branch lanes, lane guides, and bottom selection inspector.
- GitKraken-inspired branch coloring with colored lanes, curved commit paths, branch pills, and an interactive branch legend.
- Bottom drawer inspector for selected map elements with richer commit, branch, tag, PR, and finding details.
- Clickable commit nodes in the repository graph with larger hit targets and drawer selection feedback.
- Collapsible primary sidebar to give repository maps and report views more workspace.

## v0.1.0-alpha.1 - 2026-07-06

First public alpha of LeakLane.

### Added

- Local-first repository secret scanning with Gitleaks.
- GitHub repository search, manual repository staging, and Bitbucket URL support.
- GitHub CLI integration for private GitHub repositories without storing tokens.
- Persistent scan executions, findings, JSON reports, AI analyses, and scan deltas.
- Local LM Studio integration for Markdown security triage after scans.
- SvelteKit multi-page interface with dashboard, repositories, scan setup, reports, and settings.
- Tauri desktop packaging with automatic local Python backend startup.
- LeakLane brand identity, logo assets, app favicon, and GitHub-ready documentation.

### Notes

- This is an alpha prerelease intended for local validation and early feedback.
- macOS builds are currently unsigned and not notarized.
- Git, Gitleaks, and Python must be available on the local machine.
- LM Studio and GitHub CLI are optional integrations.

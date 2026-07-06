# LeakLane

**Local secret triage for repository fleets.**

LeakLane is a local-first desktop and web console for scanning GitHub and Bitbucket repositories with Gitleaks, preserving reports, and generating local AI triage through LM Studio.

It is built for teams that want repeatable secret scanning without sending repository data or findings to a hosted service.

## What It Does

- Search GitHub repositories and build a scan pitlane.
- Add GitHub or Bitbucket repository URLs manually.
- Use GitHub CLI authentication for private GitHub repositories.
- Run Gitleaks in `git` or `dir` mode.
- Persist every execution, finding, JSON report, and AI analysis.
- Compare scan deltas across repeated executions.
- Generate local Markdown triage with LM Studio.
- Run as a SvelteKit web UI or a Tauri desktop app.

## Requirements

- Git
- Gitleaks
- Python 3.10+
- Node.js and npm
- Rust/Cargo for desktop builds
- GitHub CLI, optional but recommended for private GitHub repositories
- LM Studio, optional for local AI analysis

On macOS:

```bash
brew install gitleaks rust
```

GitHub CLI authentication:

```bash
gh auth login -h github.com
```

LeakLane does not store GitHub tokens. It uses the local session managed by `gh`.

## Web Development

Start the backend from the project root:

```bash
python3 web_app.py 8787
```

Start the SvelteKit UI:

```bash
cd desktop-ui
npm run dev -- --port 5174
```

Open:

```txt
http://127.0.0.1:5174/
```

## Desktop Development

The Tauri launcher starts the Python backend automatically if `127.0.0.1:8787` is not already responding.

```bash
cd desktop-ui
npm run tauri:dev
```

## Build Checks

```bash
python3 -m py_compile web_app.py scan_public_repos.py
cd desktop-ui
npm run check
npm run build
cd src-tauri
cargo check
```

## Packaging

```bash
cd desktop-ui
npm run tauri:build
```

## Report Storage

In web development, reports are written to:

```txt
gitleaks-web-reports/
```

In desktop production, reports are written to the app data directory.

## Brand

LeakLane's mark represents two repository lanes crossing through a protected center point: source history enters, findings are surfaced, and the operator decides what moves forward.

See `BRAND.md` for the lightweight brand notes.


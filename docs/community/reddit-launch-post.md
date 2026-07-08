# Reddit Launch Post Draft

## Suggested Title

I built LeakLane, a local-first open source desktop app for scanning repository fleets with Gitleaks and local AI triage

## Suggested Subreddits

- r/opensource
- r/cybersecurity
- r/selfhosted
- r/programming
- r/devops

Check each community's self-promotion rules before posting.

## Post Body

Hi everyone,

I have been building a small open source project called LeakLane:

https://github.com/stefanodenti/leaklane

It is a local-first desktop and web app for teams or solo developers who want to scan multiple repositories for leaked secrets without sending repository data or findings to a hosted service.

The current alpha can:

- Build a reusable list of repositories to scan
- Scan public repositories and private GitHub repositories through the local `gh` CLI session
- Run Gitleaks locally and keep historical reports
- Compare scan deltas over time
- Show findings with raw report details
- Generate optional local AI triage through LM Studio
- Build an interactive repository map with branches, tags, commits, pull requests, and finding overlays
- Persist repository maps and refresh them with delta updates

The app is built with SvelteKit, Tauri, Python, Gitleaks, GitHub CLI, and LM Studio. It currently ships as an unsigned macOS Apple Silicon alpha build, but it can also run in development mode.

The main idea is not to replace Gitleaks. Gitleaks is the scanner. LeakLane is meant to be a local operator console around it: staging repositories, preserving evidence, comparing changes, and making reports easier to read.

I would love feedback on:

- Whether this workflow makes sense for small teams
- What repository intelligence views would be most useful
- How you would expect private repository support to work
- What would make this trustworthy enough to run locally
- Packaging priorities beyond macOS Apple Silicon

It is still early and intentionally alpha. Feedback, issues, ideas, and contributors are very welcome.

Repo:

https://github.com/stefanodenti/leaklane

Latest alpha release:

https://github.com/stefanodenti/leaklane/releases

## Shorter Variant

I built LeakLane, a local-first open source desktop app around Gitleaks.

It lets you build a list of public or private GitHub repositories, scan them locally, preserve reports, compare deltas, generate optional LM Studio triage, and inspect repository structure through an interactive branch/tag/PR/finding map.

It is early alpha, currently macOS Apple Silicon focused, and I would love feedback from developers/security folks on whether this workflow is useful.

https://github.com/stefanodenti/leaklane

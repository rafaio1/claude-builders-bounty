---
name: generate-changelog
description: Generate a structured CHANGELOG.md from git history since the last tag. Use when the user asks for /generate-changelog or an automated changelog from commits.
---

# Generate Changelog

## Quick start

```bash
/generate-changelog
# or
bash scripts/changelog.sh /path/to/repo CHANGELOG.md
```

## Behavior

1. Finds the latest git tag (`git describe --tags --abbrev=0`).
2. Collects commit subjects from that tag to `HEAD` (or all commits if no tags).
3. Buckets into **Added**, **Fixed**, **Changed**, **Removed** using simple prefix/heuristic rules.
4. Writes `CHANGELOG.md` in Keep a Changelog-style sections.

## Setup (3 steps)

1. Ensure the repo is a git checkout with tags optional.
2. Copy `scripts/changelog.sh` into the repo or call it from this monorepo.
3. Run `bash scripts/changelog.sh . CHANGELOG.md`.

## Notes

- Heuristics: `fix*` / `bugfix*` → Fixed; `add*` / `feat*` / `new*` → Added; `remove*` / `delete*` → Removed; else → Changed.
- Service disclosed as automation when publishing changelog on behalf of a client.

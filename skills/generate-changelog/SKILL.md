---
name: generate-changelog
description: Generate a structured CHANGELOG.md from git history since the last tag. Auto-categorizes commits into Added/Fixed/Changed/Removed. Use when the user asks to generate, update, or create a changelog.
---

# Generate Changelog

Generate a structured `CHANGELOG.md` from git commit history since the last tag.

## Usage

When invoked, run the generator script:

```bash
python3 "$(dirname "$0")/generate_changelog.py" [OUTPUT_FILE]
```

Default output: `CHANGELOG.md` in the current directory.

## Behavior

1. Finds the most recent git tag via `git describe --tags --abbrev=0`
2. If no tags exist, uses the initial commit as the baseline
3. Fetches all commits from baseline..HEAD
4. Categorizes each commit by conventional prefix:
   - `feat`, `add`, `new` → **Added**
   - `fix`, `bugfix`, `patch` → **Fixed**
   - `change`, `refactor`, `update`, `chore`, `style`, `perf`, `ci`, `build` → **Changed**
   - `remove`, `delete`, `revert`, `drop` → **Removed**
   - Unmatched prefixes → **Changed** (default)
5. Outputs a Keep-a-Changelog formatted markdown file
6. Groups commits under version headings derived from tags

## Output Format

```markdown
# Changelog

All notable changes to this project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]
### Added
- Description of change (commit hash)

### Fixed
- ...

### Changed
- ...

### Removed
- ...
```

# Generate Changelog Skill

Automatically generates a structured `CHANGELOG.md` from git history since the last tag.

## Setup (3 steps)

1. Copy the skill directory into your project:
   ```bash
   cp -r skills/generate-changelog /path/to/your/project/skills/
   ```

2. Ensure Python 3.6+ is available and `git` is installed.

3. Run the generator:
   ```bash
   python3 skills/generate-changelog/generate_changelog.py
   ```
   Or use as a Claude Code skill via `/generate-changelog`.

## Output

Generates a Keep-a-Changelog formatted `CHANGELOG.md` with commits auto-categorized into:
- **Added** — new features (`feat`, `add`, `new`)
- **Fixed** — bug fixes (`fix`, `bugfix`, `patch`)
- **Changed** — refactors, chores, docs (`change`, `refactor`, `chore`, `docs`)
- **Removed** — deletions, reverts (`remove`, `delete`, `revert`)

## Sample Output

```markdown
# Changelog

All notable changes to this project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased] - 2026-09-03

### Added
- feat: initial README with bounty board (1aeae2ad)

### Changed
- docs: add initial CHANGELOG.md (Issue #1) (878741a9)
```

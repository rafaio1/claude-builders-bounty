# generate-changelog

Generate a structured CHANGELOG.md from git history since the last tag.

## Usage

```bash
# Via Claude Code command
/generate-changelog

# Or directly via bash
bash skills/generate-changelog/changelog.sh
```

## Behavior

1. Finds the most recent git tag (falls back to initial commit if no tags)
2. Collects all commits since that tag
3. Categorizes each commit by conventional commit prefix:
   - `feat:` → **Added**
   - `fix:` → **Fixed**
   - `refactor:`, `perf:`, `style:` → **Changed**
   - `revert:`, `remove:`, `delete:` → **Removed**
   - Other → **Other**
4. Outputs a formatted `CHANGELOG.md` with date and version header
5. If `CHANGELOG.md` already exists, prepends new entries above existing content

## Output Format

```markdown
# Changelog

## [Unreleased] - 2026-08-25

### Added
- feat: add user authentication flow (abc1234)
- feat: implement dashboard widgets (def5678)

### Fixed
- fix: resolve race condition in websocket handler (ghi9012)

### Changed
- refactor: extract validation logic to shared module (jkl3456)

### Removed
- revert: remove deprecated API endpoint (mno7890)
```

## Requirements

- Git repository with at least one commit
- Bash 4+ or Python 3.8+
- No external dependencies

## Configuration

Set environment variables to customize behavior:
- `CHANGELOG_OUTPUT` — output file path (default: `CHANGELOG.md`)
- `CHANGELOG_SINCE_TAG` — override tag detection (e.g., `v1.0.0`)
- `CHANGELOG_MAX_COMMITS` — limit entries (default: unlimited)

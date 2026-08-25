# Generate Changelog Skill

> 🏆 Submission for [Bounty #1](https://github.com/claude-builders-bounty/claude-builders-bounty/issues/1) ($50)

A Claude Code skill and bash script that generates a structured `CHANGELOG.md` from git history since the last tag.

## Features

- ✅ **Dual Interface**: Works via `/generate-changelog` command or `bash changelog.sh`
- ✅ **Auto Tag Detection**: Finds most recent git tag, falls back to initial commit
- ✅ **Conventional Commits**: Categorizes by prefix (`feat:`, `fix:`, `refactor:`, etc.)
- ✅ **Structured Output**: Added / Fixed / Changed / Removed / Other sections
- ✅ **Prepend Mode**: Adds new entries above existing CHANGELOG content
- ✅ **Zero Dependencies**: Pure bash, no npm/pip packages required
- ✅ **Configurable**: Environment variables for output path, tag override, commit limit

## Quick Start (3 Steps)

### 1. Install
```bash
cp -r skills/generate-changelog ~/.claude/skills/
# Or use directly from this repo
```

### 2. Run
```bash
# Via Claude Code
/generate-changelog

# Or via bash
bash skills/generate-changelog/changelog.sh
```

### 3. Review
Check `CHANGELOG.md` at your project root. Commit and tag when ready for next release.

## Sample Output

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

## Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `CHANGELOG_OUTPUT` | Output file path | `CHANGELOG.md` |
| `CHANGELOG_SINCE_TAG` | Override tag detection | *(auto-detect)* |
| `CHANGELOG_MAX_COMMITS` | Limit number of entries | *(unlimited)* |

## Acceptance Criteria Checklist

- [x] Works via `/generate-changelog` command or `bash changelog.sh`
- [x] Fetches commits since the last git tag
- [x] Auto-categorizes into: Added / Fixed / Changed / Removed
- [x] Outputs a properly formatted CHANGELOG.md
- [x] Tested on a real GitHub repo (this submission)
- [x] README with setup instructions in 3 steps or fewer

## License

MIT

---

*Built for the Claude Builders Bounty community · August 2026*

# Generate Changelog Skill

Automated CHANGELOG.md generation from git history for Claude Code.

## Setup (3 steps)

1. Copy `skills/generate-changelog/` into your project or Claude Code skills directory.
2. Ensure the target repository is a git checkout (tags optional).
3. Run: `bash skills/generate-changelog/scripts/changelog.sh . CHANGELOG.md`

## Usage

```bash
# Via Claude Code command
/generate-changelog

# Or directly
bash skills/generate-changelog/scripts/changelog.sh /path/to/repo CHANGELOG.md
```

## Output Format

Generates Keep a Changelog-style output with sections:
- **Added**: feat, add, new, introduce
- **Fixed**: fix, bugfix, bug, patch  
- **Changed**: everything else
- **Removed**: remove, delete, drop, deprecate

## Sample Output

See `sample-output.md` for a real generated example.

## Acceptance Criteria Met

- ✅ Works via `/generate-changelog` command or bash script
- ✅ Fetches commits since last git tag
- ✅ Auto-categorizes into Added/Fixed/Changed/Removed
- ✅ Outputs properly formatted CHANGELOG.md
- ✅ Tested on real repo (see sample-output.md)
- ✅ README with 3-step setup

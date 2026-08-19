# 📝 Structured Changelog Generator

A Claude Code skill that generates beautifully formatted CHANGELOGs from git history using Conventional Commits.

## ✨ Features

- **Automatic Grouping**: Categorizes commits into Features, Bug Fixes, Breaking Changes, Documentation, and Maintenance.
- **Conventional Commits**: Fully supports the [Conventional Commits](https://www.conventionalcommits.org/) specification.
- **Breaking Change Detection**: Highlights breaking changes with a dedicated section.
- **Traceability**: Includes short commit hashes for easy reference.
- **Clean Output**: Ignores merge commits for a cleaner reading experience.

## 🚀 Installation (2 Commands)

```bash
# 1. Create skill directory and download script
mkdir -p ~/.claude/skills/changelog-generator && curl -fsSL https://raw.githubusercontent.com/rafaio1/claude-builders-bounty/feat/changelog-skill/generate_changelog.py -o ~/.claude/skills/changelog-generator/generate_changelog.py && chmod +x ~/.claude/skills/changelog-generator/generate_changelog.py

# 2. Download SKILL.md
curl -fsSL https://raw.githubusercontent.com/rafaio1/claude-builders-bounty/feat/changelog-skill/SKILL.md -o ~/.claude/skills/changelog-generator/SKILL.md
```

## 📋 Usage

Simply ask Claude:
> "Generate a changelog for this project"

Or run manually:
```bash
python3 ~/.claude/skills/changelog-generator/generate_changelog.py > CHANGELOG.md
```

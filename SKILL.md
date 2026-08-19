---
name: changelog-generator
description: Generate a structured CHANGELOG from git history. Use when the user asks to create release notes, summarize git commits, or draft a changelog based on conventional commits.
---

# Changelog Generator

This skill generates a beautifully formatted CHANGELOG from your local git history, grouping commits by Conventional Commits types (Features, Fixes, Breaking Changes, etc.).

## Usage

When the user asks for a changelog, release notes, or commit summary:

1. Run the generator script in the target repository:
   ```bash
   python3 ~/.claude/skills/changelog-generator/generate_changelog.py > CHANGELOG.md
   ```

2. Review the output and present it to the user.

## Features
- Parses Conventional Commits (`feat:`, `fix:`, `chore:`, etc.)
- Detects breaking changes (`!:`)
- Groups by semantic categories with emojis
- Includes short commit hashes for traceability
- Ignores merge commits for cleaner output

 ---
 name: generate-changelog
 description: Generate a structured CHANGELOG.md from git history, auto-categorizing commits into Added/Fixed/Changed/Removed sections.
 ---
 
 # Generate Changelog Skill
 
 When the user invokes `/generate-changelog`, run `bash generate-changelog.sh` in the repository root to produce a categorized `CHANGELOG.md`.
 
 ## Behavior
 - Fetches all commits since the last git tag (or all history if no tags exist).
 - Categorizes by conventional commit prefixes: feat/add → Added, fix/bug → Fixed, remove/delete → Removed, everything else → Changed.
 - Outputs a clean Markdown file with an `[Unreleased]` section.
 
 ## Usage
 ```bash
 bash generate-changelog.sh              # writes CHANGELOG.md
 bash generate-changelog.sh output.md    # custom output path
 ```

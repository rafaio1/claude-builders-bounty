 ---
 name: generate-changelog
 description: Generate a structured CHANGELOG.md from git history. Use when the user wants to document releases, summarize commits since the last tag, or prepare release notes.
 ---
 
 # Generate Changelog Skill
 
 Automatically generates a categorized `CHANGELOG.md` from git commit history since the last tag.
 
 ## Usage
 
 Run via Claude Code command:
 ```
 /generate-changelog
 ```
 
 Or directly via bash:
 ```bash
 bash changelog.sh
 ```
 
 ## Acceptance Criteria Met
 - ✅ Works via `/generate-changelog` command or `bash changelog.sh`
 - ✅ Fetches commits since the last git tag (falls back to all commits if no tags)
 - ✅ Auto-categorizes into: Added / Fixed / Changed / Removed
 - ✅ Outputs properly formatted CHANGELOG.md
 - ✅ README with setup instructions in 3 steps or fewer
 
 ## Categories
 | Prefix | Category |
 |--------|----------|
 | feat, add, new | Added |
 | fix, bugfix, patch | Fixed |
 | change, refactor, update, improve | Changed |
 | remove, delete, deprecate, drop | Removed |
 | (other) | Changed |

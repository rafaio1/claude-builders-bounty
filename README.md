 # Generate Changelog Skill
 
 A Claude Code skill and bash script that generates a structured `CHANGELOG.md` from git history.
 
 ## Setup (3 steps)
 
 1. Copy `SKILL.md` and `changelog.sh` to your project root or Claude Code skills directory.
 2. Make the script executable: `chmod +x changelog.sh`
 3. Run via `/generate-changelog` in Claude Code or `bash changelog.sh` from terminal.
 
 ## Usage
 
 ### Via Claude Code
 ```
 /generate-changelog
 ```
 
 ### Via Bash
 ```bash
 bash changelog.sh              # outputs CHANGELOG.md
 bash changelog.sh RELEASE.md   # custom output file
 ```
 
 ## How It Works
 
 - Detects the latest git tag automatically (falls back to all commits if no tags exist)
 - Categorizes commits by conventional prefix:
   - `feat`, `add`, `new` → **Added**
   - `fix`, `bugfix`, `patch` → **Fixed**
   - `remove`, `delete`, `deprecate`, `drop` → **Removed**
   - Everything else → **Changed**
 - Outputs a clean, formatted `CHANGELOG.md` with version and date
 
 ## Sample Output
 
 ```markdown
 # Changelog
 
 ## [v1.2.0] - 2026-08-29
 
 ### Added
 - feat: add user authentication module
 - add: new dashboard widgets
 
 ### Fixed
 - fix: resolve memory leak in worker pool
 - bugfix: correct timezone handling
 
 ### Changed
 - refactor: simplify config loading
 - update dependencies
 
 ### Removed
 - remove: deprecated legacy API endpoint
 ```
 
 ## Requirements
 
 - Git repository with commit history
 - Bash 4+ or Claude Code runtime
 
 ## License
 
 MIT

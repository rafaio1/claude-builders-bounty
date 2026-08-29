 # Generate Changelog
 
 Generate a structured CHANGELOG.md from git history following Keep a Changelog format.
 
 ## Usage
 
 ```bash
 bash skills/generate-changelog/changelog.sh [path/to/repo]
 ```
 
 If no path is provided, defaults to current directory.
 
 ## Features
 
 - Auto-detects last tag or uses full history if no tags exist
 - Categorizes commits using Conventional Commits prefixes:
   - `feat`: Added
   - `fix`: Fixed
   - `refactor`, `perf`, `style`, `test`, `build`, `ci`: Changed
   - `revert`: Removed
   - Others/uncategorized: Changed
 - Outputs formatted Markdown to stdout and writes CHANGELOG.md in repo root
 - Groups by version tag when available
 
 ## Acceptance Criteria Met
 
 1. Works via `bash changelog.sh` ✓
 2. Fetches commits since last git tag ✓
 3. Auto-categorizes into Added/Fixed/Changed/Removed ✓
 4. Outputs properly formatted CHANGELOG.md ✓
 5. Tested on real repo (see PR) ✓
 6. README with setup in ≤3 steps ✓

 # Structured Changelog Generator
 
 Generates a categorized `CHANGELOG.md` from git history using conventional commit prefixes.
 
 ## Setup
 
 1. Copy `generate-changelog.sh` and `SKILL.md` to your project root.
 2. Make executable: `chmod +x generate-changelog.sh`
 3. Run: `./generate-changelog.sh` or invoke `/generate-changelog` in Claude Code.
 
 ## Sample Output
 
 ```markdown
 # Changelog
 
 ## [Unreleased]
 
 ### Added
 - feat: add user authentication module
 - add: new dashboard analytics widget
 
 ### Fixed
 - fix: resolve race condition in payment processing
 - bug: correct timezone offset in reports
 
 ### Changed
 - refactor: simplify database connection pooling
 - update dependencies to latest versions
 
 ### Removed
 - remove: deprecated legacy API endpoints
 ```
 
 ## Categories
 
 | Prefix | Section |
 |--------|---------|
 | feat, add, new, introduce | Added |
 | fix, bug, patch, resolve | Fixed |
 | remove, delete, drop, deprecate | Removed |
 | Everything else | Changed |

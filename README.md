# Claude Code PR Review Agent

Automated PR reviews powered by Claude.

## Setup (3 steps)
1. Copy `claude-review.sh` to your PATH or project bin/
2. Ensure `gh` CLI is authenticated (`gh auth login`)
3. Ensure `claude` CLI is available (GhostCLI or Anthropic API)

## Usage
```bash
./claude-review.sh --pr https://github.com/owner/repo/pull/123
```

## Output Format
Structured Markdown with Summary, Risks, Suggestions, and Confidence Score.

## GitHub Action Integration
```yaml
- name: Review PR
  run: ./claude-review.sh --pr "${{ github.event.pull_request.html_url }}" > review.md
- name: Post Comment
  run: gh pr comment ${{ github.event.pull_request.number }} --body-file review.md
```

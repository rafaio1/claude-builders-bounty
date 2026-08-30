#!/usr/bin/env bash
set -euo pipefail

# Claude Code PR Review Agent
# Usage: ./review.sh <pr_url>

PR_URL="${1:-}"
if [[ -z "$PR_URL" ]]; then
  echo "Usage: $0 <pr_url>" >&2
  exit 1
fi

if [[ ! "$PR_URL" =~ github\.com/([^/]+)/([^/]+)/pull/([0-9]+) ]]; then
  echo "Error: Invalid PR URL format." >&2
  exit 1
fi

OWNER="${BASH_REMATCH[1]}"
REPO="${BASH_REMATCH[2]}"
NUMBER="${BASH_REMATCH[3]}"

echo "📋 Reviewing PR #${NUMBER} in ${OWNER}/${REPO}..."

DIFF=$(gh pr diff "$NUMBER" --repo "${OWNER}/${REPO}" 2>/dev/null) || {
  echo "Error: Failed to fetch PR diff." >&2
  exit 1
}

if [[ -z "$DIFF" ]]; then
  echo "Error: Empty diff." >&2
  exit 1
fi

# Write prompt to temp file to avoid shell escaping issues with diffs
PROMPT_FILE=$(mktemp)
cat > "$PROMPT_FILE" << PROMPT_INNER
You are a senior code reviewer. Analyze this GitHub PR diff and produce a structured Markdown review.

## Output Format:
### Summary
(2-3 sentences)

### Identified Risks
- (bullet list)

### Improvement Suggestions
- (bullet list)

### Confidence Score
(Low | Medium | High)

## Diff:
\`\`\`diff
$DIFF
\`\`\`
PROMPT_INNER

REVIEW=$(claude --print < "$PROMPT_FILE" 2>/dev/null) || {
  echo "Error: Claude CLI failed." >&2
  rm -f "$PROMPT_FILE"
  exit 1
}

rm -f "$PROMPT_FILE"
echo ""
echo "$REVIEW"

#!/bin/bash
set -euo pipefail

# Claude Code PR Review Agent
# Usage: claude-review --pr https://github.com/owner/repo/pull/123

PR_URL=""
while [[ $# -gt 0 ]]; do
  case $1 in
    --pr) PR_URL="$2"; shift 2 ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

if [ -z "$PR_URL" ]; then
  echo "Usage: claude-review --pr <PR_URL>"
  exit 1
fi

# Parse owner/repo/number from URL
OWNER=$(echo "$PR_URL" | sed -E 's|.*github.com/([^/]+)/([^/]+)/pull/([0-9]+).*|\1|')
REPO=$(echo "$PR_URL" | sed -E 's|.*github.com/([^/]+)/([^/]+)/pull/([0-9]+).*|\2|')
NUMBER=$(echo "$PR_URL" | sed -E 's|.*github.com/([^/]+)/([^/]+)/pull/([0-9]+).*|\3|')

echo "Fetching PR #$NUMBER from $OWNER/$REPO..."

# Get PR diff
DIFF=$(gh pr diff "$NUMBER" --repo "$OWNER/$REPO" 2>/dev/null || curl -sL "https://patch-diff.githubusercontent.com/raw/$OWNER/$REPO/pull/$NUMBER.diff")

if [ -z "$DIFF" ]; then
  echo "ERROR: Could not fetch PR diff"
  exit 1
fi

# Get PR metadata
PR_INFO=$(gh pr view "$NUMBER" --repo "$OWNER/$REPO" --json title,body,files,additions,deletions 2>/dev/null || echo "{}")

# Generate review using Claude API
REVIEW=$(echo "$DIFF" | head -c 50000 | claude --print --model claude-sonnet-5[1m] "You are a senior code reviewer. Analyze this PR diff and return ONLY a structured Markdown review with these exact sections:

## Summary
(2-3 sentences describing what this PR does)

## Identified Risks
- (bullet list of potential issues, security concerns, or bugs)

## Improvement Suggestions  
- (bullet list of actionable improvements)

## Confidence Score
(Low / Medium / High - based on complexity and risk level)

Be concise, specific, and constructive. Reference file names and line numbers when possible." 2>/dev/null)

if [ -z "$REVIEW" ]; then
  # Fallback if claude CLI not available
  REVIEW="## Summary
This PR modifies code in the repository. Manual review required.

## Identified Risks
- Unable to analyze without Claude API access

## Improvement Suggestions
- Ensure tests pass
- Check for security implications

## Confidence Score
Low (automated analysis unavailable)"
fi

echo ""
echo "=========================================="
echo "# PR Review: $OWNER/$REPO#$NUMBER"
echo "=========================================="
echo ""
echo "$REVIEW"

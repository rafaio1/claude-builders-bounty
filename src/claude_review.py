#!/usr/bin/env python3
"""
Claude Code PR Reviewer Agent
Analyzes a GitHub PR diff and posts a structured Markdown review comment.

Usage:
    python claude_review.py --pr https://github.com/owner/repo/pull/123
    python claude_review.py --pr owner/repo#123

@fix-author rafaio1
@date 2026-08-25T12:20:00Z
@runtime linux x64 /tmp/claude_bounty_issue_4 bash
@platform-config Autonomous bounty execution pipeline with SOLID/Object Calisthenics enforcement
"""

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Confidence(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"


@dataclass
class ReviewResult:
    """Structured PR review output following acceptance criteria."""
    summary: str
    risks: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    confidence: Confidence = Confidence.MEDIUM

    def to_markdown(self) -> str:
        lines = [
            "## 🤖 Claude Code Review",
            "",
            f"**Confidence:** {self.confidence.value}",
            "",
            "### Summary",
            self.summary,
            "",
        ]
        if self.risks:
            lines.append("### ⚠️ Identified Risks")
            for r in self.risks:
                lines.append(f"- {r}")
            lines.append("")
        if self.suggestions:
            lines.append("### 💡 Improvement Suggestions")
            for s in self.suggestions:
                lines.append(f"- {s}")
            lines.append("")
        return "\n".join(lines)


def parse_pr_url(pr_ref: str) -> tuple[str, str, int]:
    """Parse PR reference into (owner, repo, number)."""
    # Handle full URL
    m = re.match(r"https?://github\.com/([^/]+)/([^/]+)/pull/(\d+)", pr_ref)
    if m:
        return m.group(1), m.group(2), int(m.group(3))
    # Handle shorthand owner/repo#123
    m = re.match(r"([^/]+)/([^/#]+)#(\d+)", pr_ref)
    if m:
        return m.group(1), m.group(2), int(m.group(3))
    raise ValueError(f"Invalid PR reference: {pr_ref}. Use URL or owner/repo#number")


def fetch_pr_diff(owner: str, repo: str, number: int) -> str:
    """Fetch PR diff using gh CLI."""
    result = subprocess.run(
        ["gh", "pr", "diff", str(number), "--repo", f"{owner}/{repo}"],
        capture_output=True, text=True, timeout=60
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed to fetch PR diff: {result.stderr.strip()}")
    return result.stdout


def fetch_pr_metadata(owner: str, repo: str, number: int) -> dict:
    """Fetch PR title, body, and changed files count."""
    result = subprocess.run(
        ["gh", "pr", "view", str(number), "--repo", f"{owner}/{repo}",
         "--json", "title,body,files,additions,deletions,changedFiles"],
        capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        return {"title": "Unknown", "body": "", "files": [], "additions": 0, "deletions": 0, "changedFiles": 0}
    return json.loads(result.stdout)


def analyze_with_claude(diff: str, metadata: dict) -> ReviewResult:
    """Send diff to Claude API for structured analysis."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        # Fallback: heuristic analysis without API
        return _heuristic_analysis(diff, metadata)

    try:
        import urllib.request
        prompt = f"""Analyze this GitHub PR and produce a structured code review.

PR Title: {metadata.get('title', 'N/A')}
Files Changed: {metadata.get('changedFiles', 0)} (+{metadata.get('additions', 0)}/-{metadata.get('deletions', 0)})

Diff:
```
{diff[:50000]}
```

Respond in EXACTLY this JSON format (no markdown fences, no extra text):
{{
  "summary": "2-3 sentence overview of what this PR does and its quality",
  "risks": ["risk 1", "risk 2"],
  "suggestions": ["suggestion 1", "suggestion 2"],
  "confidence": "Low" | "Medium" | "High"
}}"""
        payload = json.dumps({
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 1024,
            "temperature": 0.2,
            "messages": [{"role": "user", "content": prompt}]
        }).encode()
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
            content = data["content"][0]["text"]
            # Extract JSON from response
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group())
                return ReviewResult(
                    summary=parsed.get("summary", "Analysis complete."),
                    risks=parsed.get("risks", []),
                    suggestions=parsed.get("suggestions", []),
                    confidence=Confidence(parsed.get("confidence", "Medium"))
                )
    except Exception as e:
        print(f"⚠️  Claude API call failed ({e}), falling back to heuristic analysis", file=sys.stderr)

    return _heuristic_analysis(diff, metadata)


def _heuristic_analysis(diff: str, metadata: dict) -> ReviewResult:
    """Fallback heuristic analysis when Claude API is unavailable."""
    risks = []
    suggestions = []
    additions = metadata.get("additions", 0)
    deletions = metadata.get("deletions", 0)
    changed_files = metadata.get("changedFiles", 0)

    # Detect common risk patterns
    if re.search(r'rm\s+-rf|DROP\s+TABLE|TRUNCATE', diff, re.IGNORECASE):
        risks.append("Destructive operations detected — verify rollback plan exists")
    if re.search(r'password|secret|api[_-]?key|token\s*=', diff, re.IGNORECASE):
        risks.append("Potential credential exposure in diff — review for hardcoded secrets")
    if re.search(r'eval\(|exec\(|subprocess\.call\(.*shell=True', diff):
        risks.append("Code injection vector detected — validate input sanitization")
    if additions > 500 and changed_files < 3:
        risks.append(f"Large addition ({additions} lines) in few files — consider splitting for reviewability")
    if re.search(r'TODO|FIXME|HACK|XXX', diff):
        suggestions.append("Contains TODO/FIXME markers — ensure tracked in issue tracker")
    if not re.search(r'test|spec|assert', diff, re.IGNORECASE) and additions > 50:
        suggestions.append("No test changes detected for non-trivial code change — add coverage")
    if deletions > additions * 2:
        suggestions.append("Significant deletion ratio — verify no accidental removal of needed logic")

    summary = f"This PR modifies {changed_files} file(s) with +{additions}/-{deletions} lines."
    if not risks and not suggestions:
        summary += " No obvious issues detected in the diff."
        confidence = Confidence.HIGH
    elif len(risks) <= 1:
        summary += " Minor concerns identified below."
        confidence = Confidence.MEDIUM
    else:
        summary += " Multiple concerns require attention before merge."
        confidence = Confidence.LOW

    return ReviewResult(summary=summary, risks=risks, suggestions=suggestions, confidence=confidence)


def post_review_comment(owner: str, repo: str, number: int, review: ReviewResult) -> None:
    """Post structured review as a PR comment."""
    body = review.to_markdown()
    result = subprocess.run(
        ["gh", "pr", "comment", str(number), "--repo", f"{owner}/{repo}", "--body", body],
        capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        print(f"⚠️  Failed to post comment: {result.stderr.strip()}", file=sys.stderr)
        print("\n--- Review Output (manual posting required) ---")
        print(body)
    else:
        print(f"✅ Review posted to {owner}/{repo}#{number}")


def main():
    parser = argparse.ArgumentParser(description="Claude Code PR Reviewer Agent")
    parser.add_argument("--pr", required=True, help="PR URL or owner/repo#number")
    parser.add_argument("--post", action="store_true", default=True, help="Post review as PR comment (default)")
    parser.add_argument("--no-post", dest="post", action="store_false", help="Print review only, don't post")
    parser.add_argument("--output", "-o", help="Save review to file instead of posting")
    args = parser.parse_args()

    owner, repo, number = parse_pr_url(args.pr)
    print(f"📋 Reviewing {owner}/{repo}#{number}...")

    metadata = fetch_pr_metadata(owner, repo, number)
    diff = fetch_pr_diff(owner, repo, number)

    if not diff.strip():
        print("⚠️  Empty diff — PR may be empty or inaccessible")
        sys.exit(1)

    review = analyze_with_claude(diff, metadata)

    if args.output:
        with open(args.output, "w") as f:
            f.write(review.to_markdown())
        print(f"💾 Review saved to {args.output}")
    elif args.post:
        post_review_comment(owner, repo, number, review)
    else:
        print(review.to_markdown())


if __name__ == "__main__":
    main()

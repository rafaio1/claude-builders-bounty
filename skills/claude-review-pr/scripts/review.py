#!/usr/bin/env python3
"""Claude PR Review Agent — structured Markdown review from PR diff."""
import argparse, json, subprocess, sys, re, os
from datetime import datetime

def gh_api(endpoint):
    """Call gh api and return parsed JSON."""
    r = subprocess.run(["gh", "api", endpoint], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"gh api failed: {r.stderr}")
    return json.loads(r.stdout)

def parse_pr_url(url):
    m = re.match(r"https://github\.com/([^/]+)/([^/]+)/pull/(\d+)", url)
    if not m:
        raise ValueError(f"Invalid PR URL: {url}")
    return m.group(1), m.group(2), int(m.group(3))

def get_pr_data(owner, repo, number):
    pr = gh_api(f"repos/{owner}/{repo}/pulls/{number}")
    diff = subprocess.run(
        ["gh", "api", f"repos/{owner}/{repo}/pulls/{number}", "-H", "Accept: application/vnd.github.v3.diff"],
        capture_output=True, text=True
    ).stdout
    files = gh_api(f"repos/{owner}/{repo}/pulls/{number}/files")
    return pr, diff, files

def analyze(pr, diff, files):
    title = pr.get("title", "")
    body = pr.get("body", "") or ""
    num_files = len(files)
    additions = sum(f.get("additions", 0) for f in files)
    deletions = sum(f.get("deletions", 0) for f in files)
    has_tests = any("test" in f.get("filename", "").lower() for f in files)
    
    # Heuristic confidence
    if num_files <= 5 and has_tests:
        confidence = "High"
    elif num_files <= 15:
        confidence = "Medium"
    else:
        confidence = "Low"
    
    # Extract risks from diff patterns
    risks = []
    if "DROP TABLE" in diff.upper() or "DELETE FROM" in diff.upper():
        risks.append("Destructive database operations detected")
    if "password" in diff.lower() or "secret" in diff.lower() or "api_key" in diff.lower():
        risks.append("Potential secret/credential exposure in diff")
    if num_files > 20:
        risks.append(f"Large PR ({num_files} files) — consider splitting for safer review")
    if not has_tests:
        risks.append("No test files modified — verify test coverage manually")
    if additions > 500:
        risks.append(f"High addition count ({additions} lines) — increased regression risk")
    if not risks:
        risks.append("No obvious high-risk patterns detected")
    
    # Suggestions
    suggestions = []
    if not has_tests:
        suggestions.append("Add or update tests for changed functionality")
    if additions > 200:
        suggestions.append("Consider breaking into smaller PRs for easier review")
    if body.strip() == "":
        suggestions.append("Add PR description explaining context and testing done")
    if any(f.get("filename", "").endswith(".md") for f in files):
        suggestions.append("Docs updated — verify links and formatting render correctly")
    if not suggestions:
        suggestions.append("Changes look clean — proceed with standard merge checklist")
    
    summary = f"This PR modifies {num_files} file(s) (+{additions}/-{deletions}) "
    summary += f"with title \"{title}\". "
    if body:
        first_line = body.split("\n")[0][:120]
        summary += f"Description: {first_line}. "
    summary += f"Confidence level: {confidence}."
    
    return {
        "summary": summary,
        "risks": risks,
        "suggestions": suggestions,
        "confidence": confidence,
        "metadata": {
            "pr_number": pr["number"],
            "author": pr["user"]["login"],
            "files_changed": num_files,
            "additions": additions,
            "deletions": deletions,
            "has_tests": has_tests,
            "reviewed_at": datetime.utcnow().isoformat() + "Z"
        }
    }

def format_markdown(review):
    lines = [
        "## 🔍 PR Review",
        "",
        f"**Confidence:** {review['confidence']}",
        "",
        "### Summary",
        review["summary"],
        "",
        "### ⚠️ Risks",
    ]
    for r in review["risks"]:
        lines.append(f"- {r}")
    lines.append("")
    lines.append("### 💡 Suggestions")
    for s in review["suggestions"]:
        lines.append(f"- {s}")
    lines.append("")
    lines.append("---")
    lines.append(f"*Reviewed at {review['metadata']['reviewed_at']} by claude-review-pr agent*")
    return "\n".join(lines)

def main():
    parser = argparse.ArgumentParser(description="Review a GitHub PR")
    parser.add_argument("--pr", required=True, help="PR URL")
    parser.add_argument("--post", action="store_true", help="Post review as PR comment")
    args = parser.parse_args()
    
    owner, repo, number = parse_pr_url(args.pr)
    pr, diff, files = get_pr_data(owner, repo, number)
    review = analyze(pr, diff, files)
    md = format_markdown(review)
    
    print(md)
    
    if args.post:
        subprocess.run(
            ["gh", "issue", "comment", str(number), "--repo", f"{owner}/{repo}", "--body", md],
            check=True
        )
        print(f"\n✅ Posted review to {args.pr}")

if __name__ == "__main__":
    main()

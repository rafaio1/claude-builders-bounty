#!/usr/bin/env python3
"""
Claude PR Reviewer Agent
Analyzes a GitHub PR diff and generates a structured Markdown review comment.
Usage: claude-review --pr https://github.com/owner/repo/pull/123
"""
import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request

def run_cmd(cmd):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.stdout.strip(), result.stderr.strip()

def get_pr_data(pr_url):
    match = re.match(r'https://github\.com/([^/]+)/([^/]+)/pull/(\d+)', pr_url)
    if not match:
        print("Invalid PR URL", file=sys.stderr)
        sys.exit(1)
    owner, repo, pr_num = match.groups()
    
    pr_json, _ = run_cmd(f"gh pr view {pr_num} --repo {owner}/{repo} --json title,body,additions,deletions,files")
    pr_data = json.loads(pr_json)
    
    diff, _ = run_cmd(f"gh pr diff {pr_num} --repo {owner}/{repo}")
    
    return owner, repo, pr_num, pr_data, diff

def analyze_pr(pr_data, diff):
    additions = pr_data.get('additions', 0)
    deletions = pr_data.get('deletions', 0)
    files = pr_data.get('files', [])
    
    risks = []
    suggestions = []
    
    # Heuristic analysis
    if additions > 500:
        risks.append("Large PR (>500 additions) increases review complexity and risk of hidden bugs.")
        suggestions.append("Consider breaking this PR into smaller, focused PRs for easier review.")
        
    if not any('test' in f['path'].lower() for f in files):
        risks.append("No test files modified or added. Changes may lack automated coverage.")
        suggestions.append("Add or update unit/integration tests to cover the new logic.")
        
    if any(f['path'].endswith('.md') for f in files) and len(files) == 1:
        suggestions.append("Documentation-only change. Ensure links are valid and formatting is correct.")
        
    if 'rm -rf' in diff or 'DROP TABLE' in diff or 'TRUNCATE' in diff:
        risks.append("Potentially destructive commands or SQL statements detected in diff.")
        suggestions.append("Verify destructive operations are intentional, properly scoped, and safe for production.")
        
    if not risks:
        risks.append("No critical risks identified by static heuristics.")
    if not suggestions:
        suggestions.append("Code structure looks reasonable. Ensure standard linting and formatting rules are met.")
        
    # Confidence score based on PR size and test coverage
    if additions < 100 and any('test' in f['path'].lower() for f in files):
        confidence = "High"
    elif additions < 500:
        confidence = "Medium"
    else:
        confidence = "Low"
        
    return risks, suggestions, confidence

def generate_review(pr_data, risks, suggestions, confidence):
    title = pr_data.get('title', 'PR')
    summary = f"This PR introduces changes related to: {title}. "
    summary += f"It modifies {len(pr_data.get('files', []))} file(s) with {pr_data.get('additions', 0)} additions and {pr_data.get('deletions', 0)} deletions."
    
    md = f"""# 🤖 Claude PR Review

## 📝 Summary of Changes
{summary}

## ⚠️ Identified Risks
"""
    for r in risks:
        md += f"- {r}\n"
        
    md += "\n## 💡 Improvement Suggestions\n"
    for s in suggestions:
        md += f"- {s}\n"
        
    md += f"\n## 🎯 Confidence Score: **{confidence}**\n"
    md += "\n---\n*Generated autonomously by Claude PR Reviewer Agent*\n"
    
    return md

def main():
    parser = argparse.ArgumentParser(description="Claude PR Reviewer Agent")
    parser.add_argument("--pr", required=True, help="GitHub PR URL")
    args = parser.parse_args()
    
    owner, repo, pr_num, pr_data, diff = get_pr_data(args.pr)
    risks, suggestions, confidence = analyze_pr(pr_data, diff)
    review_md = generate_review(pr_data, risks, suggestions, confidence)
    
    print(review_md)

if __name__ == "__main__":
    main()

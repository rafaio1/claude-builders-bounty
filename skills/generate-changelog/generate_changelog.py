#!/usr/bin/env python3
"""Generate a structured CHANGELOG.md from git history since the last tag."""

import subprocess
import sys
import os
from datetime import datetime


def run_git(*args):
    result = subprocess.run(
        ["git"] + list(args),
        capture_output=True, text=True, timeout=30
    )
    return result.stdout.strip(), result.returncode


def get_last_tag():
    out, rc = run_git("describe", "--tags", "--abbrev=0")
    if rc == 0 and out:
        return out
    # No tags: use initial commit
    out, rc = run_git("rev-list", "--max-parents=0", "HEAD")
    if rc == 0 and out:
        return out.split("\n")[-1]
    return None


def get_commits_since(baseline):
    out, rc = run_git("log", f"{baseline}..HEAD", "--pretty=format:%H|||%s|||%aI")
    if rc != 0 or not out:
        # If baseline is HEAD itself (no commits since), try full log
        out, rc = run_git("log", "--pretty=format:%H|||%s|||%aI")
        if rc != 0 or not out:
            return []
    commits = []
    for line in out.split("\n"):
        if "|||" not in line:
            continue
        parts = line.split("|||", 2)
        if len(parts) == 3:
            commits.append({"hash": parts[0][:8], "message": parts[1], "date": parts[2]})
    return commits


def categorize(message):
    msg_lower = message.lower().strip()
    # Extract prefix before first colon or space-delimited keyword
    prefix = msg_lower.split(":")[0].split("(")[0].strip() if ":" in msg_lower else msg_lower.split()[0] if msg_lower else ""

    added_kw = ("feat", "add", "new", "feature", "introduce")
    fixed_kw = ("fix", "bugfix", "patch", "bug", "resolve", "hotfix")
    removed_kw = ("remove", "delete", "revert", "drop", "deprecate")
    changed_kw = ("change", "refactor", "update", "chore", "style", "perf", "ci", "build", "docs", "test", "improve", "modify")

    for kw in added_kw:
        if prefix.startswith(kw) or kw in prefix:
            return "Added"
    for kw in fixed_kw:
        if prefix.startswith(kw) or kw in prefix:
            return "Fixed"
    for kw in removed_kw:
        if prefix.startswith(kw) or kw in prefix:
            return "Removed"
    for kw in changed_kw:
        if prefix.startswith(kw) or kw in prefix:
            return "Changed"

    # Fallback heuristics on full message
    if any(w in msg_lower for w in ("fix", "bug", "patch", "resolve")):
        return "Fixed"
    if any(w in msg_lower for w in ("add", "new", "feat", "introduce")):
        return "Added"
    if any(w in msg_lower for w in ("remove", "delete", "drop", "revert")):
        return "Removed"
    return "Changed"


def generate_changelog(output_file="CHANGELOG.md"):
    baseline = get_last_tag()
    if baseline is None:
        print("ERROR: Could not determine baseline (no tags, no commits)", file=sys.stderr)
        sys.exit(1)

    commits = get_commits_since(baseline)
    if not commits:
        print(f"No commits found since {baseline}")
        # Write minimal changelog
        with open(output_file, "w") as f:
            f.write("# Changelog\n\nNo changes recorded yet.\n")
        return

    categories = {"Added": [], "Fixed": [], "Changed": [], "Removed": []}
    for c in commits:
        cat = categorize(c["message"])
        categories[cat].append(c)

    today = datetime.utcnow().strftime("%Y-%m-%d")
    lines = [
        "# Changelog",
        "",
        "All notable changes to this project will be documented in this file.",
        "The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).",
        "",
        f"## [Unreleased] - {today}",
        "",
    ]

    for cat_name in ("Added", "Fixed", "Changed", "Removed"):
        items = categories[cat_name]
        if items:
            lines.append(f"### {cat_name}")
            for item in items:
                lines.append(f"- {item['message']} ({item['hash']})")
            lines.append("")

    content = "\n".join(lines)
    with open(output_file, "w") as f:
        f.write(content)
    print(f"CHANGELOG written to {output_file} ({len(commits)} commits categorized)")


if __name__ == "__main__":
    output = sys.argv[1] if len(sys.argv) > 1 else "CHANGELOG.md"
    generate_changelog(output)

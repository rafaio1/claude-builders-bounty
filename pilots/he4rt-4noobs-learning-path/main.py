"""
HE4RT 4NOOBS Learning Path MVP
Generates a structured learning path index from He4rt/4noobs repos.
Zero-capital: uses GitHub API + stdlib only.
"""
import json
import os
import urllib.request
import urllib.error
from datetime import datetime, timezone

REPOS_INDEX = [
    "He4rt/4noobs",
    "He4rt/python4noobs",
    "He4rt/javascript4noobs",
    "He4rt/react4noobs",
    "He4rt/nodejs4noobs",
    "He4rt/git4noobs",
]

OUTPUT_FILE = "learning_path_index.json"


def fetch_repo_metadata(repo: str) -> dict | None:
    url = f"https://api.github.com/repos/{repo}"
    req = urllib.request.Request(url, headers={"User-Agent": "He4rt-LearningPath-Bot/1.0"})
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())
            return {
                "repo": repo,
                "description": data.get("description", ""),
                "stars": data.get("stargazers_count", 0),
                "language": data.get("language"),
                "updated_at": data.get("updated_at"),
                "url": data.get("html_url"),
            }
    except urllib.error.HTTPError as e:
        print(f"[WARN] Failed to fetch {repo}: {e.code}")
        return None


def build_learning_path(repos: list[str]) -> list[dict]:
    path = []
    for repo in repos:
        meta = fetch_repo_metadata(repo)
        if meta:
            path.append(meta)
    # Sort by stars desc as proxy for relevance/maturity
    path.sort(key=lambda x: x["stars"], reverse=True)
    return path


def main():
    print(f"[{datetime.now(timezone.utc).isoformat()}] Building He4rt 4noobs Learning Path...")
    path = build_learning_path(REPOS_INDEX)

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "github.com/He4rt",
        "total_modules": len(path),
        "modules": path,
    }

    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"[OK] Index generated: {len(path)} modules -> {OUTPUT_FILE}")
    for m in path[:5]:
        print(f"  ★ {m['stars']:>5} | {m['repo']:<30} | {m['language'] or 'N/A'}")


if __name__ == "__main__":
    main()

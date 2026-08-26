#!/usr/bin/env python3
"""Python Algorithms Library Indexer - TIER0 MVP
Indexa algoritmos do TheAlgorithms/Python via GitHub API (tree recursive).
Zero-capital: stdlib only, sem custos.
"""
import json
import urllib.request
import datetime
import sys

REPO = "TheAlgorithms/Python"
TREE_URL = f"https://api.github.com/repos/{REPO}/git/trees/master?recursive=1"
OUTPUT = "output.json"

def fetch_tree():
    req = urllib.request.Request(TREE_URL, headers={
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "python-algorithms-indexer/1.0"
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"ERROR fetching tree: {e}", file=sys.stderr)
        return None

def index_algorithms(tree_data):
    categories = {}
    total = 0
    for item in tree_data.get("tree", []):
        path = item.get("path", "")
        if item.get("type") != "blob" or not path.endswith(".py"):
            continue
        parts = path.split("/")
        if len(parts) < 2:
            continue
        # Ignorar arquivos de teste, config, etc na raiz
        if parts[0] in ("tests", "test", ".github", "scripts", "docs", "project_euler"):
            continue
        cat = parts[0]
        name = parts[-1].replace(".py", "")
        url = f"https://github.com/{REPO}/blob/master/{path}"
        
        if cat not in categories:
            categories[cat] = []
        categories[cat].append({
            "name": name,
            "path": path,
            "url": url
        })
        total += 1
    
    return categories, total

def main():
    print(f"Fetching {REPO} tree...")
    data = fetch_tree()
    if not data:
        result = {"status": "ERROR", "message": "Failed to fetch repo tree", "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()}
    else:
        cats, total = index_algorithms(data)
        result = {
            "status": "OK",
            "source": REPO,
            "total_algorithms": total,
            "total_categories": len(cats),
            "categories": {k: v for k, v in sorted(cats.items())},
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }
        print(f"Indexed {total} algorithms in {len(cats)} categories.")
    
    with open(OUTPUT, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"Wrote {OUTPUT}")

if __name__ == "__main__":
    main()

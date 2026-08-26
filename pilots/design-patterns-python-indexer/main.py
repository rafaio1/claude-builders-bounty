#!/usr/bin/env python3
"""Design Patterns Python Indexer - TIER0 MVP
Indexa padrões de projeto do refactoringguru/design-patterns-python via GitHub API.
Zero-capital: stdlib only, sem custos.
"""
import json
import urllib.request
import re
import datetime
import sys

REPO = "refactoringguru/design-patterns-python"
BRANCH = "main"
TREE_URL = f"https://api.github.com/repos/{REPO}/git/trees/{BRANCH}?recursive=1"
OUTPUT = "output.json"
UA = "design-patterns-python-indexer/1.0"

def fetch_tree():
    req = urllib.request.Request(TREE_URL, headers={
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": UA
    })
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8")).get("tree", [])
    except Exception as e:
        print(f"ERROR fetching tree: {e}", file=sys.stderr)
        return None

def extract_pattern_info(path):
    """Extrai nome do padrão e categoria do path.
    Ex: src/creational/factory_method/main.py -> (factory_method, creational)
    """
    parts = path.split("/")
    if len(parts) >= 3 and parts[0] == "src":
        category = parts[1]
        pattern = parts[2]
        return pattern, category
    return None, None

def format_name(name):
    """factory_method -> Factory Method"""
    return name.replace("_", " ").title()

def main():
    print(f"Fetching tree for {REPO}@{BRANCH}...")
    tree = fetch_tree()
    if tree is None:
        # Fallback para master se main falhar
        global BRANCH, TREE_URL
        BRANCH = "master"
        TREE_URL = f"https://api.github.com/repos/{REPO}/git/trees/{BRANCH}?recursive=1"
        print(f"Retrying with branch {BRANCH}...")
        tree = fetch_tree()
        if tree is None:
            result = {"status": "ERROR", "message": "Failed to fetch tree",
                      "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()}
            with open(OUTPUT, "w") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            sys.exit(1)

    # Filtrar arquivos Python no diretório src/
    py_files = [
        item["path"] for item in tree
        if item.get("type") == "blob"
        and item["path"].startswith("src/")
        and item["path"].endswith(".py")
    ]

    print(f"Found {len(py_files)} Python files.")

    patterns = {}
    categories = {}
    all_items = []

    for fpath in py_files:
        pattern, category = extract_pattern_info(fpath)
        if not pattern or not category:
            continue

        key = f"{category}/{pattern}"
        if key not in patterns:
            patterns[key] = {
                "name": format_name(pattern),
                "category": category,
                "files": [],
                "url": f"https://github.com/{REPO}/tree/{BRANCH}/src/{category}/{pattern}"
            }
        patterns[key]["files"].append(fpath)

        if category not in categories:
            categories[category] = set()
        categories[category].add(pattern)

    # Construir output estruturado
    for key, info in sorted(patterns.items()):
        all_items.append({
            "name": info["name"],
            "category": info["category"],
            "file_count": len(info["files"]),
            "url": info["url"]
        })

    cat_summary = {k: len(v) for k, v in categories.items()}

    result = {
        "status": "OK",
        "source": REPO,
        "branch": BRANCH,
        "total_patterns": len(patterns),
        "total_categories": len(categories),
        "total_files": len(py_files),
        "categories": dict(sorted(cat_summary.items())),
        "patterns": all_items,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "notes": "Indexação via Tree API. Padrões extraídos de src/{category}/{pattern}/*.py"
    }

    with open(OUTPUT, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"\nDone: {len(patterns)} patterns in {len(categories)} categories.")
    print(f"Total Python files: {len(py_files)}")
    print(f"Wrote {OUTPUT}")

if __name__ == "__main__":
    main()

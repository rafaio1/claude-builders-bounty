#!/usr/bin/env python3
"""DevOps Roadmap Indexer - TIER0 MVP (v4)
Indexa roadmaps do kamranahmedse/developer-roadmap via Tree API only.
Estratégia zero-capital: extrai metadados dos paths, sem fetch individual de 10k arquivos.
"""
import json
import urllib.request
import re
import datetime
import sys

REPO = "nilbuild/developer-roadmap"
BRANCH = "master"
TREE_URL = f"https://api.github.com/repos/{REPO}/git/trees/{BRANCH}?recursive=1"
OUTPUT = "output.json"
UA = "devops-roadmap-indexer/4.0"

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

def extract_roadmap_id(path):
    m = re.match(r'roadmaps/([^/]+)/content/', path)
    return m.group(1) if m else None

def topic_name_from_path(path):
    """roadmaps/devops/content/docker-containers@abc123.md -> Docker Containers"""
    basename = path.split("/")[-1]
    name_part = re.sub(r'@[a-zA-Z0-9_-]+\.md$', '', basename)
    return name_part.replace("-", " ").replace("--", " - ").title()

def main():
    print(f"Fetching tree for {REPO}@{BRANCH}...")
    tree = fetch_tree()
    if tree is None:
        result = {"status": "ERROR", "message": "Failed to fetch tree",
                  "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()}
        with open(OUTPUT, "w") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        sys.exit(1)

    content_files = [
        item["path"] for item in tree
        if item.get("type") == "blob"
        and item["path"].startswith("roadmaps/")
        and "/content/" in item["path"]
        and item["path"].endswith(".md")
    ]

    print(f"Found {len(content_files)} content files.")

    roadmaps = {}
    all_topics = []

    for fpath in content_files:
        rid = extract_roadmap_id(fpath)
        if not rid:
            continue
        if rid not in roadmaps:
            roadmaps[rid] = []
        topic = {
            "name": topic_name_from_path(fpath),
            "roadmap": rid,
            "source_file": fpath,
            "url": f"https://roadmap.sh/{rid}"
        }
        roadmaps[rid].append(topic)
        all_topics.append(topic)

    roadmap_stats = {k: len(v) for k, v in roadmaps.items()}

    sample_topics = []
    for rid in sorted(roadmap_stats, key=lambda x: -roadmap_stats[x])[:5]:
        sample_topics.extend(roadmaps[rid][:3])

    result = {
        "status": "OK",
        "source": "kamranahmedse/developer-roadmap",
        "actual_repo": REPO,
        "branch": BRANCH,
        "total_topics": len(all_topics),
        "total_roadmaps": len(roadmap_stats),
        "roadmaps": dict(sorted(roadmap_stats.items(), key=lambda x: -x[1])),
        "topics_sample": sample_topics,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "notes": "Indexação via Tree API only (sem fetch individual). Tópicos extraídos de paths roadmaps/*/content/*.md."
    }

    with open(OUTPUT, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"\nDone: {len(all_topics)} topics across {len(roadmap_stats)} roadmaps.")
    print(f"Wrote {OUTPUT}")

if __name__ == "__main__":
    main()

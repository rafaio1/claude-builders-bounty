#!/usr/bin/env python3
"""DevOps Roadmap Indexer - TIER0 MVP (v2)
Indexa roadmaps do kamranahmedse/developer-roadmap.
Estrutura real: src/data/roadmaps/{id}/content/*.md (frontmatter YAML + markdown).
Zero-capital: stdlib only.
"""
import json
import urllib.request
import re
import datetime
import sys

REPO = "kamranahmedse/developer-roadmap"
BRANCH = "master"
TREE_URL = f"https://api.github.com/repos/{REPO}/git/trees/{BRANCH}?recursive=1"
OUTPUT = "output.json"
UA = "devops-roadmap-indexer/2.0"

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

def fetch_raw(path):
    url = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/{path}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        return None

def parse_frontmatter(content):
    """Extrai título e links de arquivo content/*.md com frontmatter YAML simples."""
    item = {"title": "", "links": [], "description": ""}
    
    # Frontmatter entre ---
    fm_match = re.match(r'^---\s*\n(.*?)\n---\s*\n(.*)$', content, re.DOTALL)
    if fm_match:
        fm = fm_match.group(1)
        body = fm_match.group(2)
        
        # title: "..." ou title: ...
        title_m = re.search(r'^title:\s*["\']?(.+?)["\']?\s*$', fm, re.MULTILINE)
        if title_m:
            item["title"] = title_m.group(1).strip()
        
        desc_m = re.search(r'^description:\s*["\']?(.+?)["\']?\s*$', fm, re.MULTILINE)
        if desc_m:
            item["description"] = desc_m.group(1).strip()
    else:
        body = content
    
    # Links no corpo: [text](url)
    for name, url in re.findall(r'\[([^\]]+)\]\(([^)]+)\)', body):
        if not url.startswith('#') and not url.endswith(('.png', '.jpg', '.svg', '.gif')):
            item["links"].append({"name": name.strip(), "url": url.strip()})
    
    return item

def extract_roadmap_id(path):
    """src/data/roadmaps/devops/content/topic@hash.md -> devops"""
    m = re.match(r'src/data/roadmaps/([^/]+)/content/', path)
    return m.group(1) if m else None

def main():
    print(f"Fetching tree for {REPO}@{BRANCH}...")
    tree = fetch_tree()
    if tree is None:
        result = {"status": "ERROR", "message": "Failed to fetch tree",
                  "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()}
        with open(OUTPUT, "w") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        sys.exit(1)
    
    # Filtrar content files: src/data/roadmaps/*/content/*.md
    content_files = [
        item["path"] for item in tree
        if item.get("type") == "blob"
        and item["path"].startswith("src/data/roadmaps/")
        and "/content/" in item["path"]
        and item["path"].endswith(".md")
    ]
    
    print(f"Found {len(content_files)} content files across all roadmaps.")
    
    # Agrupar por roadmap
    roadmaps = {}
    for fpath in content_files:
        rid = extract_roadmap_id(fpath)
        if rid:
            roadmaps.setdefault(rid, []).append(fpath)
    
    print(f"Discovered {len(roadmaps)} distinct roadmaps.")
    
    # Processar todos os roadmaps (zero-capital, sem rate limit agressivo)
    all_topics = []
    roadmap_stats = {}
    processed = 0
    errors = 0
    
    for rid, files in sorted(roadmaps.items()):
        topics = []
        for fpath in files:
            raw = fetch_raw(fpath)
            if raw is None:
                errors += 1
                continue
            
            item = parse_frontmatter(raw)
            if item["title"]:
                item["roadmap"] = rid
                item["source_file"] = fpath.split("/")[-1]
                topics.append(item)
            processed += 1
        
        if topics:
            roadmap_stats[rid] = len(topics)
            all_topics.extend(topics)
    
    result = {
        "status": "OK",
        "source": REPO,
        "branch": BRANCH,
        "total_topics": len(all_topics),
        "total_roadmaps": len(roadmap_stats),
        "files_processed": processed,
        "files_failed": errors,
        "roadmaps": dict(sorted(roadmap_stats.items(), key=lambda x: -x[1])),
        "topics_sample": all_topics[:5],
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "notes": "Indexação completa via Tree API. Tópicos extraídos de src/data/roadmaps/*/content/*.md com frontmatter."
    }
    
    with open(OUTPUT, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    
    print(f"\nDone: {len(all_topics)} topics across {len(roadmap_stats)} roadmaps.")
    print(f"Processed {processed} files ({errors} failures).")
    print(f"Wrote {OUTPUT}")

if __name__ == "__main__":
    main()

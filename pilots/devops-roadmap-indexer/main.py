#!/usr/bin/env python3
"""DevOps Roadmap Indexer - TIER0 MVP (v3)
Indexa roadmaps do kamranahmedse/developer-roadmap (redireciona para nilbuild/developer-roadmap).
Estrutura real: roadmaps/{id}/content/*.md com frontmatter YAML.
Zero-capital: stdlib only.
"""
import json
import urllib.request
import re
import datetime
import sys

REPO = "nilbuild/developer-roadmap"  # kamranahmedse/developer-roadmap redireciona aqui
BRANCH = "master"
TREE_URL = f"https://api.github.com/repos/{REPO}/git/trees/{BRANCH}?recursive=1"
OUTPUT = "output.json"
UA = "devops-roadmap-indexer/3.0"

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
    except Exception:
        return None

def parse_frontmatter(content):
    """Extrai título, descrição e links de content/*.md com frontmatter YAML."""
    item = {"title": "", "description": "", "links": []}
    
    fm_match = re.match(r'^---\s*\n(.*?)\n---\s*\n(.*)$', content, re.DOTALL)
    if fm_match:
        fm = fm_match.group(1)
        body = fm_match.group(2)
        
        title_m = re.search(r'^title:\s*["\']?(.+?)["\']?\s*$', fm, re.MULTILINE)
        if title_m:
            item["title"] = title_m.group(1).strip()
        
        desc_m = re.search(r'^description:\s*["\']?(.+?)["\']?\s*$', fm, re.MULTILINE)
        if desc_m:
            item["description"] = desc_m.group(1).strip()
    else:
        body = content
    
    for name, url in re.findall(r'\[([^\]]+)\]\(([^)]+)\)', body or ""):
        if not url.startswith('#') and not url.endswith(('.png', '.jpg', '.svg', '.gif')):
            item["links"].append({"name": name.strip(), "url": url.strip()})
    
    return item

def extract_roadmap_id(path):
    """roadmaps/devops/content/topic@hash.md -> devops"""
    m = re.match(r'roadmaps/([^/]+)/content/', path)
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
    
    # Filtrar: roadmaps/*/content/*.md
    content_files = [
        item["path"] for item in tree
        if item.get("type") == "blob"
        and item["path"].startswith("roadmaps/")
        and "/content/" in item["path"]
        and item["path"].endswith(".md")
    ]
    
    print(f"Found {len(content_files)} content files.")
    
    # Agrupar por roadmap
    roadmaps = {}
    for fpath in content_files:
        rid = extract_roadmap_id(fpath)
        if rid:
            roadmaps.setdefault(rid, []).append(fpath)
    
    print(f"Discovered {len(roadmaps)} distinct roadmaps.")
    
    # Amostragem estratégica: processar todos os roadmaps mas limitar arquivos por roadmap
    # para evitar timeout em rodadas únicas. Priorizar devops, backend, frontend, etc.
    priority = ["devops", "backend", "frontend", "full-stack", "python", "javascript", 
                "react", "nodejs", "docker", "kubernetes", "aws", "linux", "sql"]
    
    all_topics = []
    roadmap_stats = {}
    processed = 0
    errors = 0
    
    # Processar prioridade primeiro, depois o resto
    ordered_rids = [r for r in priority if r in roadmaps] + [r for r in sorted(roadmaps.keys()) if r not in priority]
    
    for rid in ordered_rids:
        files = roadmaps[rid]
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
        "source": "kamranahmedse/developer-roadmap",
        "actual_repo": REPO,
        "branch": BRANCH,
        "total_topics": len(all_topics),
        "total_roadmaps": len(roadmap_stats),
        "files_processed": processed,
        "files_failed": errors,
        "roadmaps": dict(sorted(roadmap_stats.items(), key=lambda x: -x[1])),
        "topics_sample": all_topics[:5],
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "notes": "Indexação completa via Tree API. Repo original redirecionado para nilbuild/developer-roadmap."
    }
    
    with open(OUTPUT, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    
    print(f"\nDone: {len(all_topics)} topics across {len(roadmap_stats)} roadmaps.")
    print(f"Processed {processed} files ({errors} failures).")
    print(f"Wrote {OUTPUT}")

if __name__ == "__main__":
    main()

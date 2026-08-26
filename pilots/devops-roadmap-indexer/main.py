#!/usr/bin/env python3
"""DevOps Roadmap Indexer - TIER0 MVP
Indexa o roadmap de DevOps do kamranahmedse/developer-roadmap via GitHub API.
Zero-capital: stdlib only, sem custos.
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
UA = "devops-roadmap-indexer/1.0"

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
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  WARN: failed {path}: {e}", file=sys.stderr)
        return None

def parse_roadmap(md, source_file=""):
    """Extrai tópicos e links de um arquivo markdown de roadmap."""
    items = []
    current_section = "General"
    
    section_re = re.compile(r'^#{1,4}\s+(.+)$')
    # Links: [Text](url) em qualquer contexto
    link_re = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')
    
    for line in md.split('\n'):
        sec = section_re.match(line)
        if sec:
            current_section = sec.group(1).strip()
            continue
        
        for name, url in link_re.findall(line):
            # Filtrar links internos (anchors) e imagens
            if url.startswith('#') or url.endswith('.png') or url.endswith('.jpg') or url.endswith('.svg'):
                continue
            items.append({
                "name": name.strip(),
                "url": url.strip(),
                "section": current_section,
                "source": source_file
            })
    
    return items

def main():
    print(f"Fetching tree for {REPO}@{BRANCH}...")
    tree = fetch_tree()
    if tree is None:
        result = {"status": "ERROR", "message": "Failed to fetch tree",
                  "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()}
        with open(OUTPUT, "w") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        sys.exit(1)
    
    # Buscar arquivos .md relevantes (roadmaps, guides)
    # O repo tem estrutura variada; focar em src/data/roadmaps/ ou similar
    md_files = [
        item["path"] for item in tree
        if item.get("type") == "blob"
        and item["path"].endswith(".md")
        and ("roadmap" in item["path"].lower() or "guide" in item["path"].lower() or item["path"] == "README.md")
    ]
    
    # Se não encontrar muitos, pegar todos os .md da raiz e src/data
    if len(md_files) < 5:
        md_files = [
            item["path"] for item in tree
            if item.get("type") == "blob"
            and item["path"].endswith(".md")
            and not item["path"].startswith(".github")
            and not item["path"].startswith("node_modules")
        ]
    
    print(f"Found {len(md_files)} markdown files. Parsing...")
    
    all_items = []
    sections = {}
    errors = []
    
    for fpath in sorted(md_files)[:50]:  # Limitar para evitar rate limit excessivo
        md = fetch_raw(fpath)
        if md is None:
            errors.append(fpath)
            continue
        
        items = parse_roadmap(md, source_file=fpath)
        if items:
            all_items.extend(items)
            for it in items:
                sec = it["section"]
                sections[sec] = sections.get(sec, 0) + 1
    
    result = {
        "status": "OK",
        "source": REPO,
        "branch": BRANCH,
        "total_items": len(all_items),
        "total_sections": len(sections),
        "files_processed": len(md_files) - len(errors),
        "files_failed": len(errors),
        "top_sections": dict(sorted(sections.items(), key=lambda x: -x[1])[:20]),
        "items_sample": all_items[:10],
        "errors": errors[:10],
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "notes": "Indexação de roadmaps/guides. Foco em conteúdo educacional DevOps."
    }
    
    with open(OUTPUT, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    
    print(f"\nDone: {len(all_items)} items in {len(sections)} sections.")
    print(f"Wrote {OUTPUT}")

if __name__ == "__main__":
    main()

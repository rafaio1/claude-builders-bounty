#!/usr/bin/env python3
"""System Design Primer Indexer - TIER0 MVP
Indexa tópicos e recursos do donnemartin/system-design-primer via GitHub API tree.
Zero-capital: stdlib only, sem custos.
"""
import json
import urllib.request
import datetime
import sys
import re

REPO = "donnemartin/system-design-primer"
TREE_URL = f"https://api.github.com/repos/{REPO}/git/trees/master?recursive=1"
README_URL = f"https://api.github.com/repos/{REPO}/readme"
OUTPUT = "output.json"

def fetch_json(url):
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "system-design-primer-indexer/1.0"
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"ERROR fetching {url}: {e}", file=sys.stderr)
        return None

def fetch_raw(url):
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github.v3.raw",
        "User-Agent": "system-design-primer-indexer/1.0"
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8")
    except Exception as e:
        print(f"ERROR fetching raw {url}: {e}", file=sys.stderr)
        return None

def index_repo_tree(tree_data):
    """Indexa arquivos .md e imagens do repositório."""
    resources = []
    for item in tree_data.get("tree", []):
        path = item.get("path", "")
        if item.get("type") != "blob":
            continue
        # Focar em conteúdo educacional (markdown)
        if not path.endswith(".md"):
            continue
        # Ignorar traduções para manter escopo principal
        if path.startswith("solutions/") or "node_modules" in path:
            continue
        
        name = path.split("/")[-1].replace(".md", "")
        url = f"https://github.com/{REPO}/blob/master/{path}"
        
        resources.append({
            "name": name,
            "path": path,
            "url": url,
            "type": "document"
        })
    return resources

def parse_readme_topics(md):
    """Extrai tópicos principais do README como índice de navegação."""
    topics = []
    # Padrão: ## Topic Name ou ### Subtopic
    section_re = re.compile(r'^#{2,3}\s+(.+)$', re.MULTILINE)
    link_re = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')
    
    lines = md.split('\n')
    current_topic = None
    
    for line in lines:
        sec_match = section_re.match(line)
        if sec_match:
            current_topic = sec_match.group(1).strip()
            continue
        
        # Extrair links dentro de seções relevantes
        if current_topic and ('study' in current_topic.lower() or 'design' in current_topic.lower() or 'guide' in current_topic.lower()):
            for match in link_re.finditer(line):
                name, url = match.groups()
                if url.startswith('http') or url.startswith('#'):
                    topics.append({
                        "topic": current_topic,
                        "name": name.strip(),
                        "url": url.strip()
                    })
    
    return topics

def main():
    print(f"Fetching {REPO} structure...")
    
    # 1. Indexar árvore do repositório
    tree_data = fetch_json(TREE_URL)
    docs = index_repo_tree(tree_data) if tree_data else []
    
    # 2. Extrair tópicos do README
    readme_md = fetch_raw(README_URL)
    topics = parse_readme_topics(readme_md) if readme_md else []
    
    result = {
        "status": "OK",
        "source": REPO,
        "total_documents": len(docs),
        "total_topics_extracted": len(topics),
        "documents": docs[:50],  # Limitar output para evitar excesso
        "topics_sample": topics[:30],
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "notes": "Focado em documentos .md principais e tópicos de estudo do README."
    }
    
    with open(OUTPUT, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    
    print(f"Indexed {len(docs)} documents and {len(topics)} topic links.")
    print(f"Wrote {OUTPUT}")

if __name__ == "__main__":
    main()

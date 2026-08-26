#!/usr/bin/env python3
"""Free Programming Books Indexer - TIER0 MVP
Indexa livros gratuitos do EbookFoundation/free-programming-books via GitHub API.
Zero-capital: stdlib only, sem custos.
"""
import json
import urllib.request
import re
import datetime
import sys

REPO = "EbookFoundation/free-programming-books"
README_URL = f"https://api.github.com/repos/{REPO}/readme"
OUTPUT = "output.json"

def fetch_readme():
    req = urllib.request.Request(README_URL, headers={
        "Accept": "application/vnd.github.v3.raw",
        "User-Agent": "free-programming-books-indexer/1.0"
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8")
    except Exception as e:
        print(f"ERROR fetching README: {e}", file=sys.stderr)
        return None

def parse_books(md):
    """Extrai livros por idioma/categoria do README principal."""
    categories = {}
    current_cat = None
    items_buffer = []
    
    # O README usa ## para idiomas/categorias principais
    section_re = re.compile(r'^#{2}\s+(.+)$')
    # Links de livro: * [Title](url) ou - [Title](url)
    item_re = re.compile(r'^\s*[-*]\s+\[([^\]]+)\]\(([^)]+)\)')
    
    for line in md.split('\n'):
        sec_match = section_re.match(line)
        if sec_match:
            if items_buffer and current_cat:
                categories[current_cat] = items_buffer
            current_cat = sec_match.group(1).strip()
            items_buffer = []
            continue
        
        item_match = item_re.match(line)
        if item_match and current_cat:
            name, url = item_match.groups()
            items_buffer.append({
                "name": name.strip(),
                "url": url.strip()
            })
    
    if items_buffer and current_cat:
        categories[current_cat] = items_buffer
    
    return categories

def main():
    print(f"Fetching {REPO} README...")
    md = fetch_readme()
    if not md:
        result = {"status": "ERROR", "message": "Failed to fetch README", "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()}
    else:
        cats = parse_books(md)
        total = sum(len(v) for v in cats.values())
        result = {
            "status": "OK",
            "source": REPO,
            "total_books": total,
            "total_categories": len(cats),
            "categories": cats,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "notes": "Indexação do README principal. Livros detalhados por idioma em arquivos separados no repo."
        }
        print(f"Indexed {total} books in {len(cats)} categories.")
    
    with open(OUTPUT, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"Wrote {OUTPUT}")

if __name__ == "__main__":
    main()

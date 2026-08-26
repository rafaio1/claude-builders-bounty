#!/usr/bin/env python3
"""Free Programming Books Indexer - TIER0 MVP (v2)
Indexa livros gratuitos do EbookFoundation/free-programming-books.
Versão corrigida: busca arquivos books/*.md na branch 'main' via Tree API.
Zero-capital: stdlib only, sem custos.
"""
import json
import urllib.request
import re
import datetime
import sys
import base64

REPO = "EbookFoundation/free-programming-books"
BRANCH = "main"
TREE_URL = f"https://api.github.com/repos/{REPO}/git/trees/{BRANCH}?recursive=1"
OUTPUT = "output.json"
UA = "free-programming-books-indexer/2.0"

def fetch_tree():
    """Busca árvore recursiva do repositório na branch main."""
    req = urllib.request.Request(TREE_URL, headers={
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": UA
    })
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("tree", [])
    except Exception as e:
        print(f"ERROR fetching tree: {e}", file=sys.stderr)
        return None

def fetch_file_raw(path):
    """Busca conteúdo raw de um arquivo específico."""
    url = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/{path}"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  WARN: failed to fetch {path}: {e}", file=sys.stderr)
        return None

def parse_books_from_md(md, lang_hint=""):
    """Extrai livros de um arquivo markdown individual."""
    books = []
    current_section = lang_hint or "Uncategorized"
    
    # Headers de categoria: ### Category ou ## Category
    section_re = re.compile(r'^#{2,3}\s+(.+)$')
    # Links de livro: * [Title](url) ou - [Title](url)
    item_re = re.compile(r'^\s*[-*]\s+\[([^\]]+)\]\(([^)]+)\)')
    
    for line in md.split('\n'):
        sec_match = section_re.match(line)
        if sec_match:
            current_section = sec_match.group(1).strip()
            continue
        
        item_match = item_re.match(line)
        if item_match:
            name, url = item_match.groups()
            books.append({
                "name": name.strip(),
                "url": url.strip(),
                "section": current_section
            })
    
    return books

def extract_lang_from_path(path):
    """Extrai código de idioma do nome do arquivo: free-programming-books-pt.md -> pt"""
    m = re.search(r'free-programming-books-([a-z]{2}(?:-[A-Z]{2})?)\.md$', path)
    if m:
        return m.group(1)
    return "en"

def main():
    print(f"Fetching tree for {REPO}@{BRANCH}...")
    tree = fetch_tree()
    if tree is None:
        result = {
            "status": "ERROR",
            "message": "Failed to fetch repository tree",
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }
        with open(OUTPUT, "w") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        sys.exit(1)
    
    # Filtrar apenas arquivos books/*.md
    book_files = [
        item["path"] for item in tree
        if item.get("type") == "blob"
        and item["path"].startswith("books/")
        and item["path"].endswith(".md")
        and "free-programming-books" in item["path"]
    ]
    
    print(f"Found {len(book_files)} book files. Parsing...")
    
    all_books_by_lang = {}
    total_books = 0
    errors = []
    
    for fpath in sorted(book_files):
        lang = extract_lang_from_path(fpath)
        md = fetch_file_raw(fpath)
        if md is None:
            errors.append(fpath)
            continue
        
        books = parse_books_from_md(md, lang_hint=lang)
        if books:
            if lang not in all_books_by_lang:
                all_books_by_lang[lang] = []
            all_books_by_lang[lang].extend(books)
            total_books += len(books)
            print(f"  {fpath}: {len(books)} books ({lang})")
    
    result = {
        "status": "OK",
        "source": REPO,
        "branch": BRANCH,
        "total_books": total_books,
        "total_languages": len(all_books_by_lang),
        "files_processed": len(book_files) - len(errors),
        "files_failed": len(errors),
        "languages": {k: len(v) for k, v in all_books_by_lang.items()},
        "books_by_language": all_books_by_lang,
        "errors": errors,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "notes": "Indexação completa via Tree API (branch main). Livros extraídos de books/free-programming-books-*.md"
    }
    
    with open(OUTPUT, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    
    print(f"\nDone: {total_books} books in {len(all_books_by_lang)} languages.")
    print(f"Wrote {OUTPUT}")

if __name__ == "__main__":
    main()

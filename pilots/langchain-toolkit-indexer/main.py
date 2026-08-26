"""
Awesome-LangChain Indexer MVP
Zero-capital: parses curated list from kyrolabs/awesome-langchain.
Handles mixed formats: '- [Name](url) - Desc', '- [Name](url): Desc', etc.
"""
import json
import re
import urllib.request
from datetime import datetime, timezone

SOURCE_URL = "https://raw.githubusercontent.com/kyrolabs/awesome-langchain/main/README.md"
OUTPUT_FILE = "toolkit_index.json"


def fetch_readme() -> str:
    req = urllib.request.Request(SOURCE_URL, headers={"User-Agent": "LangChain-Indexer/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def parse_entries(text: str) -> list[dict]:
    """Extract entries with flexible format matching."""
    # Match: - [Name](url) followed by optional separator and description
    pattern = r'^-\s+\[([^\]]+)\]\(([^)]+)\)\s*[:\-]?\s*(.*)$'
    entries = []
    current_category = "Uncategorized"
    
    for line in text.splitlines():
        line = line.strip()
        # Detect category headers
        cat_match = re.match(r'^#{2,3}\s+(.+)', line)
        if cat_match:
            current_category = cat_match.group(1).strip()
            continue
        
        m = re.match(pattern, line)
        if m:
            name, url, desc = m.groups()
            # Clean description: remove badge images and trailing whitespace
            desc = re.sub(r'!\[.*?\]\(.*?\)', '', desc).strip()
            desc = desc.rstrip(':').strip()
            
            entries.append({
                "name": name.strip(),
                "url": url.strip(),
                "description": desc if desc else "",
                "category": current_category,
            })
    return entries


def main():
    print(f"[{datetime.now(timezone.utc).isoformat()}] Awesome-LangChain Indexer MVP")
    print("=" * 60)

    print("\n[1] Fetching README...")
    text = fetch_readme()
    print(f"    Fetched {len(text)} chars")

    print("\n[2] Parsing entries...")
    entries = parse_entries(text)
    print(f"    Parsed {len(entries)} entries")

    categories = {}
    for e in entries:
        categories[e["category"]] = categories.get(e["category"], 0) + 1

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": SOURCE_URL,
        "total_entries": len(entries),
        "total_categories": len(categories),
        "categories_summary": dict(sorted(categories.items(), key=lambda x: -x[1])[:15]),
        "entries": entries,
        "wrapper_status": "FUNCTIONAL_MVP",
    }

    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n[OK] Index saved to {OUTPUT_FILE}")
    print(f"    Top categories:")
    for cat, count in list(categories.items())[:8]:
        print(f"      • {cat}: {count}")


if __name__ == "__main__":
    main()

"""
Awesome-Selfhosted Indexer MVP
Zero-capital: parses public README from awesome-selfhosted/awesome-selfhosted.
Produces structured JSON index of self-hosted software alternatives.
"""
import json
import re
import urllib.request
from datetime import datetime, timezone

SOURCE_URL = "https://raw.githubusercontent.com/awesome-selfhosted/awesome-selfhosted/master/README.md"
OUTPUT_FILE = "selfhosted_index.json"


def fetch_readme() -> str:
    req = urllib.request.Request(SOURCE_URL, headers={"User-Agent": "SelfHosted-Indexer/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def parse_entries(text: str) -> list[dict]:
    """Extract entries matching '- [Name](url) - Description' pattern."""
    pattern = r'^- \[([^\]]+)\]\(([^)]+)\)\s*-\s*(.+)$'
    entries = []
    current_category = "Uncategorized"
    for line in text.splitlines():
        # Detect category headers like '### Analytics' or '## Software'
        cat_match = re.match(r'^#{2,3}\s+(.+)', line)
        if cat_match:
            current_category = cat_match.group(1).strip()
            continue
        m = re.match(pattern, line)
        if m:
            name, url, desc = m.groups()
            entries.append({
                "name": name.strip(),
                "url": url.strip(),
                "description": desc.strip(),
                "category": current_category,
            })
    return entries


def main():
    print(f"[{datetime.now(timezone.utc).isoformat()}] Awesome-Selfhosted Indexer MVP")
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
        "categories_summary": dict(sorted(categories.items(), key=lambda x: -x[1])[:20]),
        "entries": entries,
        "wrapper_status": "FUNCTIONAL_MVP",
    }

    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n[OK] Index saved to {OUTPUT_FILE}")
    print(f"    Top categories:")
    for cat, count in list(categories.items())[:5]:
        print(f"      • {cat}: {count}")


if __name__ == "__main__":
    main()

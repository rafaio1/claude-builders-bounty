"""
Public APIs Collective Indexer MVP
Zero-capital: indexes categorized free APIs from public-apis/public-apis repo.
Demonstrates large markdown-table parsing pattern for API directories.
"""
import json
import urllib.request
import urllib.error
import re
from datetime import datetime, timezone

README_URL = "https://raw.githubusercontent.com/public-apis/public-apis/master/README.md"
OUTPUT_FILE = "apis_index.json"


def fetch_readme() -> str:
    """Fetch the main README containing all API entries."""
    req = urllib.request.Request(
        README_URL,
        headers={"User-Agent": "PublicAPIs-Bot/1.0"}
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.read().decode("utf-8")
    except Exception as e:
        print(f"[ERROR] Failed to fetch README: {type(e).__name__}: {e}")
        return ""


def parse_apis(content: str) -> list[dict]:
    """Parse API entries from markdown tables in the README."""
    apis = []
    current_category = "Uncategorized"
    
    for line in content.split("\n"):
        # Detect category headers (### Category or ## Category)
        header_match = re.match(r'^#{2,3}\s+(.+)$', line.strip())
        if header_match:
            cat = header_match.group(1).strip()
            # Skip non-category headers
            if cat.lower() not in ('index', 'table of contents', 'contributing', 'license'):
                current_category = cat
            continue
        
        # Parse table rows: | Name | Description | Auth | HTTPS | CORS |
        if line.startswith("|") and "---" not in line and "Name" not in line:
            cols = [c.strip() for c in line.split("|")]
            # Filter empty cols from split
            cols = [c for c in cols if c]
            
            if len(cols) >= 2:
                name = cols[0].strip()
                desc = cols[1].strip() if len(cols) > 1 else ""
                auth = cols[2].strip() if len(cols) > 2 else ""
                https = cols[3].strip() if len(cols) > 3 else ""
                
                # Extract URL from markdown link [Name](url)
                url_match = re.match(r'\[([^\]]+)\]\(([^)]+)\)', name)
                api_url = url_match.group(2) if url_match else ""
                api_name = url_match.group(1) if url_match else name
                
                if api_name and api_name != "---":
                    apis.append({
                        "name": api_name,
                        "description": desc[:200],
                        "category": current_category,
                        "auth": auth,
                        "https": https,
                        "url": api_url,
                    })
    
    return apis


def main():
    print(f"[{datetime.now(timezone.utc).isoformat()}] Public APIs Collective Indexer MVP")
    print("=" * 60)

    print("\n[1] Fetching public-apis README...")
    content = fetch_readme()
    
    if not content:
        print("    [WARN] Could not fetch README. Graceful degradation.")
        output = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "github.com/public-apis/public-apis",
            "total_apis": 0,
            "categories": {},
            "apis": [],
            "wrapper_status": "FUNCTIONAL_MVP_DEGRADED",
        }
    else:
        print(f"    Fetched {len(content)} bytes")
        
        print("\n[2] Parsing API entries...")
        apis = parse_apis(content)
        print(f"    Parsed {len(apis)} API entries")
        
        # Count by category
        categories = {}
        for api in apis:
            cat = api["category"]
            categories[cat] = categories.get(cat, 0) + 1
        
        print(f"    Across {len(categories)} categories")
        
        output = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "github.com/public-apis/public-apis",
            "total_apis": len(apis),
            "total_categories": len(categories),
            "categories": dict(sorted(categories.items(), key=lambda x: -x[1])),
            "apis": apis,
            "wrapper_status": "FUNCTIONAL_MVP",
        }

    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n[OK] Index saved to {OUTPUT_FILE}")
    
    if output.get("apis"):
        print(f"\n  Top categories:")
        for cat, count in list(output["categories"].items())[:5]:
            print(f"    • {cat}: {count} APIs")
        print(f"\n  Sample entries:")
        for api in output["apis"][:5]:
            print(f"    • {api['name']} [{api['category']}] — {api['description'][:60]}")
    else:
        print("\n[NOTE] No APIs parsed. README structure may have changed.")


if __name__ == "__main__":
    main()

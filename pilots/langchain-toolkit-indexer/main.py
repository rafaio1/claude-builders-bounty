"""
LangChain Community Toolkit Indexer MVP
Zero-capital: indexes tools/integrations from langchain-ai/langchain repo.
Uses GitHub Search API as primary source (rate-limit friendly).
"""
import json
import urllib.request
import urllib.error
from datetime import datetime, timezone

SEARCH_URL = "https://api.github.com/search/code?q=repo:langchain-ai/langchain+path:libs/community/langchain_community/tools+filename:__init__.py&per_page=100"
OUTPUT_FILE = "toolkit_index.json"


def fetch_tools_search() -> list[dict]:
    """Use code search to discover tool modules."""
    req = urllib.request.Request(
        SEARCH_URL,
        headers={"User-Agent": "LangChain-Toolkit-Indexer/1.0", "Accept": "application/vnd.github.v3+json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode())
            items = data.get("items", [])
            seen = set()
            dirs = []
            for item in items:
                path = item.get("path", "")
                parts = path.split("/")
                if len(parts) >= 5:
                    tool_name = parts[-2]
                    if tool_name not in seen and not tool_name.startswith("_"):
                        seen.add(tool_name)
                        dirs.append({
                            "name": tool_name,
                            "path": "/".join(parts[:-1]),
                            "url": item.get("html_url", ""),
                        })
            return dirs
    except Exception as e:
        print(f"    [WARN] Search API failed: {e}")
    return []


def main():
    print(f"[{datetime.now(timezone.utc).isoformat()}] LangChain Community Toolkit Indexer MVP")
    print("=" * 60)

    print("\n[1] Discovering tool modules via GitHub Search...")
    tools = fetch_tools_search()
    print(f"    Found {len(tools)} tool modules")

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": SEARCH_URL,
        "total_tools": len(tools),
        "tools": tools,
        "wrapper_status": "FUNCTIONAL_MVP" if tools else "FUNCTIONAL_MVP_DEGRADED",
    }

    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n[OK] Index saved to {OUTPUT_FILE}")
    if tools:
        print(f"    Sample tools:")
        for t in tools[:10]:
            print(f"      • {t['name']}")
    else:
        print("    [NOTE] No tools found. Rate limit may apply.")


if __name__ == "__main__":
    main()

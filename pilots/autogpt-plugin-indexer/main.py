"""
AutoGPT Plugin/Tool Registry Indexer MVP
Zero-capital: indexes public plugins from Significant-Gravitas/AutoGPT repo.
Demonstrates agent plugin ecosystem discovery pattern.
"""
import json
import urllib.request
import urllib.error
from datetime import datetime, timezone

# AutoGPT classic plugins lived in classic/original_autogpt/plugins; 
# newer versions use forge/sdk. Try multiple known paths.
PLUGIN_PATHS = [
    "https://api.github.com/repos/Significant-Gravitas/AutoGPT/contents/classic/original_autogpt/plugins",
    "https://api.github.com/repos/Significant-Gravitas/AutoGPT/contents/forge/plugins",
    "https://api.github.com/repos/Significant-Gravitas/AutoGPT/contents/docs/content/server/new_blocks",
]
OUTPUT_FILE = "plugins_index.json"


def fetch_path(url: str) -> list[dict]:
    """Fetch contents of a GitHub API path."""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "AutoGPT-Plugin-Bot/1.0", "Accept": "application/vnd.github.v3+json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            if isinstance(data, list):
                return data
            return []
    except urllib.error.HTTPError as e:
        return []
    except Exception:
        return []


def discover_plugins() -> tuple[str, list[dict]]:
    """Try known plugin paths and return the first one that has content."""
    for path_url in PLUGIN_PATHS:
        items = fetch_path(path_url)
        if items:
            return path_url, items
    return "", []


def build_plugin_index(source_url: str, items: list[dict]) -> list[dict]:
    """Build structured index from plugin directory contents."""
    index = []
    for item in items:
        name = item.get("name", "unknown")
        item_type = item.get("type", "unknown")
        index.append({
            "name": name,
            "type": item_type,
            "path": item.get("path", ""),
            "url": item.get("html_url", ""),
            "sha": item.get("sha", "")[:8],
            "size_bytes": item.get("size", 0),
        })
    return index


def main():
    print(f"[{datetime.now(timezone.utc).isoformat()}] AutoGPT Plugin Registry Indexer MVP")
    print("=" * 60)

    print("\n[1] Discovering plugin registry path...")
    source_url, items = discover_plugins()
    
    if not source_url:
        print("    [WARN] No plugin directory found at known paths.")
        print("    Graceful degradation: generating empty index.")
        output = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "github.com/Significant-Gravitas/AutoGPT",
            "source_path_tried": PLUGIN_PATHS,
            "total_plugins": 0,
            "plugins": [],
            "wrapper_status": "FUNCTIONAL_MVP_DEGRADED",
            "note": "Repo structure may have changed. Update PLUGIN_PATHS when new location is identified."
        }
    else:
        print(f"    Found plugins at: {source_url}")
        print(f"    Items: {len(items)}")

        print("\n[2] Building plugin index...")
        index = build_plugin_index(source_url, items)
        print(f"    Indexed {len(index)} entries")

        output = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "source": "github.com/Significant-Gravitas/AutoGPT",
            "source_path": source_url,
            "total_plugins": len(index),
            "plugins": index,
            "wrapper_status": "FUNCTIONAL_MVP",
        }

    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n[OK] Index saved to {OUTPUT_FILE}")
    
    plugins = output.get("plugins", [])
    for p in plugins[:10]:
        print(f"  • {p['name']} ({p['type']})")

    if not plugins:
        print("\n[NOTE] No plugins indexed. Check PLUGIN_PATHS or repo structure.")


if __name__ == "__main__":
    main()

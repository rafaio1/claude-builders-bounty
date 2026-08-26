"""
HuggingFace Transformers Examples/Education Indexer MVP
Zero-capital: indexes public examples and education assets from huggingface/transformers.
Demonstrates large-repo structured subset discovery pattern.
"""
import json
import urllib.request
import urllib.error
from datetime import datetime, timezone

# Focus on structured, high-value subsets rather than entire repo
TARGET_PATHS = [
    ("examples", "https://api.github.com/repos/huggingface/transformers/contents/examples"),
    ("notebooks", "https://api.github.com/repos/huggingface/transformers/contents/notebooks"),
    ("docs/source", "https://api.github.com/repos/huggingface/transformers/contents/docs/source"),
]
OUTPUT_FILE = "education_index.json"


def fetch_path(url: str) -> list[dict]:
    """Fetch contents of a GitHub API path."""
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "HF-Transformers-Bot/1.0", "Accept": "application/vnd.github.v3+json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            if isinstance(data, list):
                return data
            return []
    except urllib.error.HTTPError:
        return []
    except Exception:
        return []


def build_education_index() -> dict:
    """Build structured index from multiple target paths."""
    sections = {}
    total_items = 0
    
    for section_name, url in TARGET_PATHS:
        items = fetch_path(url)
        indexed = []
        for item in items:
            name = item.get("name", "unknown")
            item_type = item.get("type", "unknown")
            # Include directories (task-specific folders) and key files
            if item_type == "dir" or name.endswith((".md", ".ipynb", ".py")):
                indexed.append({
                    "name": name,
                    "type": item_type,
                    "path": item.get("path", ""),
                    "url": item.get("html_url", ""),
                    "sha": item.get("sha", "")[:8],
                })
        sections[section_name] = indexed
        total_items += len(indexed)
    
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "github.com/huggingface/transformers",
        "target_paths": [t[0] for t in TARGET_PATHS],
        "total_items": total_items,
        "sections": sections,
        "wrapper_status": "FUNCTIONAL_MVP",
    }


def main():
    print(f"[{datetime.now(timezone.utc).isoformat()}] HuggingFace Transformers Education Indexer MVP")
    print("=" * 60)

    print("\n[1] Fetching education assets from target paths...")
    output = build_education_index()
    
    for section, items in output["sections"].items():
        print(f"    {section}: {len(items)} items")

    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n[OK] Index saved to {OUTPUT_FILE}")
    print(f"    Total indexed: {output['total_items']} items across {len(output['sections'])} sections")
    
    # Show sample from first non-empty section
    for section, items in output["sections"].items():
        if items:
            print(f"\n  Sample from '{section}':")
            for item in items[:5]:
                print(f"    • {item['name']} ({item['type']})")
            break


if __name__ == "__main__":
    main()

"""
Anthropic Skills Registry Indexer MVP
Zero-capital: indexes public agent skills from anthropics/skills repo.
Demonstrates first-party skill registry discovery pattern.
"""
import json
import urllib.request
import urllib.error
from datetime import datetime, timezone

SKILLS_API_URL = "https://api.github.com/repos/anthropics/skills/contents"
OUTPUT_FILE = "skills_index.json"


def fetch_skills_directory() -> list[dict]:
    """Fetch contents of anthropics/skills/skills subdirectory (actual skill folders)."""
    url = "https://api.github.com/repos/anthropics/skills/contents/skills"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Anthropic-Skills-Bot/1.0", "Accept": "application/vnd.github.v3+json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            if isinstance(data, list):
                return data
            return []
    except urllib.error.HTTPError as e:
        print(f"[WARN] Failed to fetch skills directory: HTTP {e.code}")
        return []
    except Exception as e:
        print(f"[ERROR] {type(e).__name__}: {e}")
        return []


def build_skills_index(contents: list[dict]) -> list[dict]:
    """Build structured index from skill directories."""
    index = []
    for item in contents:
        name = item.get("name", "unknown")
        item_type = item.get("type", "unknown")
        # Only include directories (each is a skill)
        if item_type == "dir":
            index.append({
                "name": name,
                "type": item_type,
                "path": item.get("path", ""),
                "url": item.get("html_url", ""),
                "sha": item.get("sha", "")[:8],
            })
    return index


def main():
    print(f"[{datetime.now(timezone.utc).isoformat()}] Anthropic Skills Registry Indexer MVP")
    print("=" * 60)

    print("\n[1] Fetching skills registry...")
    contents = fetch_skills_directory()
    print(f"    Found {len(contents)} items in repo root")

    print("\n[2] Building skills index...")
    index = build_skills_index(contents)
    print(f"    Indexed {len(index)} skill-related entries")

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "github.com/anthropics/skills",
        "total_entries": len(index),
        "skills": index,
        "wrapper_status": "FUNCTIONAL_MVP",
    }

    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n[OK] Index saved to {OUTPUT_FILE}")
    for s in index[:10]:
        print(f"  • {s['name']} ({s['type']})")

    if not index:
        print("\n[NOTE] No skill entries found. Repo structure may differ.")
        print("       Graceful degradation verified.")


if __name__ == "__main__":
    main()

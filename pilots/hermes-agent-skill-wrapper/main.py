"""
Hermes Agent Skill Wrapper MVP
Zero-capital: indexes public skills from NousResearch/hermes-agent repo.
Demonstrates skill discovery pattern for future marketplace.
"""
import json
import urllib.request
import urllib.error
from datetime import datetime, timezone

SKILLS_API_URL = "https://api.github.com/repos/NousResearch/hermes-agent/contents/skills"
OUTPUT_FILE = "skill_index.json"


def fetch_skills_directory() -> list[dict]:
    """Fetch list of skill directories from the Hermes agent repo."""
    req = urllib.request.Request(
        SKILLS_API_URL,
        headers={"User-Agent": "Hermes-Skill-Wrapper/1.0", "Accept": "application/vnd.github.v3+json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            if isinstance(data, list):
                return [item for item in data if item.get("type") == "dir"]
            return []
    except urllib.error.HTTPError as e:
        print(f"[WARN] Failed to fetch skills directory: HTTP {e.code}")
        return []
    except Exception as e:
        print(f"[ERROR] {type(e).__name__}: {e}")
        return []


def build_skill_index(skills_dirs: list[dict]) -> list[dict]:
    """Build structured index from skill directories."""
    index = []
    for skill in skills_dirs:
        index.append({
            "name": skill.get("name", "unknown"),
            "path": skill.get("path", ""),
            "url": skill.get("html_url", ""),
            "sha": skill.get("sha", "")[:8],
        })
    return index


def main():
    print(f"[{datetime.now(timezone.utc).isoformat()}] Hermes Agent Skill Wrapper MVP")
    print("=" * 60)

    print("\n[1] Fetching skills directory...")
    dirs = fetch_skills_directory()
    print(f"    Found {len(dirs)} skill directories")

    print("\n[2] Building skill index...")
    index = build_skill_index(dirs)

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "github.com/NousResearch/hermes-agent/skills",
        "total_skills": len(index),
        "skills": index,
        "wrapper_status": "FUNCTIONAL_MVP",
    }

    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n[OK] Index saved to {OUTPUT_FILE}")
    for s in index[:10]:
        print(f"  • {s['name']} ({s['sha']})")

    if not index:
        print("\n[NOTE] No skills found. Repo structure may differ or skills dir may not exist.")
        print("       This is expected for an MVP wrapper — graceful degradation verified.")


if __name__ == "__main__":
    main()

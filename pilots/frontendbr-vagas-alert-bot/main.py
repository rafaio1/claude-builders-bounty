import json
import os
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone

def fetch_issues(repo="frontendbr/vagas", limit=30):
    url = f"https://api.github.com/repos/{repo}/issues?state=open&per_page={limit}&sort=created&direction=desc"
    req = urllib.request.Request(url, headers={"User-Agent": "FrontendBR-Alert-Bot/1.0"})
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as e:
        print(f"Error fetching issues: {e.code}")
        return []

def filter_relevant(issues, keywords=None):
    # Default broad filter for frontend roles if no user profile provided yet
    if keywords is None:
        keywords = ["react", "next.js", "typescript", "vue", "angular", "frontend", "front-end"]
    
    relevant = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=2)  # Focus on fresh posts
    
    for issue in issues:
        created = datetime.strptime(issue["created_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        if created < cutoff:
            continue
            
        text = (issue.get("title", "") + " " + issue.get("body", "")).lower()
        if any(kw.lower() in text for kw in keywords):
            relevant.append({
                "title": issue["title"],
                "url": issue["html_url"],
                "labels": [l["name"] for l in issue.get("labels", [])],
                "created_at": issue["created_at"]
            })
    return relevant

def format_digest(items):
    if not items:
        return "Nenhuma vaga nova relevante encontrada nas últimas 48h."

    lines = [f"🚀 *Resumo de Vagas Frontend* ({len(items)} novas)\n"]
    for item in items[:10]:  # Cap at 10 to avoid spam
        labels = ", ".join(item["labels"]) if item["labels"] else "Sem tags"
        lines.append(f"• [{item['title']}]({item['url']})\n  _{labels}_")
    return "\n".join(lines)

if __name__ == "__main__":
    issues = fetch_issues()
    matches = filter_relevant(issues)
    digest = format_digest(matches)
    
    # Output for GitHub Actions log / potential webhook integration later
    print(digest)
    
    # Save state for deduplication in next run (simple file-based state)
    state_file = "last_seen_ids.json"
    seen_ids = set()
    if os.path.exists(state_file):
        with open(state_file) as f:
            seen_ids = set(json.load(f))
    
    new_ids = [i["url"].split("/")[-1] for i in matches]
    all_ids = list(seen_ids.union(set(new_ids)))[-500:] # Keep last 500
    
    with open(state_file, "w") as f:
        json.dump(all_ids, f)
from datetime import datetime, timedelta, timezone

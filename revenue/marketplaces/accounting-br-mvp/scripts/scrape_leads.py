#!/usr/bin/env python3
"""
ContábilHub Lead Scraper - Zero Cost Acquisition
Searches GitHub for Domínio/Contmatic integrations and extracts developer contacts.
Usage: python3 scrape_leads.py
Output: leads.json (structured list for outreach)
"""
import json
import subprocess
import re
from datetime import datetime

def search_github_repos(query, limit=10):
    """Search GitHub repos via gh cli"""
    cmd = f"gh search repos '{query}' --limit {limit} --json name,owner,url,description,stargazersCount,updatedAt"
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return json.loads(result.stdout)
    except Exception as e:
        print(f"Error searching '{query}': {e}")
    return []

def extract_email_from_repo(repo_url):
    """Try to find email in repo README or profile (best effort)"""
    # Placeholder - real implementation would use playwright-cli to scrape
    # For now, return None to indicate manual verification needed
    return None

def main():
    queries = [
        "dominio sistemas api contabilidade",
        "contmatic api integration",
        "sped contabil python",
        "nfe emissao automatica dominio",
        "escritorio contabil saas"
    ]
    
    all_leads = []
    seen_urls = set()
    
    print("🔍 Iniciando busca de leads no GitHub...")
    for q in queries:
        print(f"  → Buscando: {q}")
        repos = search_github_repos(q, limit=8)
        for r in repos:
            url = r.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                lead = {
                    "source": "github",
                    "repo_name": r.get("name"),
                    "owner": r.get("owner", {}).get("login"),
                    "url": url,
                    "description": r.get("description", ""),
                    "stars": r.get("stargazersCount", 0),
                    "updated": r.get("updatedAt", ""),
                    "contact_email": None,  # Requires manual/playwright lookup
                    "status": "prospecting",
                    "added_at": datetime.utcnow().isoformat()
                }
                all_leads.append(lead)
    
    output_path = "revenue/marketplaces/accounting-br-mvp/leads.json"
    with open(output_path, "w") as f:
        json.dump(all_leads, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ {len(all_leads)} leads salvos em {output_path}")
    print("⚠️  Emails não extraídos automaticamente - usar playwright-cli ou verificação manual")
    print("📋 Próximo passo: enriquecer com LinkedIn/email via OUTREACH_PLAN.md")

if __name__ == "__main__":
    main()

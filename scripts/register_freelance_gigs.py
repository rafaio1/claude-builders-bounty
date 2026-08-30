#!/usr/bin/env python3
"""
Register freelance gigs on platforms using GhostCLI automation.
Since we cannot directly access Workana/99Freelas APIs without credentials,
this script prepares the gig metadata and logs the registration intent.
Next step: Use playwright-cli to automate browser registration if credentials are provided.
"""
import json, os
from datetime import datetime, timezone

STATE_PATH = "/Agentic/state/freelance_pipeline.json"
PROPOSALS_DIR = "/Agentic/state/proposals"
PORTFOLIO_URL = "https://rafaio1.github.io/ghostcli-portfolio/"

def load_json(path):
    with open(path) as f:
        return json.load(f)

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def main():
    state = load_json(STATE_PATH)
    
    # Define gig listings for each platform
    gigs = [
        {
            "platform": "workana",
            "title": "Automação AI para Contabilidade e Empresas",
            "description": "Implemento agentes AI personalizados que automatizam relatórios, atendimento e processos internos. ROI garantido.",
            "price_brl": 450,
            "delivery_days": 5,
            "portfolio_url": PORTFOLIO_URL,
            "tags": ["automação", "inteligência artificial", "contabilidade", "python"],
            "status": "ready_to_register"
        },
        {
            "platform": "99freelas",
            "title": "Desenvolvimento de Agentes AI com GhostCLI",
            "description": "Crio automações inteligentes para empresas brasileiras usando tecnologia enterprise. Setup rápido e suporte incluso.",
            "price_brl": 520,
            "delivery_days": 7,
            "portfolio_url": PORTFOLIO_URL,
            "tags": ["ai", "automação", "desenvolvimento", "saas"],
            "status": "ready_to_register"
        }
    ]
    
    state["gig_listings"] = gigs
    state["registration_status"] = "metadata_prepared"
    state["next_action"] = "Use playwright-cli to register on platforms OR provide API tokens for direct submission"
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    save_json(STATE_PATH, state)
    
    print(json.dumps({
        "status": "gig_metadata_prepared",
        "gigs_count": len(gigs),
        "portfolio_live": PORTFOLIO_URL,
        "blocking_issue": "No Workana/99Freelas API credentials found in environment",
        "fallback_options": [
            "1. Provide WORKANA_API_TOKEN and FREELAS_API_TOKEN in /root/.automaton/.env",
            "2. Use playwright-cli to automate browser registration manually",
            "3. Register manually using prepared templates in state/proposals/"
        ]
    }, indent=2))

if __name__ == "__main__":
    main()

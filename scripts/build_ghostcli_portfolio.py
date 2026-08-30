#!/usr/bin/env python3
"""Build GhostCLI AI Automation Portfolio Site for Freelance Revenue"""
import json, os, subprocess, sys
from datetime import datetime, timezone

SITE_DIR = "/Agentic/site/ghostcli-portfolio"
STATE_PATH = "/Agentic/state/freelance_pipeline.json"

def log(msg):
    ts = datetime.now(timezone.utc).isoformat()
    print(f"[{ts}] {msg}", flush=True)

def main():
    os.makedirs(SITE_DIR, exist_ok=True)
    
    # Portfolio content targeting Brazilian SMBs on Workana/99Freelas
    index_html = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Automação AI para Empresas | GhostCLI Solutions</title>
    <style>
        body { font-family: system-ui; max-width: 800px; margin: 0 auto; padding: 20px; line-height: 1.6; }
        .hero { background: #0f172a; color: white; padding: 40px; border-radius: 8px; margin-bottom: 30px; }
        .service { border: 1px solid #e2e8f0; padding: 20px; margin: 15px 0; border-radius: 8px; }
        .price { color: #059669; font-weight: bold; font-size: 1.2em; }
        .cta { background: #2563eb; color: white; padding: 15px 30px; text-decoration: none; border-radius: 6px; display: inline-block; margin-top: 20px; }
    </style>
</head>
<body>
    <div class="hero">
        <h1>🤖 Automação Inteligente para sua Empresa</h1>
        <p>Economize 20-40 horas/mês com agentes AI personalizados</p>
    </div>
    
    <h2>Serviços de Automação AI</h2>
    
    <div class="service">
        <h3>📊 Automação de Relatórios Financeiros</h3>
        <p>Agentes que extraem dados do seu ERP, geram relatórios automáticos e enviam por email/Slack.</p>
        <p class="price">R$ 450 (setup único) + R$ 90/mês suporte</p>
    </div>
    
    <div class="service">
        <h3>📧 Processamento Inteligente de Emails</h3>
        <p>Classificação automática, respostas draft e roteamento para setores corretos.</p>
        <p class="price">R$ 380 (setup único) + R$ 70/mês suporte</p>
    </div>
    
    <div class="service">
        <h3>🔍 Monitoramento de Concorrência</h3>
        <p>Agentes que rastreiam preços, lançamentos e menções da concorrência 24/7.</p>
        <p class="price">R$ 520 (setup único) + R$ 120/mês suporte</p>
    </div>
    
    <div class="service">
        <h3>📋 Onboarding Automatizado de Clientes</h3>
        <p>Coleta de documentos, validação de dados e criação automática de contas.</p>
        <p class="price">R$ 650 (setup único) + R$ 150/mês suporte</p>
    </div>
    
    <h2>Como Funciona</h2>
    <ol>
        <li><strong>Diagnóstico Gratuito:</strong> Analisamos seus processos atuais</li>
        <li><strong>Proposta Personalizada:</strong> ROI estimado e timeline</li>
        <li><strong>Implementação em 3-5 dias:</strong> Setup completo + testes</li>
        <li><strong>Treinamento da Equipe:</strong> 2h de capacitação inclusa</li>
        <li><strong>Suporte Contínuo:</strong> Ajustes e melhorias mensais</li>
    </ol>
    
    <h2>Tecnologia</h2>
    <p>Utilizamos <strong>GhostCLI</strong> - plataforma enterprise de agentes AI com:</p>
    <ul>
        <li>Integração nativa com APIs brasileiras (NFe, eSocial, Domínio, Omie)</li>
        <li>Segurança bank-grade (dados nunca saem do seu ambiente)</li>
        <li>Logs auditáveis e compliance LGPD</li>
        <li>Suporte a múltiplos modelos (Claude, GPT, Llama)</li>
    </ul>
    
    <div style="text-align: center; margin-top: 40px;">
        <a href="mailto:automacao@ghostcli.solutions" class="cta">📅 Agendar Diagnóstico Gratuito</a>
        <p style="margin-top: 15px; color: #64748b;">Resposta em até 4 horas úteis</p>
    </div>
    
    <footer style="margin-top: 60px; padding-top: 20px; border-top: 1px solid #e2e8f0; color: #64748b;">
        <p>© 2026 GhostCLI Solutions • CNPJ: Em formação • São Paulo, SP</p>
    </footer>
</body>
</html>"""
    
    with open(os.path.join(SITE_DIR, "index.html"), "w") as f:
        f.write(index_html)
    
    # Create service catalog JSON for programmatic use
    catalog = {
        "services": [
            {"id": "fin_reports", "name": "Automação Relatórios Financeiros", "setup_brl": 450, "monthly_brl": 90},
            {"id": "email_proc", "name": "Processamento Emails AI", "setup_brl": 380, "monthly_brl": 70},
            {"id": "comp_monitor", "name": "Monitoramento Concorrência", "setup_brl": 520, "monthly_brl": 120},
            {"id": "client_onboard", "name": "Onboarding Clientes Auto", "setup_brl": 650, "monthly_brl": 150}
        ],
        "tech_stack": ["GhostCLI", "Claude Fable 5", "Python", "Playwright"],
        "target_markets": ["Workana", "99Freelas", "LinkedIn BR", "Indicação Direta"],
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    with open(os.path.join(SITE_DIR, "catalog.json"), "w") as f:
        json.dump(catalog, f, indent=2)
    
    # Update pipeline state
    state = {
        "portfolio_site": SITE_DIR,
        "status": "built_local",
        "next_step": "deploy_to_sites_or_vercel",
        "gig_platforms": [],
        "proposals_sent": 0,
        "revenue_brl": 0,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)
    
    log(f"Portfolio built at {SITE_DIR}")
    log("Next: Deploy via Sites connector or Vercel CLI")

if __name__ == "__main__":
    main()

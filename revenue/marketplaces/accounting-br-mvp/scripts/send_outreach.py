#!/usr/bin/env python3
"""
ContábilHub Outreach Sender
Sends personalized emails via Gmail MCP or logs drafts for manual send.
For GitHub issues, generates pre-filled URLs.
"""
import json
import subprocess
import sys
from datetime import datetime

OUTREACH_TEMPLATE = """Assunto: Convite — Liste sua ferramenta no ContábilHub (0 custo fixo)

Olá {owner},

Vi que você desenvolveu o {tool_name} com integração ao Domínio Sistemas. 
Estamos lançando o ContábilHub, um marketplace curado exclusivamente para 
micro-SaaS contábeis verificados pelo CRC/CFC.

Modelo transparente:
• 15% comissão sobre assinaturas recorrentes (split automático via Asaas/Pix)
• Sem mensalidade, sem custo de listagem, sem exclusividade
• Verificação CRC + selo de conformidade CFC 1594/2020 incluso

Seu produto se encaixa perfeitamente no perfil. Posso enviar o kit de 
integração e iniciar a verificação hoje?

Abraço,
Equipe ContábilHub
https://rafaio1.github.io/contabilhub/
"""

GITHUB_ISSUE_BODY = """## 🤝 Convite para Parceria — ContábilHub

Olá @{owner},

Vi seu repositório **{repo_name}** e acredito que ele se encaixa perfeitamente no [ContábilHub](https://rafaio1.github.io/contabilhub/), um marketplace curado de micro-SaaS para escritórios contábeis.

### Modelo
- **15% comissão** sobre assinaturas recorrentes (split automático Asaas/Pix)
- **0 custo** de listagem, mensalidade ou exclusividade
- Verificação CRC/CFC inclusa

### Por que listar?
- Visibilidade direta para contadores que usam Domínio/Contmatic
- Infraestrutura de pagamento e compliance resolvida
- Foco em ferramentas verificadas (menos ruído, mais conversão)

Se fizer sentido, responda aqui ou preencha o formulário no site para iniciarmos a verificação.

Abraço!  
Equipe ContábilHub
"""

def generate_github_issue_url(owner, repo, title, body):
    """Generate pre-filled GitHub issue URL"""
    from urllib.parse import quote
    base = f"https://github.com/{owner}/{repo}/issues/new"
    params = f"?title={quote(title)}&body={quote(body)}"
    return base + params

def main():
    with open('outreach_queue.json') as f:
        queue = json.load(f)
    
    results = []
    
    for item in queue:
        owner = item['owner']
        tool = item['tool_fit']
        
        if item['channel'] == 'email' and item.get('target'):
            # Email ready - log draft
            email_body = OUTREACH_TEMPLATE.format(owner=owner, tool_name=tool)
            result = {
                "owner": owner,
                "channel": "email",
                "target": item['target'],
                "status": "draft_ready",
                "action": "Send via Gmail MCP or copy-paste",
                "draft_preview": email_body[:200] + "...",
                "timestamp": datetime.utcnow().isoformat()
            }
            print(f"📧 EMAIL DRAFT READY: {owner} ({item['target']})")
            print(f"   Preview: {email_body[:100]}...")
            
        elif item['channel'] == 'github_issue':
            # Generate issue URL
            repo_name = tool
            title = f"Parceria: Listar {repo_name} no ContábilHub"
            body = GITHUB_ISSUE_BODY.format(owner=owner, repo_name=repo_name)
            url = generate_github_issue_url(owner, repo_name, title, body)
            
            result = {
                "owner": owner,
                "channel": "github_issue",
                "target": url,
                "status": "url_generated",
                "action": "Open URL to create issue",
                "timestamp": datetime.utcnow().isoformat()
            }
            print(f"🔗 ISSUE URL GENERATED: {owner}/{repo_name}")
            print(f"   {url[:80]}...")
        
        results.append(result)
    
    # Save actionable output
    with open('outreach_actions.json', 'w') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ {len(results)} outreach actions prepared. See outreach_actions.json")
    print("⚠️  Email sending requires Gmail MCP connection or manual action.")
    print("💡 GitHub issue URLs can be opened directly in browser.")

if __name__ == "__main__":
    main()

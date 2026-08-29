#!/usr/bin/env python3
"""
SMTP Email Sender for ContábilHub Outreach
Uses environment variables for credentials to avoid hardcoding secrets.
Falls back to logging if SMTP is not configured.
"""
import os
import smtplib
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone

def send_email(to_addr: str, subject: str, body: str) -> dict:
    smtp_host = os.environ.get("SMTP_HOST")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER")
    smtp_pass = os.environ.get("SMTP_PASS")
    
    result = {
        "to": to_addr,
        "subject": subject,
        "status": "not_sent",
        "reason": "",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    if not all([smtp_host, smtp_user, smtp_pass]):
        result["status"] = "skipped"
        result["reason"] = "SMTP credentials not configured (SMTP_HOST, SMTP_USER, SMTP_PASS)"
        print(f"⚠️  Email to {to_addr} skipped: {result['reason']}")
        return result
    
    try:
        msg = MIMEMultipart()
        msg["From"] = smtp_user
        msg["To"] = to_addr
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))
        
        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, to_addr, msg.as_string())
        
        result["status"] = "sent"
        print(f"✅ Email sent to {to_addr}")
    except Exception as e:
        result["status"] = "error"
        result["reason"] = str(e)
        print(f"❌ Failed to send to {to_addr}: {e}")
    
    return result

if __name__ == "__main__":
    # Load draft from EMAIL_DRAFT_TIAGO.md or use hardcoded fallback
    draft_file = "revenue/marketplaces/accounting-br-mvp/EMAIL_DRAFT_TIAGO.md"
    to_email = "tiagobordan@gmail.com"
    subject = "Convite — Liste sua ferramenta no ContábilHub (0 custo fixo)"
    
    # Simple extraction - in production parse markdown properly
    body = """Olá Tiago,

Vi que você desenvolveu o IntegracaoDominioThomsomReuters com integração à API Domínio Sistemas. 
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
https://rafaio1.github.io/contabilhub/"""
    
    result = send_email(to_email, subject, body)
    
    # Log result
    log_path = "revenue/marketplaces/accounting-br-mvp/email_send_log.json"
    try:
        with open(log_path) as f:
            logs = json.load(f)
    except FileNotFoundError:
        logs = []
    
    logs.append(result)
    with open(log_path, "w") as f:
        json.dump(logs, f, indent=2, ensure_ascii=False)
    
    print(f"\n📋 Log saved to {log_path}")

#!/usr/bin/env python3
"""
Gmail Client - Metodos reutilizaveis para a Gmail API v1.

Usa OAuth2 refresh token do /Agentic/.env para obter access tokens,
e oferece metodos simples: listar, buscar, ler, enviar, marcar lido,
arquivar e apagar emails.

Dependencias: requests (pip install requests)

Uso:
    from tools.gmail_client import GmailClient

    g = GmailClient()
    msgs = g.search("from:noreply@github.com newer_than:2d", max_results=10)
    for m in msgs:
        detail = g.get_message(m["id"])
        print(detail["subject"], detail["body_preview"][:200])

    g.send_message(
        to="someone@example.com",
        subject="Hello",
        body="This is a test."
    )
"""

import base64
import json
import os
import re
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

try:
    import requests
except ImportError:
    raise ImportError("requests nao instalado. Rode: pip install requests")

ROOT = Path("/Agentic")
ENV_PATH = ROOT / ".env"
TOKEN_CACHE_PATH = ROOT / ".config" / "gmail_token_cache.json"
LOG_PATH = ROOT / "logs" / "gmail_client.log"


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).isoformat()
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "a") as f:
        f.write(line + "\n")


def _load_env() -> dict:
    """Carrega variaveis do .env."""
    env = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            line = line.strip()
            if line and "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


class GmailClient:
    """Cliente reutilizavel para a Gmail API v1 com OAuth2."""

    BASE_URL = "https://gmail.googleapis.com/gmail/v1/users/me"

    def __init__(self):
        self._env = _load_env()
        self._client_id = self._env.get("GOOGLE_CLIENT_ID", "")
        self._client_secret = self._env.get("GOOGLE_CLIENT_SECRET", "")
        self._refresh_token = self._env.get("GOOGLE_REFRESH_TOKEN", "")
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0

    # ---- Token management ----

    def get_access_token(self) -> str:
        """Obtem access token via refresh token, com cache em memoria e disco."""
        if self._access_token and time.time() < self._token_expires_at - 60:
            return self._access_token

        if TOKEN_CACHE_PATH.exists():
            try:
                cached = json.loads(TOKEN_CACHE_PATH.read_text())
                if cached.get("expires_at", 0) > time.time() + 60:
                    self._access_token = cached["access_token"]
                    self._token_expires_at = cached["expires_at"]
                    return self._access_token
            except (json.JSONDecodeError, KeyError):
                pass

        if not all([self._client_id, self._client_secret, self._refresh_token]):
            raise RuntimeError("GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET ou GOOGLE_REFRESH_TOKEN ausentes no .env")

        resp = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "refresh_token": self._refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=15,
        )
        if resp.status_code != 200:
            err = resp.text[:300]
            _log(f"Token refresh falhou: {resp.status_code} {err}")
            raise RuntimeError(f"Token refresh falhou: {err}")

        data = resp.json()
        self._access_token = data["access_token"]
        self._token_expires_at = time.time() + data.get("expires_in", 3600)

        TOKEN_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_CACHE_PATH.write_text(json.dumps({
            "access_token": self._access_token,
            "expires_at": self._token_expires_at,
        }, indent=2))

        return self._access_token

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.get_access_token()}"}

    def _api(self, method: str, endpoint: str, **kwargs) -> dict:
        url = f"{self.BASE_URL}/{endpoint}"
        resp = requests.request(method, url, headers=self._headers(), timeout=30, **kwargs)
        if resp.status_code >= 400:
            _log(f"API erro {resp.status_code}: {resp.text[:300]}")
            raise RuntimeError(f"Gmail API {resp.status_code}: {resp.text[:300]}")
        return resp.json() if resp.text else {}

    # ---- Listar e buscar ----

    def list_messages(self, max_results: int = 20, page_token: Optional[str] = None) -> dict:
        """Lista mensagens recentes."""
        params = {"maxResults": max_results}
        if page_token:
            params["pageToken"] = page_token
        return self._api("GET", "messages", params=params)

    def search(self, query: str, max_results: int = 20) -> list[dict]:
        """Busca mensagens por query Gmail com paginação automática.
        Retorna lista de {id, threadId} até max_results ou esgotar."""
        messages = []
        page_token = None
        while len(messages) < max_results:
            batch_size = min(500, max_results - len(messages))
            params = {"q": query, "maxResults": batch_size}
            if page_token:
                params["pageToken"] = page_token
            result = self._api("GET", "messages", params=params)
            batch = result.get("messages", [])
            if not batch:
                break
            messages.extend(batch)
            page_token = result.get("nextPageToken")
            if not page_token:
                break
        return messages[:max_results]

    def list_threads(self, max_results: int = 20, page_token: Optional[str] = None) -> dict:
        """Lista threads recentes."""
        params = {"maxResults": max_results}
        if page_token:
            params["pageToken"] = page_token
        return self._api("GET", "threads", params=params)

    def search_threads(self, query: str, max_results: int = 20) -> list[dict]:
        """Busca threads por query."""
        params = {"q": query, "maxResults": max_results}
        result = self._api("GET", "threads", params=params)
        return result.get("threads", [])

    # ---- Ler mensagens ----

    def get_message(self, message_id: str, format: str = "full") -> dict:
        """Retorna mensagem completa."""
        return self._api("GET", f"messages/{message_id}", params={"format": format})

    def get_thread(self, thread_id: str) -> dict:
        """Retorna thread completa com todas as mensagens."""
        return self._api("GET", f"threads/{thread_id}")

    def get_message_parsed(self, message_id: str) -> dict:
        """Retorna mensagem parseada com subject, from, to, date, body, snippet."""
        msg = self.get_message(message_id)
        headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
        body = self._extract_body(msg.get("payload", {}))
        return {
            "id": message_id,
            "threadId": msg.get("threadId"),
            "subject": headers.get("subject", ""),
            "from": headers.get("from", ""),
            "to": headers.get("to", ""),
            "date": headers.get("date", ""),
            "snippet": msg.get("snippet", ""),
            "body": body,
            "labelIds": msg.get("labelIds", []),
        }

    def _extract_body(self, payload: dict) -> str:
        """Extrai corpo do email do payload."""
        if "parts" in payload:
            for part in payload["parts"]:
                if part.get("mimeType") == "text/plain":
                    data = part.get("body", {}).get("data", "")
                    if data:
                        return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
                elif part.get("mimeType", "").startswith("multipart/"):
                    result = self._extract_body(part)
                    if result:
                        return result
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
        return ""

    # ---- Enviar ----

    def send_message(self, to: str, subject: str, body: str, cc: Optional[str] = None, html: bool = False) -> dict:
        """Envia email."""
        msg = MIMEMultipart("alternative")
        msg["To"] = to
        msg["Subject"] = subject
        if cc:
            msg["Cc"] = cc
        if html:
            msg.attach(MIMEText(body, "html"))
        else:
            msg.attach(MIMEText(body, "plain"))
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        return self._api("POST", "messages/send", json={"raw": raw})

    def reply_to(self, message_id: str, body: str, html: bool = False) -> dict:
        """Responde a uma mensagem."""
        orig = self.get_message_parsed(message_id)
        subject = f"Re: {orig['subject']}" if not orig["subject"].lower().startswith("re:") else orig["subject"]
        return self.send_message(orig["from"], subject, body, html=html)

    def create_draft(self, to: str, subject: str, body: str) -> dict:
        """Cria rascunho."""
        msg = MIMEMultipart()
        msg["To"] = to
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        return self._api("POST", "drafts", json={"message": {"raw": raw}})

    # ---- Labels ----

    def list_labels(self) -> list[dict]:
        """Lista todas as labels."""
        result = self._api("GET", "labels")
        return result.get("labels", [])

    def add_labels(self, message_id: str, label_ids: list[str]) -> dict:
        """Adiciona labels a uma mensagem."""
        return self._api("POST", f"messages/{message_id}/modify", json={"addLabelIds": label_ids})

    def remove_labels(self, message_id: str, label_ids: list[str]) -> dict:
        """Remove labels de uma mensagem."""
        return self._api("POST", f"messages/{message_id}/modify", json={"removeLabelIds": label_ids})

    # ---- Acoes ----

    def mark_as_read(self, message_id: str) -> dict:
        """Marca como lido."""
        return self.remove_labels(message_id, ["UNREAD"])

    def mark_as_unread(self, message_id: str) -> dict:
        """Marca como nao lido."""
        return self.add_labels(message_id, ["UNREAD"])

    def archive(self, message_id: str) -> dict:
        """Arquiva (remove INBOX)."""
        return self.remove_labels(message_id, ["INBOX"])

    def unarchive(self, message_id: str) -> dict:
        """Desarquiva (adiciona INBOX)."""
        return self.add_labels(message_id, ["INBOX"])

    def trash(self, message_id: str) -> dict:
        """Move para lixeira."""
        return self._api("POST", f"messages/{message_id}/trash")

    def untrash(self, message_id: str) -> dict:
        """Restaura da lixeira."""
        return self._api("POST", f"messages/{message_id}/untrash")

    def delete_permanently(self, message_id: str) -> None:
        """Apaga permanentemente (irreversivel)."""
        self._api("DELETE", f"messages/{message_id}")

    # ---- Perfil ----

    def get_profile(self) -> dict:
        """Retorna perfil: emailAddress, messagesTotal, threadsTotal, historyId."""
        return self._api("GET", "profile")

    # ---- Helpers de alto nivel ----

    def get_unread(self, max_results: int = 20) -> list[dict]:
        """Retorna lista de mensagens nao lidas."""
        return self.search("is:unread", max_results=max_results)

    def get_unread_parsed(self, max_results: int = 20) -> list[dict]:
        """Retorna mensagens nao lidas ja parseadas."""
        unread = self.get_unread(max_results)
        return [self.get_message_parsed(m["id"]) for m in unread]

    def mark_thread_as_read(self, thread_id: str) -> list[dict]:
        """Marca todos os emails de uma thread como lidos."""
        thread = self.get_thread(thread_id)
        results = []
        for msg in thread.get("messages", []):
            if "UNREAD" in msg.get("labelIds", []):
                results.append(self.mark_as_read(msg["id"]))
        return results

    def bulk_mark_read(self, query: str) -> int:
        """Marca todas as mensagens que casam com a query como lidas."""
        msgs = self.search(query, max_results=100)
        count = 0
        for m in msgs:
            self.mark_as_read(m["id"])
            count += 1
        return count

    def watch_inbox(self, query: str = "is:unread", interval: int = 30, callback=None):
        """Loop de polling para novos emails."""
        seen = set()
        _log(f"Iniciando watch_inbox: query='{query}', interval={interval}s")
        try:
            while True:
                msgs = self.search(query, max_results=50)
                new_msgs = [m for m in msgs if m["id"] not in seen]
                for m in new_msgs:
                    seen.add(m["id"])
                if new_msgs and callback:
                    callback(new_msgs)
                elif new_msgs:
                    for m in new_msgs:
                        parsed = self.get_message_parsed(m["id"])
                        _log(f"NOVO: from={parsed['from']} | subject={parsed['subject']}")
                time.sleep(interval)
        except KeyboardInterrupt:
            _log("Watch interrompido pelo usuario.")

    # ---- Bounty & GitHub Convenience Methods ----

    def get_github_notifications(self, max_results: int = 50) -> list[dict]:
        """Busca notificacoes recentes do GitHub."""
        return self.search("from:noreply@github.com newer_than:2d", max_results=max_results)

    def get_bounty_related_emails(self, max_results: int = 30) -> list[dict]:
        """Busca emails relacionados a bounties e pagamentos."""
        queries = [
            "bounty OR payment OR payout OR merged OR approved",
            "from:noreply@github.com subject:bounty",
        ]
        seen_ids = set()
        results = []
        for q in queries:
            msgs = self.search(q, max_results=max_results)
            for m in msgs:
                if m["id"] not in seen_ids:
                    seen_ids.add(m["id"])
                    results.append(m)
        return results[:max_results]

    def extract_bounty_amount(self, message_id: str) -> Optional[float]:
        """Tenta extrair valor de bounty do corpo do email."""
        parsed = self.get_message_parsed(message_id)
        body = f"{parsed.get('body', '')} {parsed.get('snippet', '')}"
        patterns = [
            r'\$(\d+(?:\.\d{1,2})?)',
            r'(\d+(?:\.\d{1,2})?)\s*USD',
            r'bounty[:\s]+[\$]?(\d+(?:\.\d{1,2})?)',
            r'payment[:\s]+[\$]?(\d+(?:\.\d{1,2})?)',
        ]
        for pat in patterns:
            match = re.search(pat, body, re.IGNORECASE)
            if match:
                try:
                    return float(match.group(1))
                except ValueError:
                    continue
        return None

    def summarize_unread_bounties(self, max_results: int = 20) -> list[dict]:
        """Retorna resumo de emails nao lidos relacionados a bounties."""
        unread = self.get_unread(max_results=max_results * 2)
        summaries = []
        for msg in unread:
            parsed = self.get_message_parsed(msg["id"])
            sender = parsed.get("from", "").lower()
            subject = parsed.get("subject", "").lower()
            snippet = parsed.get("snippet", "").lower()
            combined = f"{sender} {subject} {snippet}"
            is_bounty = any(kw in combined for kw in ["bounty", "payment", "payout", "merged", "approved", "github"])
            if is_bounty:
                amount = self.extract_bounty_amount(msg["id"])
                summaries.append({
                    "id": msg["id"],
                    "from": parsed.get("from"),
                    "subject": parsed.get("subject"),
                    "date": parsed.get("date"),
                    "bounty_amount": amount,
                    "snippet": parsed.get("snippet", "")[:200],
                    "is_github": "github" in sender,
                })
        return summaries[:max_results]


# ---- CLI ----

def _cli():
    import argparse
    p = argparse.ArgumentParser(description="Gmail CLI")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("profile", help="Perfil da conta")
    sub.add_parser("unread", help="Mensagens nao lidas")

    s = sub.add_parser("search", help="Buscar mensagens")
    s.add_argument("query")
    s.add_argument("--max", type=int, default=20)

    s = sub.add_parser("read", help="Ler mensagem por ID")
    s.add_argument("message_id")

    s = sub.add_parser("send", help="Enviar email")
    s.add_argument("--to", required=True)
    s.add_argument("--subject", required=True)
    s.add_argument("--body", required=True)

    s = sub.add_parser("mark-read", help="Marcar como lido")
    s.add_argument("message_id")

    s = sub.add_parser("trash", help="Mover para lixeira")
    s.add_argument("message_id")

    s = sub.add_parser("labels", help="Listar labels")

    args = p.parse_args()
    g = GmailClient()

    if args.cmd == "profile":
        print(json.dumps(g.get_profile(), indent=2))
    elif args.cmd == "unread":
        msgs = g.get_unread_parsed(20)
        for m in msgs:
            print(f"[{m['id']}] {m['date']}")
            print(f"  De: {m['from']}")
            print(f"  Assunto: {m['subject']}")
            print(f"  Snippet: {m['snippet'][:150]}")
            print()
    elif args.cmd == "search":
        msgs = g.search(args.query, args.max)
        for m in msgs:
            parsed = g.get_message_parsed(m["id"])
            print(f"[{m['id']}] {parsed['date']} | {parsed['from']} | {parsed['subject']}")
    elif args.cmd == "read":
        parsed = g.get_message_parsed(args.message_id)
        print(json.dumps(parsed, indent=2, ensure_ascii=False))
    elif args.cmd == "send":
        r = g.send_message(args.to, args.subject, args.body)
        print(f"Enviado: id={r.get('id')}, thread={r.get('threadId')}")
    elif args.cmd == "mark-read":
        g.mark_as_read(args.message_id)
        print("Marcado como lido.")
    elif args.cmd == "trash":
        g.trash(args.message_id)
        print("Movido para lixeira.")
    elif args.cmd == "labels":
        labels = g.list_labels()
        for lb in labels:
            print(f"{lb['id']:30s} {lb['name']}")
    else:
        p.print_help()


if __name__ == "__main__":
    _cli()

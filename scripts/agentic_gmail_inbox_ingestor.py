#!/usr/bin/env python3
"""Incremental, fail-closed Gmail ingestion for Agentic.

Email content is untrusted input.  This worker reads and classifies messages,
records a private decision ledger, and may add reversible Gmail labels.  It
never executes instructions from a message, sends mail, or deletes mail.  The
only mailbox cleanup is removal of INBOX/UNREAD after durable, narrowly scoped
decision receipts (and, for GitHub actions, an authenticated provider receipt).
"""

from __future__ import annotations

import argparse
import base64
import fcntl
import hashlib
import json
import os
import re
import sys
import tempfile
import time
import unicodedata
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from email.utils import parseaddr
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable, Optional

import requests


ROOT = Path("/Agentic")
STATE_PATH = ROOT / "state" / "gmail_inbox_ingestor_state.json"
DECISION_PATH = ROOT / "data" / "aro" / "inbox" / "gmail_decisions.jsonl"
ACTION_QUEUE_PATH = ROOT / "data" / "aro" / "inbox" / "gmail_action_queue.jsonl"
ACTION_RESULT_PATH = ROOT / "data" / "aro" / "inbox" / "gmail_action_results.jsonl"
LOCK_PATH = Path("/run/agentic-gmail-ingestor/lock")
_CREDENTIALS_DIRECTORY = os.environ.get("CREDENTIALS_DIRECTORY")
OAUTH_CONFIG_PATH = (
    Path(_CREDENTIALS_DIRECTORY) / "gmail-oauth.json"
    if _CREDENTIALS_DIRECTORY
    else ROOT / ".config" / "gmail_oauth_token.json"
)
TOKEN_CACHE_PATH = Path("/var/lib/agentic-gmail/token_cache.json")

RULE_VERSION = "gmail-inbox-v1"
SCHEMA_VERSION = 1
REQUIRED_SCOPE = "https://www.googleapis.com/auth/gmail.modify"
SEARCH_LIMIT = 10_000
BODY_LIMIT = 200_000
BASELINE_QUERIES = (
    "newer_than:30d -in:sent -in:drafts -in:spam -in:trash",
    "is:unread -in:sent -in:drafts -in:spam -in:trash",
)

LABEL_NAMES = {
    "ingested": "Agentic/Ingested",
    "queued": "Agentic/Safe action queued",
    "quarantine": "Agentic/Untrusted content",
    "financial": "Agentic/Financial signal",
    "github_routine": "Agentic/GitHub routine",
    "github_verified": "Agentic/GitHub verified",
    "routine": "Agentic/Routine",
}

VALID_GITHUB_VERIFICATION_METHODS = {
    "authenticated_github_read_only_api",
    "authenticated_local_github_inventory",
}
REPO_VALUE_RE = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")

PRIORITY_PROVIDER_DOMAINS = {
    "algora.io",
    "bybit.com",
    "dework.xyz",
    "github.com",
    "gitcoin.co",
    "immunefi.com",
    "layer3.xyz",
    "openrouter.ai",
    "paypal.com",
    "polar.sh",
    "replit.com",
    "stripe.com",
    "superteam.fun",
    "wise.com",
}

FINANCIAL_RE = re.compile(
    r"\b(?:bount(?:y|ies)|reward|payout|payment|paid|invoice|receipt|settlement|"
    r"claim(?:ed|ing|s)?|funds?\s+released|transfer(?:red)?|wire|refund|"
    r"usdc|usdt|btc|eth|sol|rtc|pix)\b",
    re.IGNORECASE,
)
SECURITY_RE = re.compile(
    r"\b(?:security\s+alert|vulnerabilit(?:y|ies)|cve-\d|breach|compromised|"
    r"suspicious\s+(?:login|activity)|new\s+login|password\s+reset|2fa|mfa|"
    r"phishing|malware|secret\s+scanning)\b",
    re.IGNORECASE,
)
ACCOUNT_RE = re.compile(
    r"\b(?:action\s+required|verify|verification|confirm\s+(?:your|the)\s+"
    r"(?:account|identity|email)|kyc|identity|account\s+(?:locked|suspended)|"
    r"invitation|authorize|authorization|sign\s+in)\b",
    re.IGNORECASE,
)
ACTION_REQUEST_RE = re.compile(
    r"\b(?:action\s+required|respond\s+by|reply\s+(?:by|before)|complete\s+"
    r"verification|tax\s+form|wallet\s+address|withdraw(?:al)?|sign\s+(?:the\s+)?"
    r"(?:form|agreement)|submit\s+(?:the\s+)?(?:form|details|documents?))\b",
    re.IGNORECASE,
)
COMMERCE_RE = re.compile(
    r"\b(?:proposal|contract|quote|quotation|orcamento|budget|client\s+reply|"
    r"freelance|workana|upwork|99freelas|purchase\s+order)\b",
    re.IGNORECASE,
)
GITHUB_ACTION_RE = re.compile(
    r"\b(?:pull\s+request|pr\s*#?\d+|issue\s*#?\d+|review\s+requested|"
    r"changes\s+requested|assigned|mentioned|merged|merge\s+conflict|"
    r"workflow\s+(?:failed|failure)|checks?\s+failed|build\s+failed|cla\b)\b",
    re.IGNORECASE,
)
ROUTINE_RE = re.compile(
    r"\b(?:newsletter|digest|weekly\s+(?:update|summary)|monthly\s+summary|"
    r"trending|new\s+follower|marketing|promotion(?:al)?|unsubscribe|"
    r"all\s+checks\s+passed|successfully\s+deployed)\b",
    re.IGNORECASE,
)
PROMPT_INJECTION_RE = re.compile(
    r"(?:ignore|disregard|override)\s+(?:all\s+|any\s+|the\s+)?(?:previous|prior|"
    r"system|developer)\s+instructions?|"
    r"(?:reveal|print|send|exfiltrate)\s+(?:the\s+)?(?:system\s+prompt|developer\s+"
    r"message|password|oauth\s+token|api\s+key|private\s+key|seed\s+phrase)|"
    r"(?:execute|run)\s+(?:this\s+)?(?:shell|bash|powershell|terminal|command)|"
    r"act\s+as\s+(?:the\s+)?(?:system|developer|administrator)",
    re.IGNORECASE,
)
REPO_RE = re.compile(r"\[([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)\]")
EXPLICIT_ENTITY_RE = re.compile(
    r"\((PR|Pull\s+Request|Issue)\s*#(\d+)\)", re.IGNORECASE
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(ch for ch in text if not unicodedata.combining(ch)).lower()


def message_hash(message_id: str) -> str:
    return hashlib.sha256(f"gmail:{message_id}".encode()).hexdigest()[:16]


def content_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()[:24]


def chunks(values: list[str], size: int = 1000) -> Iterable[list[str]]:
    for offset in range(0, len(values), size):
        yield values[offset : offset + size]


def atomic_json_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        os.chmod(path, 0o600)
    finally:
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass


def append_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    if not records:
        return
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    with open(path, "a", encoding="utf-8") as handle:
        os.chmod(path, 0o600)
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def load_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def load_decisions(path: Path = DECISION_PATH) -> dict[tuple[str, str], dict[str, Any]]:
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return latest
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"decision ledger invalid at line {line_number}") from exc
        message_id = str(item.get("message_id", ""))
        rule_version = str(item.get("rule_version", ""))
        if not message_id or not rule_version:
            raise RuntimeError(f"decision ledger key missing at line {line_number}")
        latest[(message_id, rule_version)] = item
    return latest


def load_action_queue_keys(path: Path = ACTION_QUEUE_PATH) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return keys
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"action queue invalid at line {line_number}") from exc
        key = (str(item.get("message_id", "")), str(item.get("rule_version", "")))
        if not all(key):
            raise RuntimeError(f"action queue key missing at line {line_number}")
        keys.add(key)
    return keys


def load_action_results(
    path: Path = ACTION_RESULT_PATH,
) -> dict[tuple[str, str], dict[str, Any]]:
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return latest
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"action result invalid at line {line_number}") from exc
        key = (str(item.get("message_id", "")), str(item.get("rule_version", "")))
        if not all(key):
            raise RuntimeError(f"action result key missing at line {line_number}")
        latest[key] = item
    return latest


def oauth_health() -> dict[str, Any]:
    token = load_json_object(OAUTH_CONFIG_PATH)
    configured_scopes = token.get("scopes") or []
    if isinstance(configured_scopes, str):
        configured_scopes = configured_scopes.split()
    return {
        "credential_source": (
            "systemd_credential" if _CREDENTIALS_DIRECTORY else "oauth_json_direct"
        ),
        "oauth_file_present": OAUTH_CONFIG_PATH.is_file(),
        "oauth_file_private": OAUTH_CONFIG_PATH.is_file()
        and bool(OAUTH_CONFIG_PATH.stat().st_mode & 0o400)
        and not bool(OAUTH_CONFIG_PATH.stat().st_mode & 0o077),
        "oauth_file_not_symlink": OAUTH_CONFIG_PATH.is_file()
        and not OAUTH_CONFIG_PATH.is_symlink(),
        "required_fields_present": all(
            bool(token.get(key))
            for key in ("client_id", "client_secret", "refresh_token", "token_uri")
        ),
        "required_scope_configured": REQUIRED_SCOPE in configured_scopes,
    }


def _atomic_token_cache_write(payload: dict[str, Any]) -> None:
    TOKEN_CACHE_PATH.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(TOKEN_CACHE_PATH.parent, 0o700)
    fd, temporary_name = tempfile.mkstemp(
        prefix=".token_cache.", dir=TOKEN_CACHE_PATH.parent
    )
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, TOKEN_CACHE_PATH)
        os.chmod(TOKEN_CACHE_PATH, 0o600)
    finally:
        try:
            temporary_path.unlink()
        except FileNotFoundError:
            pass


class GmailAPIClient:
    BASE_URL = "https://gmail.googleapis.com/gmail/v1/users/me"

    def __init__(self) -> None:
        health = oauth_health()
        if not all(
            health.get(key)
            for key in (
                "oauth_file_present",
                "oauth_file_private",
                "oauth_file_not_symlink",
                "required_fields_present",
                "required_scope_configured",
            )
        ):
            raise RuntimeError("OAuth configuration health check failed")
        config = load_json_object(OAUTH_CONFIG_PATH)
        self._client_id = str(config["client_id"])
        self._client_secret = str(config["client_secret"])
        self._refresh_token = str(config["refresh_token"])
        self._token_uri = str(config["token_uri"])
        self._access_token: Optional[str] = None
        self._expires_at = 0.0

    def _load_cached_token(self) -> None:
        if not TOKEN_CACHE_PATH.is_file() or TOKEN_CACHE_PATH.is_symlink():
            return
        if (TOKEN_CACHE_PATH.stat().st_mode & 0o777) != 0o600:
            return
        try:
            cached = json.loads(TOKEN_CACHE_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if cached.get("expires_at", 0) > time.time() + 60 and cached.get("access_token"):
            self._access_token = str(cached["access_token"])
            self._expires_at = float(cached["expires_at"])

    def get_access_token(self, force_refresh: bool = False) -> str:
        if not force_refresh and self._access_token and time.time() < self._expires_at - 60:
            return self._access_token
        if not force_refresh:
            self._load_cached_token()
            if self._access_token and time.time() < self._expires_at - 60:
                return self._access_token
        response = None
        for attempt in range(5):
            try:
                response = requests.post(
                    self._token_uri,
                    data={
                        "client_id": self._client_id,
                        "client_secret": self._client_secret,
                        "refresh_token": self._refresh_token,
                        "grant_type": "refresh_token",
                    },
                    timeout=20,
                )
                break
            except requests.RequestException as exc:
                if attempt >= 4:
                    raise RuntimeError("OAuth transport retry exhausted") from exc
                time.sleep(min(10.0, 0.5 * (2**attempt)))
        if response is None:
            raise RuntimeError("OAuth transport retry exhausted")
        if response.status_code != 200:
            error_code = "oauth_refresh_failed"
            try:
                error_code = str(response.json().get("error") or error_code)
            except (ValueError, AttributeError):
                pass
            raise RuntimeError(f"OAuth refresh failed: {response.status_code}:{error_code}")
        payload = response.json()
        self._access_token = str(payload["access_token"])
        self._expires_at = time.time() + int(payload.get("expires_in", 3600))
        _atomic_token_cache_write(
            {"access_token": self._access_token, "expires_at": self._expires_at}
        )
        return self._access_token

    @staticmethod
    def _api_error_code(response: Any) -> str:
        try:
            error = response.json().get("error", {})
            if isinstance(error, dict):
                return str(error.get("status") or error.get("code") or "api_error")
        except (ValueError, AttributeError):
            pass
        return "api_error"

    def _api(self, method: str, endpoint: str, **kwargs: Any) -> dict[str, Any]:
        url = f"{self.BASE_URL}/{endpoint}"
        for attempt in range(5):
            token = self.get_access_token(force_refresh=False)
            try:
                response = requests.request(
                    method,
                    url,
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=30,
                    **kwargs,
                )
            except requests.RequestException as exc:
                if attempt >= 4:
                    raise RuntimeError("Gmail API transport retry exhausted") from exc
                time.sleep(min(10.0, 0.5 * (2**attempt)))
                continue
            if response.status_code == 401 and attempt == 0:
                self._access_token = None
                self._expires_at = 0
                self.get_access_token(force_refresh=True)
                continue
            if response.status_code in {429, 500, 502, 503, 504} and attempt < 4:
                retry_after = response.headers.get("Retry-After")
                try:
                    delay = min(10.0, max(0.25, float(retry_after)))
                except (TypeError, ValueError):
                    delay = min(10.0, 0.5 * (2**attempt))
                time.sleep(delay)
                continue
            if response.status_code >= 400:
                raise RuntimeError(
                    f"Gmail API {response.status_code}: {self._api_error_code(response)}"
                )
            return response.json() if response.text else {}
        raise RuntimeError("Gmail API bounded retry exhausted")

    def get_profile(self) -> dict[str, Any]:
        return self._api("GET", "profile")

    def get_message(self, message_id: str) -> dict[str, Any]:
        return self._api("GET", f"messages/{message_id}", params={"format": "full"})

    def list_labels(self) -> list[dict[str, Any]]:
        return self._api("GET", "labels").get("labels", [])

    def search(self, query: str, max_results: int) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        seen_tokens: set[str] = set()
        page_token: Optional[str] = None
        while len(messages) < max_results:
            params: dict[str, Any] = {
                "q": query,
                "maxResults": min(500, max_results - len(messages)),
            }
            if page_token:
                params["pageToken"] = page_token
            result = self._api("GET", "messages", params=params)
            for item in result.get("messages", []) or []:
                message_id = str(item.get("id", ""))
                if message_id and message_id not in seen_ids:
                    seen_ids.add(message_id)
                    messages.append(item)
            next_token = result.get("nextPageToken")
            if not next_token:
                break
            next_token = str(next_token)
            if next_token in seen_tokens:
                raise RuntimeError("Gmail search pagination token repeated")
            seen_tokens.add(next_token)
            page_token = next_token
        return messages[:max_results]


class _HTMLText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data)


def _decode_data(value: object) -> str:
    if not value:
        return ""
    raw = str(value)
    raw += "=" * (-len(raw) % 4)
    try:
        return base64.urlsafe_b64decode(raw.encode("ascii")).decode(
            "utf-8", errors="replace"
        )
    except (ValueError, UnicodeEncodeError):
        return ""


def extract_message_text(payload: dict[str, Any], limit: int = BODY_LIMIT) -> tuple[str, bool]:
    plain: list[str] = []
    html_parts: list[str] = []
    external_text_part = False

    def visit(part: dict[str, Any]) -> None:
        nonlocal external_text_part
        mime = str(part.get("mimeType", "")).lower()
        filename = str(part.get("filename", ""))
        body = part.get("body") if isinstance(part.get("body"), dict) else {}
        if mime.startswith("text/") and body.get("attachmentId") and not filename:
            external_text_part = True
        data = _decode_data(body.get("data"))
        if data and not filename:
            if mime == "text/plain":
                plain.append(data)
            elif mime == "text/html":
                html_parts.append(data)
        for child in part.get("parts", []) or []:
            if isinstance(child, dict):
                visit(child)

    visit(payload)
    text = "\n".join(plain)
    if not text and html_parts:
        parser = _HTMLText()
        for value in html_parts:
            try:
                parser.feed(value)
            except Exception:
                continue
        text = "\n".join(parser.parts)
    truncated = len(text) > limit or external_text_part
    return text[:limit], truncated


def parsed_headers(payload: dict[str, Any]) -> dict[str, str]:
    headers: dict[str, str] = {}
    for item in payload.get("headers", []) or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip().lower()
        value = str(item.get("value", ""))
        if name:
            headers[name] = f"{headers[name]}\n{value}" if name in headers else value
    return headers


def sender_domain(sender: str) -> Optional[str]:
    address = parseaddr(sender)[1].strip().lower()
    if "@" not in address:
        return None
    domain = address.rsplit("@", 1)[-1]
    return domain if re.fullmatch(r"[a-z0-9.-]+", domain) else None


def is_priority_provider_domain(domain: Optional[str]) -> bool:
    if not domain:
        return False
    return any(domain == known or domain.endswith("." + known) for known in PRIORITY_PROVIDER_DOMAINS)


def authentication_summary(headers: dict[str, str]) -> dict[str, bool]:
    result = normalize(headers.get("authentication-results", ""))
    return {
        "spf_pass": bool(re.search(r"\bspf=pass\b", result)),
        "dkim_pass": bool(re.search(r"\bdkim=pass\b", result)),
        "dmarc_pass": bool(re.search(r"\bdmarc=pass\b", result)),
    }


def structured_entities(domain: Optional[str], subject: str) -> dict[str, Any]:
    if not domain or not (domain == "github.com" or domain.endswith(".github.com")):
        return {}
    repo_match = REPO_RE.search(subject)
    entity_match = EXPLICIT_ENTITY_RE.search(subject)
    result: dict[str, Any] = {"provider": "github"}
    if repo_match:
        result["repo"] = repo_match.group(1)
    if entity_match:
        kind = normalize(entity_match.group(1))
        result["entity_kind"] = "issue" if kind == "issue" else "pull_request"
        result["number"] = int(entity_match.group(2))
    return result


def classify_text(sender: str, subject: str, snippet: str, body: str) -> dict[str, Any]:
    domain = sender_domain(sender)
    text = normalize("\n".join((sender, subject, snippet, body)))
    prompt_injection = bool(PROMPT_INJECTION_RE.search(text))
    financial = bool(FINANCIAL_RE.search(text))
    security = bool(SECURITY_RE.search(text))
    account = bool(ACCOUNT_RE.search(text))
    action_request = bool(ACTION_REQUEST_RE.search(text))
    commerce = bool(COMMERCE_RE.search(text))
    github = bool(domain and (domain == "github.com" or domain.endswith(".github.com")))
    priority_provider = is_priority_provider_domain(domain)
    github_action = bool(GITHUB_ACTION_RE.search(text))
    routine = bool(ROUTINE_RE.search(text))

    if prompt_injection:
        category, urgency = "untrusted_instruction", "high"
        route = "autonomous_quarantine"
    elif financial:
        category, urgency = "financial_signal", "high"
        route = "autonomous_provider_verification"
    elif security:
        category, urgency = "security_alert", "high"
        route = "autonomous_provider_verification"
    elif account:
        category, urgency = "account_action", "medium"
        route = "awaiting_safe_executor"
    elif action_request:
        category, urgency = "action_request", "medium"
        route = "awaiting_safe_executor"
    elif commerce:
        category, urgency = "commerce_signal", "medium"
        route = "autonomous_counterparty_verification"
    elif github and github_action:
        category, urgency = "github_action", "medium"
        route = "autonomous_github_verification"
    elif github:
        category, urgency = "github_routine", "low"
        route = "autonomous_archive_routine"
    elif routine:
        category, urgency = "routine_notification", "low"
        route = "record_only_routine"
    else:
        category, urgency = "unknown", "medium"
        route = "record_only_unclassified"

    requires_safe_action = category in {
        "untrusted_instruction",
        "financial_signal",
        "security_alert",
        "account_action",
        "action_request",
        "commerce_signal",
        "github_action",
    }
    return {
        "category": category,
        "urgency": urgency,
        "route": route,
        "requires_safe_action": requires_safe_action,
        "sender_domain": domain,
        "signals": {
            "prompt_injection": prompt_injection,
            "financial": financial,
            "security": security,
            "account": account,
            "action_request": action_request,
            "commerce": commerce,
            "github": github,
            "priority_provider": priority_provider,
            "github_action": github_action,
            "routine": routine,
        },
        "trusted_instruction": False,
        "auto_execute": False,
        "financial_effect_allowed": False,
    }


def decision_from_message(raw: dict[str, Any], source: str, detected_at: str) -> dict[str, Any]:
    message_id = str(raw.get("id", ""))
    if not message_id:
        raise ValueError("message lacks id")
    payload = raw.get("payload") if isinstance(raw.get("payload"), dict) else {}
    headers = parsed_headers(payload)
    body, body_truncated = extract_message_text(payload)
    subject = headers.get("subject", "")
    sender = headers.get("from", "")
    snippet = str(raw.get("snippet", ""))
    classification = classify_text(sender, subject, snippet, body)
    return {
        "schema_version": SCHEMA_VERSION,
        "rule_version": RULE_VERSION,
        "source": source,
        "message_id": message_id,
        "message_hash": message_hash(message_id),
        "thread_id": str(raw.get("threadId", "")) or None,
        "history_id": str(raw.get("historyId", "")) or None,
        "internal_date_ms": str(raw.get("internalDate", "")) or None,
        "gmail_labels_at_ingest": sorted(str(x) for x in raw.get("labelIds", []) or []),
        "sender_domain": classification["sender_domain"],
        "subject_fingerprint": content_hash(subject),
        "content_fingerprint": content_hash("\n".join((subject, snippet, body))),
        "body_truncated_or_external": body_truncated,
        "authentication": authentication_summary(headers),
        "structured_entities": structured_entities(
            classification["sender_domain"], subject
        ),
        "classification": {
            key: classification[key]
            for key in (
                "category",
                "urgency",
                "route",
                "requires_safe_action",
                "signals",
                "trusted_instruction",
                "auto_execute",
                "financial_effect_allowed",
            )
        },
        "detected_at": detected_at,
        "status": "classified_untrusted_input",
    }


def missing_decision(message_id: str, source: str, detected_at: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "rule_version": RULE_VERSION,
        "source": source,
        "message_id": message_id,
        "message_hash": message_hash(message_id),
        "classification": {
            "category": "message_missing",
            "urgency": "low",
            "route": "no_action",
            "requires_safe_action": False,
            "signals": {},
            "trusted_instruction": False,
            "auto_execute": False,
            "financial_effect_allowed": False,
        },
        "detected_at": detected_at,
        "status": "message_missing_before_fetch",
    }


def unique_ids(items: Iterable[dict[str, Any]]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        message_id = str(item.get("id", ""))
        if message_id and message_id not in seen:
            seen.add(message_id)
            result.append(message_id)
    return result


def search_candidates(client: Any, search_limit: int = SEARCH_LIMIT) -> tuple[list[str], bool]:
    result: list[str] = []
    seen: set[str] = set()
    truncated = False
    for query in BASELINE_QUERIES:
        ids = unique_ids(client.search(query, max_results=search_limit))
        truncated = truncated or len(ids) >= search_limit
        for message_id in ids:
            if message_id not in seen:
                seen.add(message_id)
                result.append(message_id)
    return result, truncated


def gap_scan_required(
    state: dict[str, Any], now: datetime, interval_seconds: int
) -> bool:
    if not state.get("bootstrap_complete") or state.get("history_checkpoint_stale"):
        return True
    value = state.get("last_gap_scan_at")
    if not value:
        return True
    try:
        previous = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if previous.tzinfo is None:
            previous = previous.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return True
    return (now - previous.astimezone(timezone.utc)).total_seconds() >= interval_seconds


def promote_completed_gap_scan(state: dict[str, Any], complete: bool) -> None:
    if complete and state.get("gap_scan_performed") and state.get("gap_scan_started_at"):
        state["last_gap_scan_at"] = state["gap_scan_started_at"]


def history_candidates(client: Any, start_history_id: str) -> tuple[list[str], str]:
    ids: list[str] = []
    seen_ids: set[str] = set()
    seen_tokens: set[str] = set()
    page_token: Optional[str] = None
    latest_history_id = start_history_id
    while True:
        params: dict[str, Any] = {
            "startHistoryId": start_history_id,
            "historyTypes": "messageAdded",
            "maxResults": 500,
        }
        if page_token:
            params["pageToken"] = page_token
        result = client._api("GET", "history", params=params)
        latest_history_id = str(result.get("historyId") or latest_history_id)
        for history in result.get("history", []) or []:
            for added in history.get("messagesAdded", []) or []:
                message = added.get("message") if isinstance(added, dict) else None
                if not isinstance(message, dict):
                    continue
                message_id = str(message.get("id", ""))
                if message_id and message_id not in seen_ids:
                    seen_ids.add(message_id)
                    ids.append(message_id)
        next_token = result.get("nextPageToken")
        if not next_token:
            break
        next_token = str(next_token)
        if next_token in seen_tokens:
            raise RuntimeError("Gmail history pagination token repeated")
        seen_tokens.add(next_token)
        page_token = next_token
    return ids, latest_history_id


def resolve_labels(client: Any) -> dict[str, str]:
    existing = {
        str(item.get("name", "")): str(item.get("id", ""))
        for item in client.list_labels()
        if item.get("name") and item.get("id")
    }
    result: dict[str, str] = {}
    for key, name in LABEL_NAMES.items():
        label_id = existing.get(name)
        if not label_id:
            created = client._api(
                "POST",
                "labels",
                json={
                    "name": name,
                    "labelListVisibility": "labelShow",
                    "messageListVisibility": "show",
                },
            )
            label_id = str(created.get("id", ""))
        if not label_id:
            raise RuntimeError(f"Gmail label unavailable: {name}")
        result[key] = label_id
    return result


def label_keys_for(decision: dict[str, Any]) -> set[str]:
    classification = decision.get("classification", {})
    category = str(classification.get("category", "unknown"))
    keys = {"ingested"}
    if classification.get("requires_safe_action"):
        keys.add("queued")
    if category == "untrusted_instruction":
        keys.add("quarantine")
    if category == "financial_signal":
        keys.add("financial")
    if category == "github_routine":
        keys.add("github_routine")
    if category == "routine_notification":
        keys.add("routine")
    return keys


def apply_reversible_labels(
    client: Any, decisions: list[dict[str, Any]], label_ids: dict[str, str]
) -> dict[str, int]:
    ids_by_label: dict[str, list[str]] = {key: [] for key in label_ids}
    for decision in decisions:
        if decision.get("status") == "message_missing_before_fetch":
            continue
        for key in label_keys_for(decision):
            ids_by_label[key].append(str(decision["message_id"]))
    counts: dict[str, int] = {}
    for key, message_ids in ids_by_label.items():
        unique = list(dict.fromkeys(message_ids))
        for batch in chunks(unique):
            client._api(
                "POST",
                "messages/batchModify",
                json={"ids": batch, "addLabelIds": [label_ids[key]]},
            )
        counts[key] = len(unique)
    return counts


def archive_labeled_github_routine(
    client: Any,
    label_id: str,
    persisted_decisions: Iterable[dict[str, Any]],
    search_limit: int = SEARCH_LIMIT,
) -> tuple[int, bool]:
    # This is the only destructive-looking mailbox transition in this worker.
    # It is reversible and is constrained to messages already durably classified
    # and labeled as non-financial GitHub routine.  No message is trashed/deleted.
    query = f'in:inbox label:"{LABEL_NAMES["github_routine"]}"'
    labeled_inbox_ids = set(
        unique_ids(client.search(query, max_results=search_limit))
    )
    persisted_routine_ids = {
        str(item.get("message_id", ""))
        for item in persisted_decisions
        if item.get("rule_version") == RULE_VERSION
        and item.get("classification", {}).get("category") == "github_routine"
    }
    message_ids = sorted(labeled_inbox_ids & persisted_routine_ids)
    for batch in chunks(message_ids):
        client._api(
            "POST",
            "messages/batchModify",
            json={"ids": batch, "removeLabelIds": ["INBOX", "UNREAD"]},
        )
    return len(message_ids), len(labeled_inbox_ids) >= search_limit


def verified_github_action_ids(
    persisted_decisions: Iterable[dict[str, Any]],
    action_results: dict[tuple[str, str], dict[str, Any]],
) -> list[str]:
    eligible: list[str] = []
    for decision in persisted_decisions:
        message_id = str(decision.get("message_id", ""))
        if not message_id or decision.get("rule_version") != RULE_VERSION:
            continue
        classification = decision.get("classification", {})
        signals = classification.get("signals", {})
        if classification.get("category") != "github_action":
            continue
        if any(
            bool(signals.get(key))
            for key in ("financial", "security", "account", "action_request")
        ):
            continue
        domain = str(decision.get("sender_domain", ""))
        if domain != "github.com" and not domain.endswith(".github.com"):
            continue
        authentication = decision.get("authentication", {})
        if not (
            authentication.get("dkim_pass") or authentication.get("dmarc_pass")
        ):
            continue
        entities = decision.get("structured_entities", {})
        result = action_results.get((message_id, RULE_VERSION), {})
        verification = result.get("provider_verification", {})
        if result.get("status") != "verified_provider_state_awaiting_safe_executor":
            continue
        if result.get("category") != "github_action":
            continue
        if result.get("auto_executed_email_instruction") is not False:
            continue
        if result.get("financial_effect") is not False:
            continue
        if verification.get("provider") != "github":
            continue
        if verification.get("verification_method") not in VALID_GITHUB_VERIFICATION_METHODS:
            continue
        if not verification.get("verified_at"):
            continue
        if verification.get("bounty_label_present") is not False:
            continue
        repo = str(verification.get("repo", ""))
        kind = str(verification.get("entity_kind", ""))
        try:
            number = int(verification.get("number"))
            entity_number = int(entities.get("number"))
        except (TypeError, ValueError):
            continue
        if not REPO_VALUE_RE.fullmatch(repo) or kind != "pull_request" or number <= 0:
            continue
        if (
            entities.get("provider") != "github"
            or str(entities.get("repo", "")) != repo
            or str(entities.get("entity_kind", "")) != kind
            or entity_number != number
        ):
            continue
        eligible.append(message_id)
    return sorted(set(eligible))


def archive_verified_github_actions(
    client: Any,
    label_id: str,
    persisted_decisions: Iterable[dict[str, Any]],
    action_results: dict[tuple[str, str], dict[str, Any]],
    search_limit: int = SEARCH_LIMIT,
) -> tuple[int, int, bool]:
    # Two durable receipts are mandatory: the current classification decision
    # and an authenticated GitHub provider verification result.  Financial,
    # security, account/action-request, bounty, issue, or unverifiable messages
    # never enter this reversible cleanup path.
    eligible = verified_github_action_ids(persisted_decisions, action_results)
    for batch in chunks(eligible):
        client._api(
            "POST",
            "messages/batchModify",
            json={"ids": batch, "addLabelIds": [label_id, "TRASH"]},
        )
    query = f'in:inbox label:"{LABEL_NAMES["github_verified"]}"'
    labeled_inbox_ids = set(unique_ids(client.search(query, max_results=search_limit)))
    message_ids = sorted(labeled_inbox_ids & set(eligible))
    for batch in chunks(message_ids):
        client._api(
            "POST",
            "messages/batchModify",
            json={"ids": batch, "removeLabelIds": ["INBOX", "UNREAD"], "addLabelIds": ["TRASH"]},
        )
    return len(eligible), len(message_ids), len(labeled_inbox_ids) >= search_limit


def action_queue_record(decision: dict[str, Any]) -> Optional[dict[str, Any]]:
    classification = decision.get("classification", {})
    if not classification.get("requires_safe_action"):
        return None
    return {
        "schema_version": SCHEMA_VERSION,
        "rule_version": RULE_VERSION,
        "source": "gmail_ingestor",
        "message_id": decision["message_id"],
        "message_hash": decision["message_hash"],
        "sender_domain": decision.get("sender_domain"),
        "structured_entities": decision.get("structured_entities", {}),
        "category": classification.get("category"),
        "urgency": classification.get("urgency"),
        "safe_route": classification.get("route"),
        "status": "pending_safe_consumer",
        "email_content_trusted": False,
        "auto_execute": False,
        "financial_effect_allowed": False,
        "queued_at": decision["detected_at"],
    }


def missing_action_records(
    persisted_decisions: Iterable[dict[str, Any]],
    action_queue_keys: set[tuple[str, str]],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for decision in persisted_decisions:
        value = action_queue_record(decision)
        if value is None:
            continue
        key = (str(value["message_id"]), str(value["rule_version"]))
        if key not in action_queue_keys:
            records.append(value)
    return records


def process_one(client: Any, message_id: str, source: str, detected_at: str) -> dict[str, Any]:
    try:
        raw = client.get_message(message_id)
    except RuntimeError as exc:
        if "Gmail API 404" in str(exc):
            return missing_decision(message_id, source, detected_at)
        raise
    label_ids = {str(value) for value in raw.get("labelIds", []) or []}
    if label_ids.intersection({"SENT", "DRAFT", "SPAM", "TRASH"}):
        decision = missing_decision(message_id, source, detected_at)
        decision["status"] = "excluded_mailbox_location"
        decision["classification"]["category"] = "excluded_mailbox_location"
        return decision
    return decision_from_message(raw, source, detected_at)


def run(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    started_at = utc_now()
    previous_state = load_json_object(STATE_PATH)
    state: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "rule_version": RULE_VERSION,
        "started_at": started_at,
        "completed_at": None,
        "status": "running",
        "dry_run": bool(args.dry_run),
        "apply_labels": bool(args.apply_labels),
        "oauth": oauth_health(),
        "baseline_candidate_count": 0,
        "history_candidate_count": 0,
        "candidate_count": 0,
        "already_decided_count": 0,
        "attempted_count": 0,
        "processed_count": 0,
        "remaining_count": 0,
        "error_count": 0,
        "errors": [],
        "new_category_counts": {},
        "total_category_counts": {},
        "total_decision_count": 0,
        "labels_added_counts": {},
        "github_routine_archived_count": 0,
        "github_routine_archive_truncated": False,
        "github_verified_action_label_count": 0,
        "github_verified_action_archived_count": 0,
        "github_verified_action_archive_truncated": False,
        "new_action_queue_count": 0,
        "total_action_queue_count": 0,
        "baseline_truncated": False,
        "bootstrap_complete": bool(previous_state.get("bootstrap_complete")),
        "bootstrap_history_id": previous_state.get("bootstrap_history_id"),
        "checkpoint_history_id": previous_state.get("checkpoint_history_id"),
        "history_checkpoint_stale": False,
        "gap_scan_performed": False,
        "gap_scan_started_at": None,
        "last_gap_scan_at": previous_state.get("last_gap_scan_at"),
        "last_success_at": previous_state.get("last_success_at"),
        "consecutive_failure_count": 0,
    }

    oauth = state["oauth"]
    if not all(
        oauth.get(key)
        for key in (
            "oauth_file_present",
            "oauth_file_private",
            "oauth_file_not_symlink",
            "required_fields_present",
            "required_scope_configured",
        )
    ):
        raise RuntimeError("OAuth configuration health check failed")

    client = GmailAPIClient()
    client.get_access_token()
    profile = client.get_profile()
    run_start_history_id = str(profile.get("historyId", ""))
    if not run_start_history_id:
        raise RuntimeError("Gmail profile lacks historyId")
    if not state["bootstrap_history_id"]:
        state["bootstrap_history_id"] = run_start_history_id

    decisions = load_decisions()
    action_queue_keys = load_action_queue_keys()
    history_ids: list[str] = []
    history_latest = str(state.get("checkpoint_history_id") or "")
    if state["bootstrap_complete"] and state.get("checkpoint_history_id"):
        try:
            history_ids, history_latest = history_candidates(
                client, str(state["checkpoint_history_id"])
            )
        except RuntimeError as exc:
            if "Gmail API 404" not in str(exc):
                raise
            state["history_checkpoint_stale"] = True
            state["bootstrap_complete"] = False
            state["bootstrap_history_id"] = run_start_history_id
            state["checkpoint_history_id"] = None
            history_ids = []
    state["history_candidate_count"] = len(history_ids)

    baseline_ids: list[str] = []
    baseline_truncated = False
    now = datetime.now(timezone.utc)
    if gap_scan_required(state, now, args.gap_scan_interval_sec):
        baseline_ids, baseline_truncated = search_candidates(
            client, args.search_limit
        )
        state["gap_scan_performed"] = True
        state["gap_scan_started_at"] = now.isoformat()
    state["baseline_candidate_count"] = len(baseline_ids)
    state["baseline_truncated"] = baseline_truncated

    source_by_id: dict[str, str] = {}
    ordered_ids: list[str] = []
    for message_id in history_ids:
        if message_id not in source_by_id:
            source_by_id[message_id] = "gmail_history"
            ordered_ids.append(message_id)
    for message_id in baseline_ids:
        if message_id not in source_by_id:
            source_by_id[message_id] = "gmail_baseline"
            ordered_ids.append(message_id)

    state["candidate_count"] = len(ordered_ids)
    pending_ids = [
        message_id
        for message_id in ordered_ids
        if (message_id, RULE_VERSION) not in decisions
    ]
    state["already_decided_count"] = len(ordered_ids) - len(pending_ids)
    attempted_ids = pending_ids[: args.max_messages]
    state["attempted_count"] = len(attempted_ids)

    new_decisions: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                process_one,
                client,
                message_id,
                source_by_id[message_id],
                started_at,
            ): message_id
            for message_id in attempted_ids
        }
        for future in as_completed(futures):
            message_id = futures[future]
            try:
                new_decisions.append(future.result())
            except Exception as exc:  # retry on next cycle; never advance checkpoint
                errors.append(
                    {
                        "message_hash": message_hash(message_id),
                        "error_type": type(exc).__name__,
                    }
                )

    new_decisions.sort(
        key=lambda item: (str(item.get("internal_date_ms") or ""), item["message_id"])
    )
    state["error_count"] = len(errors)
    state["errors"] = errors[:50]
    state["processed_count"] = len(new_decisions)
    state["new_category_counts"] = dict(
        sorted(
            Counter(
                str(item.get("classification", {}).get("category", "unknown"))
                for item in new_decisions
            ).items()
        )
    )

    label_ids: dict[str, str] = {}
    if not args.dry_run and (
        (args.apply_labels and new_decisions)
        or args.archive_github_routine
        or args.archive_verified_github_actions
    ):
        label_ids = resolve_labels(client)
    if args.apply_labels and not args.dry_run and new_decisions:
        state["labels_added_counts"] = apply_reversible_labels(
            client, new_decisions, label_ids
        )

    if not args.dry_run:
        # Receipt is the commit point.  The safe-action queue is derived only
        # after the decision ledger has been fsync'd.  Every later run repairs a
        # missing queue record from persisted decisions, so a crash at either
        # boundary remains fail-closed and self-healing.
        append_jsonl(DECISION_PATH, new_decisions)
        for item in new_decisions:
            decisions[(str(item["message_id"]), RULE_VERSION)] = item
        current_persisted_decisions = [
            value
            for (_, version), value in decisions.items()
            if version == RULE_VERSION
        ]
        action_records = missing_action_records(
            current_persisted_decisions, action_queue_keys
        )
        append_jsonl(ACTION_QUEUE_PATH, action_records)
        for value in action_records:
            action_queue_keys.add(
                (str(value["message_id"]), str(value["rule_version"]))
            )
        state["new_action_queue_count"] = len(action_records)
        if args.archive_github_routine:
            archived_count, archive_truncated = archive_labeled_github_routine(
                client,
                label_ids["github_routine"],
                [
                    value
                    for value in current_persisted_decisions
                ],
                args.search_limit,
            )
            state["github_routine_archived_count"] = archived_count
            state["github_routine_archive_truncated"] = archive_truncated
        if args.archive_verified_github_actions:
            action_results = load_action_results()
            (
                verified_label_count,
                verified_archived_count,
                verified_archive_truncated,
            ) = archive_verified_github_actions(
                client,
                label_ids["github_verified"],
                current_persisted_decisions,
                action_results,
                args.search_limit,
            )
            state["github_verified_action_label_count"] = verified_label_count
            state["github_verified_action_archived_count"] = verified_archived_count
            state["github_verified_action_archive_truncated"] = (
                verified_archive_truncated
            )

    remaining = [
        message_id
        for message_id in ordered_ids
        if (message_id, RULE_VERSION) not in decisions
    ]
    if args.dry_run:
        remaining = pending_ids[len(attempted_ids) :]
    state["remaining_count"] = len(remaining)

    current_rule_decisions = [
        value for (message_id, version), value in decisions.items() if version == RULE_VERSION
    ]
    state["total_decision_count"] = len(current_rule_decisions)
    state["total_action_queue_count"] = sum(
        1 for _, version in action_queue_keys if version == RULE_VERSION
    )
    state["total_category_counts"] = dict(
        sorted(
            Counter(
                str(item.get("classification", {}).get("category", "unknown"))
                for item in current_rule_decisions
            ).items()
        )
    )

    complete = (
        not remaining
        and not errors
        and not baseline_truncated
        and not state["github_routine_archive_truncated"]
        and not state["github_verified_action_archive_truncated"]
    )
    promote_completed_gap_scan(state, complete and not args.dry_run)
    if complete and not args.dry_run:
        if not state["bootstrap_complete"]:
            state["bootstrap_complete"] = True
            state["checkpoint_history_id"] = str(state["bootstrap_history_id"])
        else:
            state["checkpoint_history_id"] = history_latest or run_start_history_id
        state["last_success_at"] = utc_now()

    state["completed_at"] = utc_now()
    if errors:
        state["status"] = "partial_error"
    elif baseline_truncated:
        state["status"] = "partial_search_limit"
    elif state["github_routine_archive_truncated"]:
        state["status"] = "partial_archive_limit"
    elif state["github_verified_action_archive_truncated"]:
        state["status"] = "partial_archive_limit"
    elif remaining:
        state["status"] = "catching_up"
    elif args.dry_run:
        state["status"] = "dry_run"
    else:
        state["status"] = "ok"

    if not args.dry_run:
        atomic_json_write(STATE_PATH, state)
    return (
        2
        if errors
        or baseline_truncated
        or state["github_routine_archive_truncated"]
        or state["github_verified_action_archive_truncated"]
        else 0
    ), state


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-messages", type=int, default=1000)
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--search-limit", type=int, default=SEARCH_LIMIT)
    parser.add_argument("--gap-scan-interval-sec", type=int, default=21_600)
    parser.add_argument("--apply-labels", action="store_true")
    parser.add_argument("--archive-github-routine", action="store_true")
    parser.add_argument("--archive-verified-github-actions", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.max_messages <= 10_000:
        parser.error("--max-messages must be between 1 and 10000")
    if not 1 <= args.workers <= 16:
        parser.error("--workers must be between 1 and 16")
    if not 1 <= args.search_limit <= SEARCH_LIMIT:
        parser.error("--search-limit must be between 1 and 10000")
    if not 300 <= args.gap_scan_interval_sec <= 86_400:
        parser.error("--gap-scan-interval-sec must be between 300 and 86400")

    lock_handle = open(LOCK_PATH, "w", encoding="utf-8")
    try:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock_handle.close()
        print(json.dumps({"status": "skipped_lock_busy"}, sort_keys=True))
        return 0

    try:
        try:
            return_code, state = run(args)
        except Exception as exc:
            previous_state = load_json_object(STATE_PATH)
            state = {
                **previous_state,
                "schema_version": SCHEMA_VERSION,
                "rule_version": RULE_VERSION,
                "status": "error",
                "completed_at": utc_now(),
                "error_type": type(exc).__name__,
                "consecutive_failure_count": int(
                    previous_state.get("consecutive_failure_count", 0) or 0
                )
                + 1,
            }
            if not args.dry_run:
                try:
                    atomic_json_write(STATE_PATH, state)
                except Exception:
                    pass
            print(json.dumps(state, sort_keys=True), file=sys.stderr)
            return 1
        safe_output = {
            key: state.get(key)
            for key in (
                "status",
                "rule_version",
                "baseline_candidate_count",
                "history_candidate_count",
                "gap_scan_performed",
                "candidate_count",
                "already_decided_count",
                "attempted_count",
                "processed_count",
                "remaining_count",
                "error_count",
                "new_category_counts",
                "total_category_counts",
                "total_decision_count",
                "labels_added_counts",
                "github_routine_archived_count",
                "github_routine_archive_truncated",
                "github_verified_action_label_count",
                "github_verified_action_archived_count",
                "github_verified_action_archive_truncated",
                "new_action_queue_count",
                "total_action_queue_count",
                "bootstrap_complete",
                "history_checkpoint_stale",
                "completed_at",
            )
        }
        print(json.dumps(safe_output, ensure_ascii=False, sort_keys=True))
        return return_code
    finally:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
        lock_handle.close()


if __name__ == "__main__":
    raise SystemExit(main())

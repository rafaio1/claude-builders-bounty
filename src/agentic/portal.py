from __future__ import annotations

import argparse
import base64
import binascii
import getpass
import hashlib
import ipaddress
import json
import math
import mimetypes
import os
import re
import secrets
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
from http.cookies import CookieError, SimpleCookie
from pathlib import Path
from socketserver import ThreadingMixIn
from typing import Any, Callable, Iterable, Mapping
from urllib.parse import parse_qs, urlsplit
from wsgiref.simple_server import ServerHandler, WSGIRequestHandler, WSGIServer, make_server

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from argon2.low_level import Type
from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateNotFound, select_autoescape


PACKAGE_ROOT = Path(__file__).resolve().parent
DEFAULT_STATE_PATH = Path("/var/lib/agentic-portal/state.json")
COOKIE_NAME = "agentic_portal_session"
HASH_FILE = "portal_password_hash"
USERNAME_FILE = "portal_username"
DISPLAY_NAME_FILE = "portal_display_name"
SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{40,128}$")
STATIC_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,100}$")
PBKDF2_MIN_ITERATIONS = 100_000
PBKDF2_MAX_ITERATIONS = 5_000_000
SCRYPT_MIN_N = 2**14
SCRYPT_MAX_N = 2**18
MAX_STATE_BYTES = 4 * 1024 * 1024
MAX_FORM_BYTES = 16 * 1024


class PortalConfigurationError(RuntimeError):
    """Raised when the portal cannot start with secure configuration."""


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    text = str(value or "").strip()
    if not text or len(text) > 4096:
        raise PortalConfigurationError("invalid password hash encoding")
    try:
        decoded = base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
    except (binascii.Error, ValueError) as exc:
        raise PortalConfigurationError("invalid password hash encoding") from exc
    if not decoded:
        raise PortalConfigurationError("invalid password hash encoding")
    return decoded


class PasswordVerifier:
    """Verify Argon2id PHC or bounded PBKDF2/scrypt encoded hashes."""

    def __init__(self, encoded: str) -> None:
        self.encoded = str(encoded or "").strip()
        self.algorithm = ""
        self.parameters: tuple[Any, ...] = ()
        self._argon2 = PasswordHasher(
            time_cost=3,
            memory_cost=65_536,
            parallelism=1,
            hash_len=32,
            salt_len=16,
            type=Type.ID,
        )
        if self.encoded.startswith("$argon2id$"):
            try:
                # Parsing is deliberately done once at startup. A dummy verify
                # confirms the PHC string and its bounded resource parameters.
                fields = self.encoded.split("$")
                params = {
                    key: int(value)
                    for key, value in (item.split("=", 1) for item in fields[3].split(","))
                }
                memory = params.get("m", 0)
                iterations = params.get("t", 0)
                parallelism = params.get("p", 0)
                if not (8_192 <= memory <= 262_144):
                    raise ValueError("argon2 memory outside bounds")
                if not (1 <= iterations <= 10 and 1 <= parallelism <= 8):
                    raise ValueError("argon2 parameters outside bounds")
                _b64decode(fields[4])
                _b64decode(fields[5])
            except (IndexError, KeyError, ValueError, PortalConfigurationError) as exc:
                raise PortalConfigurationError("invalid Argon2id password hash") from exc
            self.algorithm = "argon2id"
            return

        fields = self.encoded.split("$")
        if fields and fields[0] == "pbkdf2_sha256" and len(fields) == 4:
            try:
                iterations = int(fields[1])
            except ValueError as exc:
                raise PortalConfigurationError("invalid PBKDF2 password hash") from exc
            if not PBKDF2_MIN_ITERATIONS <= iterations <= PBKDF2_MAX_ITERATIONS:
                raise PortalConfigurationError("PBKDF2 iterations outside safe bounds")
            salt = _b64decode(fields[2])
            digest = _b64decode(fields[3])
            if len(salt) < 16 or len(digest) != 32:
                raise PortalConfigurationError("invalid PBKDF2 password hash")
            self.algorithm = "pbkdf2_sha256"
            self.parameters = (iterations, salt, digest)
            return

        if fields and fields[0] == "scrypt" and len(fields) == 7:
            try:
                n, r, p = (int(fields[index]) for index in (1, 2, 3))
            except ValueError as exc:
                raise PortalConfigurationError("invalid scrypt password hash") from exc
            if n & (n - 1) or not SCRYPT_MIN_N <= n <= SCRYPT_MAX_N:
                raise PortalConfigurationError("scrypt N outside safe bounds")
            if not (1 <= r <= 32 and 1 <= p <= 16 and r * p <= 64):
                raise PortalConfigurationError("scrypt parameters outside safe bounds")
            salt = _b64decode(fields[4])
            digest = _b64decode(fields[5])
            # Field six is reserved for a future key identifier and must be '-'.
            if fields[6] != "-" or len(salt) < 16 or len(digest) != 32:
                raise PortalConfigurationError("invalid scrypt password hash")
            self.algorithm = "scrypt"
            self.parameters = (n, r, p, salt, digest)
            return
        raise PortalConfigurationError(
            "password hash must be Argon2id PHC, pbkdf2_sha256, or scrypt"
        )

    def verify(self, password: str) -> bool:
        candidate = str(password or "").encode("utf-8")
        if len(candidate) > 4096:
            return False
        if self.algorithm == "argon2id":
            try:
                return bool(self._argon2.verify(self.encoded, candidate))
            except (InvalidHashError, VerificationError, VerifyMismatchError):
                return False
        if self.algorithm == "pbkdf2_sha256":
            iterations, salt, expected = self.parameters
            actual = hashlib.pbkdf2_hmac("sha256", candidate, salt, iterations, dklen=32)
            return secrets.compare_digest(actual, expected)
        n, r, p, salt, expected = self.parameters
        maxmem = min(256 * 1024 * 1024, max(32 * 1024 * 1024, 256 * n * r))
        try:
            actual = hashlib.scrypt(
                candidate, salt=salt, n=n, r=r, p=p, dklen=32, maxmem=maxmem
            )
        except ValueError:
            return False
        return secrets.compare_digest(actual, expected)


def hash_password(
    password: str,
    *,
    algorithm: str = "argon2id",
    iterations: int = 600_000,
    salt: bytes | None = None,
) -> str:
    """Create a portal password hash; plaintext is never persisted."""

    candidate = str(password or "")
    if not candidate:
        raise ValueError("password must not be empty")
    if algorithm == "argon2id":
        return PasswordHasher(
            time_cost=3,
            memory_cost=65_536,
            parallelism=1,
            hash_len=32,
            salt_len=16,
            type=Type.ID,
        ).hash(candidate)
    salt = salt or secrets.token_bytes(16)
    if len(salt) < 16:
        raise ValueError("salt must contain at least 16 bytes")
    if algorithm == "pbkdf2_sha256":
        if not PBKDF2_MIN_ITERATIONS <= iterations <= PBKDF2_MAX_ITERATIONS:
            raise ValueError("PBKDF2 iterations outside safe bounds")
        digest = hashlib.pbkdf2_hmac(
            "sha256", candidate.encode("utf-8"), salt, iterations, dklen=32
        )
        return f"pbkdf2_sha256${iterations}${_b64encode(salt)}${_b64encode(digest)}"
    if algorithm == "scrypt":
        n, r, p = SCRYPT_MIN_N, 8, 1
        digest = hashlib.scrypt(
            candidate.encode("utf-8"),
            salt=salt,
            n=n,
            r=r,
            p=p,
            dklen=32,
            maxmem=64 * 1024 * 1024,
        )
        return f"scrypt${n}${r}${p}${_b64encode(salt)}${_b64encode(digest)}$-"
    raise ValueError(f"unsupported password algorithm: {algorithm}")


def _credential(directory: Path | None, name: str, *, max_bytes: int = 16_384) -> str:
    if directory is None:
        return ""
    root = directory.resolve()
    candidate = directory / name
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
        if not resolved.is_file() or resolved.stat().st_size > max_bytes:
            return ""
        return resolved.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError, ValueError):
        return ""


@dataclass(frozen=True)
class PortalConfig:
    state_path: Path
    password_hash: str
    username: str = "rafaio"
    display_name: str = "Rafaio"
    host: str = "127.0.0.1"
    port: int = 8767
    cookie_secure: bool = False
    session_ttl_seconds: int = 28_800
    preauth_ttl_seconds: int = 600
    login_attempts: int = 5
    login_window_seconds: int = 300
    template_dir: Path = PACKAGE_ROOT / "portal_templates"
    static_dir: Path = PACKAGE_ROOT / "portal_static"
    worker_model: str = ""
    orchestrator_model: str = ""
    allowed_hosts: tuple[str, ...] = ()
    inbox_path: Path = Path("/var/lib/agentic-portal/inbox.jsonl")

    @classmethod
    def from_environment(cls) -> "PortalConfig":
        """Load only portal-specific values; never load the project's main .env."""

        credentials_raw = os.getenv("CREDENTIALS_DIRECTORY", "").strip()
        credentials = Path(credentials_raw) if credentials_raw else None
        encoded = _credential(credentials, HASH_FILE) or os.getenv(
            "AGENTIC_PORTAL_PASSWORD_HASH", ""
        ).strip()
        username = (
            _credential(credentials, USERNAME_FILE, max_bytes=256)
            or os.getenv("AGENTIC_PORTAL_USERNAME", "rafaio").strip()
        )
        display_name = (
            _credential(credentials, DISPLAY_NAME_FILE, max_bytes=256)
            or os.getenv("AGENTIC_PORTAL_DISPLAY_NAME", username).strip()
        )
        state = Path(
            os.getenv("AGENTIC_PORTAL_STATE_PATH", str(DEFAULT_STATE_PATH)).strip()
        )
        host = os.getenv("AGENTIC_PORTAL_HOST", "127.0.0.1").strip()
        try:
            port = int(os.getenv("AGENTIC_PORTAL_PORT", "8767"))
        except ValueError as exc:
            raise PortalConfigurationError("invalid portal port") from exc
        if not 1 <= port <= 65_535:
            raise PortalConfigurationError("invalid portal port")
        if not encoded:
            raise PortalConfigurationError(
                f"missing {HASH_FILE} credential or AGENTIC_PORTAL_PASSWORD_HASH"
            )
        if not re.fullmatch(r"[A-Za-z0-9_.@-]{1,128}", username):
            raise PortalConfigurationError("invalid portal username")
        secure = os.getenv("AGENTIC_PORTAL_COOKIE_SECURE", "").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        allowed_hosts: list[str] = []
        for item in os.getenv("AGENTIC_PORTAL_ALLOWED_HOSTS", "").split(","):
            candidate = item.strip().lower()
            if not candidate:
                continue
            try:
                ipaddress.ip_address(candidate)
            except ValueError:
                if not re.fullmatch(
                    r"(?=.{1,253}\Z)[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?",
                    candidate,
                ):
                    raise PortalConfigurationError("invalid portal allowed host")
            if candidate not in allowed_hosts:
                allowed_hosts.append(candidate)
        return cls(
            state_path=state,
            password_hash=encoded,
            username=username,
            display_name=display_name[:128] or username,
            host=host,
            port=port,
            cookie_secure=secure,
            worker_model=_safe_model(os.getenv("GHOSTCLI_MODEL", "")),
            orchestrator_model=_safe_model(
                os.getenv("GHOSTCLI_ORCHESTRATOR_MODEL", "")
            ),
            allowed_hosts=tuple(allowed_hosts),
            inbox_path=Path(
                os.getenv(
                    "AGENTIC_PORTAL_INBOX_PATH",
                    "/var/lib/agentic-portal/inbox.jsonl",
                ).strip()
                or "/var/lib/agentic-portal/inbox.jsonl"
            ),
        )


def _safe_model(value: str) -> str:
    text = str(value or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9._+\-\[\]]{1,100}", text):
        return ""
    return text


@dataclass
class _Session:
    session_id: str
    csrf_token: str
    username: str | None
    authenticated: bool
    created_at: float
    expires_at: float
    last_seen: float


class SessionStore:
    def __init__(
        self,
        *,
        auth_ttl: int = 28_800,
        preauth_ttl: int = 600,
        max_sessions: int = 2_048,
        time_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        self.auth_ttl = max(300, min(int(auth_ttl), 86_400))
        self.preauth_ttl = max(60, min(int(preauth_ttl), 1_800))
        self.max_sessions = max(32, min(int(max_sessions), 16_384))
        self.time_fn = time_fn
        self._sessions: dict[str, _Session] = {}
        self._lock = threading.RLock()

    def create(self, *, username: str | None = None, authenticated: bool = False) -> _Session:
        now = self.time_fn()
        ttl = self.auth_ttl if authenticated else self.preauth_ttl
        session = _Session(
            session_id=secrets.token_urlsafe(32),
            csrf_token=secrets.token_urlsafe(32),
            username=username if authenticated else None,
            authenticated=authenticated,
            created_at=now,
            expires_at=now + ttl,
            last_seen=now,
        )
        with self._lock:
            self._purge(now)
            if len(self._sessions) >= self.max_sessions:
                oldest = min(self._sessions.values(), key=lambda item: item.last_seen)
                self._sessions.pop(oldest.session_id, None)
            self._sessions[session.session_id] = session
        return session

    def get(self, session_id: str | None) -> _Session | None:
        if not session_id or not SESSION_ID_RE.fullmatch(session_id):
            return None
        now = self.time_fn()
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            if session.expires_at <= now:
                self._sessions.pop(session_id, None)
                return None
            session.last_seen = now
            return session

    def rotate_authenticated(self, old_session_id: str, username: str) -> _Session:
        with self._lock:
            self._sessions.pop(old_session_id, None)
        return self.create(username=username, authenticated=True)

    def destroy(self, session_id: str | None) -> None:
        if not session_id:
            return
        with self._lock:
            self._sessions.pop(session_id, None)

    def _purge(self, now: float) -> None:
        expired = [
            key for key, session in self._sessions.items() if session.expires_at <= now
        ]
        for key in expired:
            self._sessions.pop(key, None)


class LoginRateLimiter:
    def __init__(
        self,
        *,
        attempts: int = 5,
        window_seconds: int = 300,
        max_keys: int = 2_048,
        time_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        self.attempts = max(1, min(int(attempts), 20))
        self.window = max(30, min(int(window_seconds), 3_600))
        self.max_keys = max(32, min(int(max_keys), 16_384))
        self.time_fn = time_fn
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def consume(self, key: str) -> tuple[bool, int]:
        now = self.time_fn()
        normalized = str(key or "unknown")[:128]
        with self._lock:
            events = self._events[normalized]
            cutoff = now - self.window
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= self.attempts:
                return False, max(1, math.ceil(self.window - (now - events[0])))
            events.append(now)
            if len(self._events) > self.max_keys:
                self._purge(now)
            return True, 0

    def reset(self, key: str) -> None:
        with self._lock:
            self._events.pop(str(key or "unknown")[:128], None)

    def _purge(self, now: float) -> None:
        cutoff = now - self.window
        stale = [
            key for key, events in self._events.items() if not events or events[-1] <= cutoff
        ]
        for key in stale:
            self._events.pop(key, None)
        while len(self._events) > self.max_keys:
            self._events.pop(next(iter(self._events)))


def _text(value: Any, limit: int = 500) -> str:
    text = str(value or "")
    text = "".join(character for character in text if character >= " " or character in "\t\n")
    text = re.sub(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+", "Bearer [redacted]", text)
    text = re.sub(
        r"(?i)\b(authorization|api[_ -]?key|access[_ -]?token|password|secret)"
        r"\s*[:=]\s*[^\s,;]+",
        lambda match: f"{match.group(1)}=[redacted]",
        text,
    )
    return text[:limit]


def _integer(value: Any, *, minimum: int = 0, maximum: int = 10_000_000) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return minimum
    return min(maximum, max(minimum, number))


def _safe_report_url(value: Any) -> str:
    text = _text(value, 300)
    if not text:
        return ""
    parsed = urlsplit(text)
    if (
        parsed.scheme == "https"
        and parsed.hostname in {"hackerone.com", "www.hackerone.com"}
        and re.fullmatch(r"/reports/[0-9]+/?", parsed.path)
        and not parsed.username
        and not parsed.password
    ):
        return text
    return ""


def _safe_missing(value: Any) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if not isinstance(value, list):
        return rows
    for item in value[:20]:
        if isinstance(item, dict):
            rows.append(
                {
                    "section": _text(item.get("section"), 80),
                    "reason": _text(item.get("reason"), 300),
                }
            )
        else:
            rows.append({"section": _text(item, 80), "reason": ""})
    return rows


def _sanitize_stats(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    return {
        "programs_total": _integer(source.get("programs_total")),
        "findings_total": _integer(source.get("findings_total")),
        "reports_ready": _integer(source.get("reports_ready")),
        "submissions_total": _integer(source.get("submissions_total")),
        "engine_status": _text(source.get("engine_status") or "Em observação", 80),
        "last_run": _text(source.get("last_run") or "Aguardando dados", 100),
        "last_run_iso": _text(source.get("last_run_iso"), 50),
        "next_action": _text(source.get("next_action") or "Aguardar autorização comercial", 160),
        "cash_brl": _integer(source.get("cash_brl")),
        "offers_total": _integer(source.get("offers_total") or source.get("programs_total")),
        "paused": _text(source.get("paused") or "não", 20),
        "fiscal_destination": _text(source.get("fiscal_destination"), 40),
        "fiscal_government_payment": False,
    }


def _sanitize_findings(value: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not isinstance(value, list):
        return rows
    for item in value[:100]:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "id": _integer(item.get("id")),
                "title": _text(item.get("title") or "Relatório sem título", 240),
                "program": _text(item.get("program") or item.get("handle"), 200),
                "severity": _text(item.get("severity") or "Não definida", 30),
                "status": _text(item.get("status") or "Em revisão", 40),
                "updated_at": _text(item.get("updated_at") or "—", 100),
                "updated_at_iso": _text(item.get("updated_at_iso"), 50),
            }
        )
    return rows


def _sanitize_activity(value: Any) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if not isinstance(value, list):
        return rows
    for item in value[:100]:
        if not isinstance(item, dict):
            continue
        status = _text(item.get("status") or "info", 20).lower()
        if status not in {"success", "warning", "muted", "info"}:
            status = "info"
        rows.append(
            {
                "title": _text(item.get("title") or "Evento registrado", 160),
                "detail": _text(item.get("detail") or "Sem detalhes adicionais.", 500),
                "time": _text(item.get("time") or "—", 100),
                "datetime": _text(item.get("datetime"), 50),
                "status": status,
            }
        )
    return rows


def _sanitize_programs(value: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not isinstance(value, list):
        return rows
    for item in value[:200]:
        if not isinstance(item, dict):
            continue
        handle = _text(item.get("handle"), 200)
        name = _text(item.get("name") or handle or "Programa", 200)
        rows.append(
            {
                "handle": handle,
                "name": name,
                "initial": _text(item.get("initial") or name[:1].upper(), 3),
                "status": _text(item.get("status") or "Monitorado", 50),
                "findings": _integer(item.get("findings")),
                "reports": _integer(item.get("reports")),
                "last_seen": _text(item.get("last_seen") or "—", 100),
                "last_seen_iso": _text(item.get("last_seen_iso"), 50),
            }
        )
    return rows


def _sanitize_reports(value: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not isinstance(value, list):
        return rows
    for item in value[:200]:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "id": _integer(item.get("id")),
                "program": _text(item.get("program") or item.get("handle"), 200),
                "title": _text(item.get("title"), 240),
                "report_kind": _text(item.get("report_kind"), 40),
                "severity": _text(item.get("severity"), 30),
                "summary": _text(item.get("summary"), 1_000),
                "ready_to_submit": bool(item.get("ready_to_submit")),
                "status": _text(item.get("status"), 40),
                "started_at": _text(item.get("started_at"), 50),
                "validation": {
                    "passed": bool((item.get("validation") or {}).get("passed")),
                    "score": _integer((item.get("validation") or {}).get("score"), maximum=100),
                    "summary": _text((item.get("validation") or {}).get("summary"), 500),
                    "missing": _safe_missing((item.get("validation") or {}).get("missing")),
                }
                if isinstance(item.get("validation"), dict)
                else {},
                "review": {
                    "verdict": _text((item.get("review") or {}).get("verdict"), 30),
                    "return_to": _text((item.get("review") or {}).get("return_to"), 30),
                    "reason": _text((item.get("review") or {}).get("reason"), 500),
                    "missing": [
                        _text(entry, 200)
                        for entry in ((item.get("review") or {}).get("missing") or [])[:20]
                    ],
                }
                if isinstance(item.get("review"), dict)
                else {},
                "blockers": [_text(entry, 300) for entry in (item.get("blockers") or [])[:20]],
            }
        )
    return rows


def _sanitize_submissions(value: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not isinstance(value, list):
        return rows
    for item in value[:200]:
        if not isinstance(item, dict):
            continue
        report_id = _text(item.get("h1_report_id"), 40)
        if report_id and not report_id.isdigit():
            report_id = ""
        rows.append(
            {
                "id": _integer(item.get("id")),
                "program": _text(item.get("program") or item.get("handle"), 200),
                "report_pack_id": _integer(item.get("report_pack_id")),
                "status": _text(item.get("status"), 40),
                "review_verdict": _text(item.get("review_verdict"), 30),
                "return_to": _text(item.get("return_to"), 30),
                "h1_report_id": report_id,
                "h1_report_url": _safe_report_url(item.get("h1_report_url")),
                "code": _text(item.get("code"), 80),
                "retryable": bool(item.get("retryable")),
                "created_at": _text(item.get("created_at"), 50),
            }
        )
    return rows


def _sanitize_heartbeat(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    pipeline_source = source.get("pipeline") if isinstance(source.get("pipeline"), dict) else {}
    pipeline = {
        key: _integer(pipeline_source.get(key))
        for key in (
            "missing_intel",
            "missing_intel_huntable",
            "open_not_huntable",
            "empty_scope",
            "skipped_details",
            "missing_plan",
            "queued",
            "blocked",
            "submitted",
            "revised",
            "unconfirmed",
        )
    }
    return {
        "status": _text(source.get("status") or "unavailable", 30),
        "engine_status": _text(source.get("engine_status") or "unknown", 50),
        "generated_at": _text(source.get("generated_at"), 50),
        "updated_at": _text(source.get("updated_at"), 50),
        "age_seconds": _integer(source.get("age_seconds"), maximum=31_536_000),
        "last_activity": _text(source.get("last_activity"), 50),
        "pipeline": pipeline,
    }


def _sanitize_models(value: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not isinstance(value, list):
        return rows
    for item in value[:20]:
        if not isinstance(item, dict):
            continue
        name = _safe_model(item.get("name"))
        if not name:
            continue
        rows.append(
            {
                "name": name,
                "uses": _integer(item.get("uses")),
                "last_used_at": _text(item.get("last_used_at"), 50),
            }
        )
    return rows


def _sanitize_improve(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    counts_source = source.get("counts") if isinstance(source.get("counts"), dict) else {}
    census_source = source.get("census") if isinstance(source.get("census"), dict) else {}
    counts = {
        key: _integer(counts_source.get(key))
        for key in (
            "total",
            "pending",
            "developing",
            "in_review",
            "applied",
            "rejected",
            "blocked",
            "active",
        )
    }
    proposals: list[dict[str, Any]] = []
    raw_proposals = source.get("proposals")
    if isinstance(raw_proposals, list):
        for item in raw_proposals[:40]:
            if not isinstance(item, dict):
                continue
            proposal_id = _text(item.get("id"), 80)
            if not re.fullmatch(r"imp-[a-z0-9-]{1,72}", proposal_id):
                continue
            kind = _text(item.get("kind") or "improvement", 20).lower()
            if kind not in {"bottleneck", "improvement"}:
                kind = "improvement"
            status = _text(item.get("status") or "pending", 20).lower()
            if status not in {
                "pending",
                "developing",
                "in_review",
                "applied",
                "rejected",
                "blocked",
            }:
                status = "pending"
            kind_label = _text(
                item.get("kind_label")
                or ("Gargalo" if kind == "bottleneck" else "Melhoria"),
                40,
            )
            theme = _text(item.get("theme") or "engine", 20).lower()
            if theme not in {"engine", "portal", "ai", "tools"}:
                theme = "engine"
            theme_label = _text(
                item.get("theme_label")
                or {
                    "engine": "Motor",
                    "portal": "Portal",
                    "ai": "IA",
                    "tools": "Ferramentas",
                }[theme],
                40,
            )
            status_label = _text(item.get("status_label") or status, 40)
            files_hint = [
                _text(path, 120)
                for path in (item.get("files_hint") or [])
                if str(path).strip()
            ][:6]
            never = [
                _text(entry, 160)
                for entry in (item.get("never") or [])
                if str(entry).strip()
            ][:6]
            proposals.append(
                {
                    "id": proposal_id,
                    "title": _text(item.get("title") or "Feature sem título", 160),
                    "kind": kind,
                    "kind_label": kind_label,
                    "theme": theme,
                    "theme_label": theme_label,
                    "priority": _integer(item.get("priority") or 3, minimum=1, maximum=5),
                    "status": status,
                    "status_label": status_label,
                    "rationale": _text(item.get("rationale"), 400),
                    "change": _text(item.get("change"), 400),
                    "never": [entry for entry in never if entry],
                    "files_hint": [path for path in files_hint if path],
                    "branch": _text(item.get("branch"), 80),
                    "map_id": _text(item.get("map_id"), 40),
                }
            )
    return {
        "updated_at": _text(source.get("updated_at"), 50),
        "map_id": _text(source.get("map_id"), 40),
        "summary": _text(source.get("summary"), 400),
        "counts": counts,
        "census": {
            key: _integer(census_source.get(key))
            for key in (
                "open_programs",
                "huntable_open",
                "huntable_without_intel",
                "huntable_intel_without_plan",
                "open_empty_scopes",
                "missing_intel",
                "missing_intel_huntable",
                "open_not_huntable",
                "empty_scope",
                "skipped_details",
                "missing_plan",
                "playwright",
                "ghostcli",
                "bybit_key",
            )
        },
        "proposals": proposals,
    }


def _sanitize_integrity(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    status = _text(source.get("status") or "missing", 20).lower()
    if status not in {"missing", "ok", "failed"}:
        status = "missing"
    failed: list[str] = []
    for item in source.get("failed") or []:
        check_id = _text(item, 40).lower()
        if re.fullmatch(r"[a-z][a-z0-9_]{0,40}", check_id) and check_id not in failed:
            failed.append(check_id)
        if len(failed) >= 40:
            break
    checks: list[dict[str, Any]] = []
    raw_checks = source.get("checks")
    if isinstance(raw_checks, list):
        for item in raw_checks[:40]:
            if not isinstance(item, dict):
                continue
            check_id = _text(item.get("id"), 40).lower()
            if not re.fullmatch(r"[a-z][a-z0-9_]{0,40}", check_id):
                continue
            checks.append(
                {
                    "id": check_id,
                    "ok": bool(item.get("ok")),
                    "detail": _text(item.get("detail"), 400),
                }
            )
    ok = status != "failed"
    return {
        "ok": ok,
        "status": status,
        "generated_at": _text(source.get("generated_at"), 50),
        "summary": _text(source.get("summary"), 400),
        "failed": failed,
        "checks": checks,
        "total": _integer(source.get("total") or len(checks), maximum=40),
    }


def _sanitize_ai_eval(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    status = _text(source.get("status") or "missing", 20).lower()
    if status not in {"missing", "ok", "failed"}:
        status = "missing"
    cases: list[dict[str, Any]] = []
    raw_cases = source.get("cases")
    if isinstance(raw_cases, list):
        for item in raw_cases[:20]:
            if not isinstance(item, dict):
                continue
            case_id = _text(item.get("id"), 60).lower()
            if not re.fullmatch(r"[a-z][a-z0-9-]{0,60}", case_id):
                continue
            cases.append(
                {
                    "id": case_id,
                    "ok": bool(item.get("ok")),
                    "detail": _text(item.get("detail"), 200),
                }
            )
    return {
        "ok": status != "failed",
        "status": status,
        "generated_at": _text(source.get("generated_at"), 50),
        "summary": _text(source.get("summary"), 400),
        "passed": _integer(source.get("passed") or sum(1 for item in cases if item["ok"]), maximum=40),
        "failed": _integer(source.get("failed"), maximum=40),
        "total": _integer(source.get("total") or len(cases), maximum=40),
        "cases": cases,
    }


def _sanitize_messages(value: Any) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if not isinstance(value, list):
        return rows
    for item in value[-80:]:
        if not isinstance(item, dict):
            continue
        role = _text(item.get("role") or "owner", 20).lower()
        if role not in {"owner", "agent"}:
            role = "owner"
        ident = _text(item.get("id"), 40)
        if ident and not re.fullmatch(r"[A-Za-z0-9_-]{6,40}", ident):
            ident = ident[:16]
        rows.append(
            {
                "id": ident,
                "role": role,
                "author": _text(item.get("author") or ("rafaio" if role == "owner" else "ARO"), 40),
                "body": _text(item.get("body") or item.get("text"), 2_000),
                "time": _text(item.get("time") or item.get("at"), 100),
                "datetime": _text(item.get("datetime") or item.get("at"), 50),
            }
        )
    return [row for row in rows if row["body"]]


def _sanitize_codex_terminals(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    terminals: list[dict[str, Any]] = []
    raw_terminals = source.get("terminals")
    if isinstance(raw_terminals, list):
        for item in raw_terminals[:20]:
            if not isinstance(item, dict):
                continue
            status = _text(item.get("status") or "waiting", 20).lower()
            if status not in {"running", "waiting", "stopped", "failed"}:
                status = "waiting"
            provider = _text(item.get("provider") or "ghostcli", 40).lower()
            if provider not in {"ghostcli", "ghostcli2"}:
                provider = "ghostcli"
            logs = []
            for line in item.get("logs") or []:
                logs.append(_text(line, 500))
                if len(logs) >= 5:
                    break
            terminals.append(
                {
                    "name": _text(item.get("name") or "Terminal Codex", 100),
                    "handle": _text(item.get("handle"), 100),
                    "worktree": _text(item.get("worktree") or "/Agentic", 200),
                    "provider": provider,
                    "status": status,
                    "logs": logs,
                }
            )
    return {
        "generated_at": _text(source.get("generated_at"), 80),
        "host": _text(source.get("host"), 100),
        "gateway": _text(source.get("gateway"), 100),
        "model": _text(source.get("model"), 100),
        "terminals": terminals,
    }


def sanitize_state(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    schema_version = _integer(source.get("schema_version"), maximum=10)
    if schema_version != 1:
        raise ValueError("unsupported portal state schema")
    reports = _sanitize_reports(source.get("reports"))
    findings = _sanitize_findings(source.get("findings"))
    if not findings and reports:
        findings = _sanitize_findings(reports)
    if not reports and findings:
        reports = _sanitize_reports(findings)
    return {
        "schema_version": schema_version,
        "generated_at": _text(source.get("generated_at"), 50),
        "stats": _sanitize_stats(source.get("stats")),
        "findings": findings,
        "activity": _sanitize_activity(source.get("activity")),
        "programs": _sanitize_programs(source.get("programs")),
        "reports": reports,
        "submissions": _sanitize_submissions(source.get("submissions")),
        "heartbeat": _sanitize_heartbeat(source.get("heartbeat")),
        "modelos": _sanitize_models(source.get("modelos")),
        "improve": _sanitize_improve(source.get("improve")),
        "integrity": _sanitize_integrity(source.get("integrity")),
        "ai_eval": _sanitize_ai_eval(source.get("ai_eval")),
        "messages": _sanitize_messages(source.get("messages")),
        "codex_terminals": _sanitize_codex_terminals(source.get("codex_terminals")),
    }


def empty_state() -> dict[str, Any]:
    return sanitize_state(
        {
            "schema_version": 1,
            "stats": {},
            "findings": [],
            "activity": [],
            "programs": [],
            "reports": [],
            "submissions": [],
            "heartbeat": {"status": "unavailable", "engine_status": "unknown"},
            "modelos": [],
            "improve": {},
            "integrity": {},
            "ai_eval": {},
            "messages": [],
            "codex_terminals": {},
        }
    )


class StateStore:
    """Read an immutable, sanitized snapshot without access to the source SQLite DB."""

    def __init__(self, path: Path, *, max_bytes: int = MAX_STATE_BYTES) -> None:
        self.path = Path(path)
        self.max_bytes = max(1_024, min(int(max_bytes), 32 * 1024 * 1024))
        self._signature: tuple[int, int, int] | None = None
        self._cached: dict[str, Any] | None = None
        self._lock = threading.RLock()

    def load(self) -> dict[str, Any]:
        with self._lock:
            try:
                flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
                descriptor = os.open(self.path, flags)
                try:
                    metadata = os.fstat(descriptor)
                    signature = (metadata.st_ino, metadata.st_mtime_ns, metadata.st_size)
                    if metadata.st_size <= 0 or metadata.st_size > self.max_bytes:
                        raise ValueError("portal state size outside bounds")
                    if self._cached is not None and signature == self._signature:
                        return self._cached
                    chunks: list[bytes] = []
                    remaining = self.max_bytes + 1
                    while remaining > 0:
                        chunk = os.read(descriptor, min(65_536, remaining))
                        if not chunk:
                            break
                        chunks.append(chunk)
                        remaining -= len(chunk)
                    raw = b"".join(chunks)
                finally:
                    os.close(descriptor)
                if len(raw) > self.max_bytes:
                    raise ValueError("portal state size outside bounds")
                parsed = json.loads(raw.decode("utf-8"))
                state = sanitize_state(parsed)
                self._cached = state
                self._signature = signature
                return state
            except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
                return self._cached or empty_state()


class InboxStore:
    """Append-only owner messages. Portal never reads the Agentic git tree."""

    def __init__(self, path: Path, *, max_bytes: int = 512 * 1024) -> None:
        self.path = Path(path)
        self.max_bytes = max(4_096, min(int(max_bytes), 2 * 1024 * 1024))
        self._lock = threading.Lock()

    def append(self, *, username: str, body: str) -> dict[str, str]:
        text = _text(body, 2_000).strip()
        if len(text) < 2:
            raise ValueError("mensagem vazia")
        row = {
            "id": secrets.token_urlsafe(12),
            "role": "owner",
            "author": _text(username, 40) or "rafaio",
            "body": text,
            "at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        }
        payload = json.dumps(row, ensure_ascii=False) + "\n"
        encoded = payload.encode("utf-8")
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            size = self.path.stat().st_size if self.path.is_file() else 0
            if size + len(encoded) > self.max_bytes:
                raise ValueError("caixa de mensagens cheia")
            flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_CLOEXEC", 0)
            descriptor = os.open(self.path, flags, 0o660)
            try:
                os.write(descriptor, encoded)
            finally:
                os.close(descriptor)
        return row


@dataclass
class Response:
    status: str
    body: bytes
    headers: list[tuple[str, str]]


def _json_response(payload: Any, status: str = "200 OK") -> Response:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return Response(status, body, [("Content-Type", "application/json; charset=utf-8")])


def _html_response(body: str, status: str = "200 OK") -> Response:
    return Response(
        status,
        body.encode("utf-8"),
        [("Content-Type", "text/html; charset=utf-8")],
    )


def _redirect(location: str, *, headers: Iterable[tuple[str, str]] = ()) -> Response:
    return Response(
        "303 See Other",
        b"",
        [("Location", location), *list(headers)],
    )


class PortalApp:
    """Authenticated read-only WSGI portal backed only by a sanitized JSON state."""

    def __init__(
        self,
        config: PortalConfig,
        *,
        state_store: StateStore | None = None,
        sessions: SessionStore | None = None,
        rate_limiter: LoginRateLimiter | None = None,
    ) -> None:
        self.config = config
        self.verifier = PasswordVerifier(config.password_hash)
        self.state_store = state_store or StateStore(config.state_path)
        self.inbox = InboxStore(config.inbox_path)
        self.sessions = sessions or SessionStore(
            auth_ttl=config.session_ttl_seconds,
            preauth_ttl=config.preauth_ttl_seconds,
        )
        self.rate_limiter = rate_limiter or LoginRateLimiter(
            attempts=config.login_attempts,
            window_seconds=config.login_window_seconds,
        )
        self.templates = Environment(
            loader=FileSystemLoader(str(config.template_dir)),
            autoescape=select_autoescape(("html", "xml"), default=True),
            undefined=StrictUndefined,
            auto_reload=False,
            enable_async=False,
        )

    def __call__(self, environ: Mapping[str, Any], start_response: Callable[..., Any]) -> list[bytes]:
        try:
            response = self._dispatch(environ)
        except Exception:
            # No exception details, paths, SQL, environment, or credentials reach clients.
            response = _html_response(
                "<!doctype html><meta charset=utf-8><title>Erro</title>"
                "<h1>Falha interna do portal</h1>",
                "500 Internal Server Error",
            )
        method = str(environ.get("REQUEST_METHOD") or "GET").upper()
        body = b"" if method == "HEAD" else response.body
        headers = self._secure_headers(response.headers)
        headers.append(("Content-Length", str(len(body))))
        start_response(response.status, headers)
        return [body]

    def _dispatch(self, environ: Mapping[str, Any]) -> Response:
        if not self._host_allowed(environ):
            return _html_response("<h1>Requisição inválida</h1>", "400 Bad Request")
        method = str(environ.get("REQUEST_METHOD") or "GET").upper()
        path = str(environ.get("PATH_INFO") or "/")
        if method not in {"GET", "HEAD", "POST"}:
            return Response(
                "405 Method Not Allowed",
                b"",
                [("Allow", "GET, HEAD, POST")],
            )
        if path == "/healthz" and method in {"GET", "HEAD"}:
            return _json_response({"status": "ok"})
        if path.startswith("/static/") and method in {"GET", "HEAD"}:
            return self._static(path.removeprefix("/static/"))
        if path == "/login":
            if method in {"GET", "HEAD"}:
                return self._login_page(environ)
            if method == "POST":
                return self._login(environ)
        if path == "/logout" and method == "POST":
            return self._logout(environ)
        session = self._request_session(environ)
        if not session or not session.authenticated:
            if path.startswith("/api/") or path == "/message":
                return _json_response({"error": "authentication_required"}, "401 Unauthorized")
            return _redirect("/login")
        if path == "/message" and method == "POST":
            return self._post_message(environ, session)
        if method not in {"GET", "HEAD"}:
            return Response("405 Method Not Allowed", b"", [("Allow", "GET, HEAD, POST")])
        if path == "/":
            return self._dashboard(session)
        if path == "/api/status":
            state = self.state_store.load()
            return _json_response(
                {
                    "generated_at": state["generated_at"],
                    "stats": state["stats"],
                    "heartbeat": state["heartbeat"],
                    "models": self._models(state),
                    "improve": {
                        "updated_at": state["improve"].get("updated_at", ""),
                        "summary": state["improve"].get("summary", ""),
                        "counts": state["improve"].get("counts", {}),
                        "census": state["improve"].get("census", {}),
                    },
                    "integrity": {
                        "ok": state["integrity"].get("ok", True),
                        "status": state["integrity"].get("status", "missing"),
                        "generated_at": state["integrity"].get("generated_at", ""),
                        "summary": state["integrity"].get("summary", ""),
                        "failed": state["integrity"].get("failed", []),
                    },
                    "ai_eval": {
                        "ok": state["ai_eval"].get("ok", True),
                        "status": state["ai_eval"].get("status", "missing"),
                        "summary": state["ai_eval"].get("summary", ""),
                        "passed": state["ai_eval"].get("passed", 0),
                        "failed": state["ai_eval"].get("failed", 0),
                        "total": state["ai_eval"].get("total", 0),
                    },
                }
            )
        if path == "/api/reports":
            return _json_response({"reports": self.state_store.load()["reports"]})
        match = re.fullmatch(r"/api/reports/([1-9][0-9]{0,18})", path)
        if match:
            report_id = int(match.group(1))
            report = next(
                (
                    item
                    for item in self.state_store.load()["reports"]
                    if item.get("id") == report_id
                ),
                None,
            )
            if report is None:
                return _json_response({"error": "not_found"}, "404 Not Found")
            return _json_response({"report": report})
        if path == "/api/submissions":
            state = self.state_store.load()
            pipeline = state["heartbeat"].get("pipeline") or {}
            activity = [
                item
                for item in state["activity"]
                if any(
                    marker in f"{item.get('title', '')} {item.get('detail', '')}".lower()
                    for marker in ("submiss", "envio", "report")
                )
            ][:20]
            return _json_response(
                {
                    "total": state["stats"]["submissions_total"],
                    "by_status": {
                        key: _integer(pipeline.get(key))
                        for key in ("queued", "blocked", "submitted", "revised")
                    },
                    "submissions": state["submissions"],
                    "recent_activity": activity,
                }
            )
        if path == "/api/improve":
            return _json_response({"improve": self.state_store.load()["improve"]})
        if path == "/api/integrity":
            return _json_response({"integrity": self.state_store.load()["integrity"]})
        if path == "/api/eval":
            return _json_response({"ai_eval": self.state_store.load()["ai_eval"]})
        if path == "/api/heartbeat":
            state = self.state_store.load()
            heartbeat = dict(state["heartbeat"])
            heartbeat["models"] = self._models(state)
            return _json_response(heartbeat)
        if path == "/api/messages":
            return _json_response({"messages": self.state_store.load().get("messages") or []})
        if path.startswith("/api/"):
            return _json_response({"error": "not_found"}, "404 Not Found")
        return _html_response("<h1>Não encontrado</h1>", "404 Not Found")

    def _login_page(self, environ: Mapping[str, Any]) -> Response:
        existing = self._request_session(environ)
        if existing and existing.authenticated:
            return _redirect("/")
        session = existing or self.sessions.create()
        response = self._render(
            "login.html",
            self._context(session=session, user=None, error="", username=""),
        )
        if existing is None:
            response.headers.append(("Set-Cookie", self._session_cookie(session)))
        return response

    def _login(self, environ: Mapping[str, Any]) -> Response:
        session = self._request_session(environ)
        if session is None or session.authenticated:
            return _html_response("<h1>CSRF inválido</h1>", "403 Forbidden")
        form, error = self._form(environ)
        if error:
            return _html_response(f"<h1>{escape(error)}</h1>", error)
        csrf = self._single(form, "csrf_token", 256)
        if not csrf or not secrets.compare_digest(csrf, session.csrf_token):
            return _html_response("<h1>CSRF inválido</h1>", "403 Forbidden")
        remote = _text(environ.get("REMOTE_ADDR") or "unknown", 128)
        allowed, retry_after = self.rate_limiter.consume(remote)
        if not allowed:
            response = _html_response(
                "<h1>Muitas tentativas</h1><p>Tente novamente em alguns minutos.</p>",
                "429 Too Many Requests",
            )
            response.headers.append(("Retry-After", str(retry_after)))
            return response
        username = self._single(form, "username", 128)
        password = self._single(form, "password", 4_096)
        password_ok = self.verifier.verify(password)
        username_ok = secrets.compare_digest(username, self.config.username)
        if not (username_ok and password_ok):
            return self._render(
                "login.html",
                self._context(
                    session=session,
                    user=None,
                    error="Usuário ou senha inválidos.",
                    username=username,
                ),
                status="401 Unauthorized",
            )
        self.rate_limiter.reset(remote)
        authenticated = self.sessions.rotate_authenticated(
            session.session_id, self.config.username
        )
        return _redirect(
            "/", headers=[("Set-Cookie", self._session_cookie(authenticated))]
        )

    def _logout(self, environ: Mapping[str, Any]) -> Response:
        session = self._request_session(environ)
        if not session or not session.authenticated:
            return _json_response({"error": "authentication_required"}, "401 Unauthorized")
        form, error = self._form(environ)
        if error:
            return _html_response(f"<h1>{escape(error)}</h1>", error)
        csrf = self._single(form, "csrf_token", 256)
        if not csrf or not secrets.compare_digest(csrf, session.csrf_token):
            return _html_response("<h1>CSRF inválido</h1>", "403 Forbidden")
        self.sessions.destroy(session.session_id)
        return _redirect("/login", headers=[("Set-Cookie", self._clear_cookie())])

    def _post_message(self, environ: Mapping[str, Any], session: _Session) -> Response:
        if not self._origin_allowed(environ):
            return _html_response("<h1>Origem inválida</h1>", "403 Forbidden")
        form, error = self._form(environ)
        if error:
            return _html_response(f"<h1>{escape(error)}</h1>", error)
        csrf = self._single(form, "csrf_token", 256)
        if not csrf or not secrets.compare_digest(csrf, session.csrf_token):
            return _html_response("<h1>CSRF inválido</h1>", "403 Forbidden")
        body = self._single(form, "body", 2_000)
        try:
            self.inbox.append(username=session.username or self.config.username, body=body)
        except ValueError:
            return self._dashboard(session, flash="Mensagem recusada. Use texto curto, sem anexos.")
        except OSError:
            return self._dashboard(session, flash="Não foi possível gravar a mensagem neste momento.")
        return _redirect("/")

    def _dashboard(self, session: _Session, *, flash: str = "") -> Response:
        state = self.state_store.load()
        return self._render(
            "dashboard.html",
            self._context(
                session=session,
                user=self._user(),
                stats=state["stats"],
                findings=state["findings"],
                activity=state["activity"],
                programs=state["programs"],
                improve=state.get("improve") or {},
                integrity=state.get("integrity") or {},
                ai_eval=state.get("ai_eval") or {},
                messages=state.get("messages") or [],
                codex_terminals=state.get("codex_terminals") or {},
                last_activity=state["heartbeat"].get("last_activity", ""),
                flash_message=flash,
            ),
        )

    def _context(self, *, session: _Session, user: dict[str, str] | None, **extra: Any) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        context: dict[str, Any] = {
            "static_url": "/static",
            "user": user or {},
            "stats": {},
            "findings": [],
            "activity": [],
            "programs": [],
            "improve": {},
            "integrity": {},
            "ai_eval": {},
            "messages": [],
            "codex_terminals": {},
            "login_url": "/login",
            "logout_url": "/logout",
            "dashboard_url": "/",
            "csrf_token": session.csrf_token,
            "error": "",
            "flash_message": "",
            "username": "",
            "locale": "pt-BR",
            "current_year": str(now.year),
            "current_date": now.strftime("%d/%m/%Y"),
            "rendered_at": now.strftime("%d/%m/%Y %H:%M UTC"),
            "last_activity": "",
        }
        context.update(extra)
        return context

    def _user(self) -> dict[str, str]:
        words = [word for word in re.split(r"\s+", self.config.display_name) if word]
        initials = "".join(word[0] for word in words[:2]).upper() or self.config.username[:2].upper()
        return {
            "username": self.config.username,
            "display_name": self.config.display_name,
            "initials": initials[:3],
        }

    def _models(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        rows = list(state.get("modelos") or [])
        for name in (self.config.worker_model, self.config.orchestrator_model):
            if name and all(item["name"] != name for item in rows):
                rows.append({"name": name, "uses": 0, "last_used_at": ""})
        return rows

    def _render(self, name: str, context: dict[str, Any], *, status: str = "200 OK") -> Response:
        try:
            rendered = self.templates.get_template(name).render(**context)
        except TemplateNotFound:
            if name == "login.html":
                rendered = (
                    "<!doctype html><meta charset=utf-8><title>Agentic</title>"
                    f"<h1>Entrar</h1><p>{escape(str(context.get('error') or ''))}</p>"
                    "<form method=post action=/login>"
                    f"<input type=hidden name=csrf_token value=\"{escape(str(context['csrf_token']))}\">"
                    "<input name=username autocomplete=username required>"
                    "<input name=password type=password autocomplete=current-password required>"
                    "<button>Entrar</button></form>"
                )
            else:
                rendered = "<!doctype html><meta charset=utf-8><title>Agentic</title><h1>Agentic</h1>"
        return _html_response(rendered, status)

    def _static(self, name: str) -> Response:
        if not STATIC_NAME_RE.fullmatch(name):
            return _html_response("<h1>Não encontrado</h1>", "404 Not Found")
        root = self.config.static_dir.resolve()
        try:
            target = (root / name).resolve(strict=True)
            target.relative_to(root)
            if not target.is_file() or target.stat().st_size > 2 * 1024 * 1024:
                raise OSError("invalid static file")
            body = target.read_bytes()
        except (OSError, ValueError):
            return _html_response("<h1>Não encontrado</h1>", "404 Not Found")
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        return Response(
            "200 OK",
            body,
            [
                ("Content-Type", content_type),
                ("Cache-Control", "public, max-age=3600"),
            ],
        )

    def _form(self, environ: Mapping[str, Any]) -> tuple[dict[str, list[str]], str | None]:
        content_type = str(environ.get("CONTENT_TYPE") or "").split(";", 1)[0].lower()
        if content_type != "application/x-www-form-urlencoded":
            return {}, "415 Unsupported Media Type"
        raw_length = str(environ.get("CONTENT_LENGTH") or "")
        if not raw_length.isdigit():
            return {}, "411 Length Required"
        length = int(raw_length)
        if length < 0 or length > MAX_FORM_BYTES:
            return {}, "413 Content Too Large"
        stream = environ.get("wsgi.input")
        body = stream.read(length) if stream is not None else b""
        if len(body) != length:
            return {}, "400 Bad Request"
        try:
            parsed = parse_qs(
                body.decode("utf-8"),
                keep_blank_values=True,
                strict_parsing=False,
                max_num_fields=12,
            )
        except (UnicodeError, ValueError):
            return {}, "400 Bad Request"
        return parsed, None

    @staticmethod
    def _single(form: dict[str, list[str]], name: str, limit: int) -> str:
        values = form.get(name) or []
        if len(values) != 1:
            return ""
        return _text(values[0], limit)

    def _request_session(self, environ: Mapping[str, Any]) -> _Session | None:
        raw = str(environ.get("HTTP_COOKIE") or "")
        try:
            cookie = SimpleCookie()
            cookie.load(raw)
            morsel = cookie.get(COOKIE_NAME)
        except CookieError:
            return None
        return self.sessions.get(morsel.value if morsel else None)

    def _session_cookie(self, session: _Session) -> str:
        max_age = max(1, int(session.expires_at - self.sessions.time_fn()))
        flags = [
            f"{COOKIE_NAME}={session.session_id}",
            "Path=/",
            f"Max-Age={max_age}",
            "HttpOnly",
            "SameSite=Strict",
        ]
        if self.config.cookie_secure:
            flags.append("Secure")
        return "; ".join(flags)

    def _clear_cookie(self) -> str:
        flags = [
            f"{COOKIE_NAME}=",
            "Path=/",
            "Max-Age=0",
            "Expires=Thu, 01 Jan 1970 00:00:00 GMT",
            "HttpOnly",
            "SameSite=Strict",
        ]
        if self.config.cookie_secure:
            flags.append("Secure")
        return "; ".join(flags)

    def _host_allowed(self, environ: Mapping[str, Any]) -> bool:
        raw = str(environ.get("HTTP_HOST") or environ.get("SERVER_NAME") or "")
        try:
            parsed = urlsplit(f"//{raw}")
            host = parsed.hostname
            _ = parsed.port
        except ValueError:
            return False
        if not host or parsed.username or parsed.password:
            return False
        allowed = {"localhost", "127.0.0.1", "::1", *self.config.allowed_hosts}
        if self.config.host not in {"0.0.0.0", "::"}:
            allowed.add(self.config.host.lower())
        return host.lower() in allowed

    def _origin_allowed(self, environ: Mapping[str, Any]) -> bool:
        raw = str(environ.get("HTTP_ORIGIN") or "").strip()
        if not raw:
            return True
        fetch_site = str(environ.get("HTTP_SEC_FETCH_SITE") or "").lower()
        metadata_allows = fetch_site in {"same-origin", "same-site", "none"}
        try:
            parsed = urlsplit(raw)
        except ValueError:
            return metadata_allows
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
        ):
            return metadata_allows
        allowed = {"localhost", "127.0.0.1", "::1", *self.config.allowed_hosts}
        if self.config.host not in {"0.0.0.0", "::"}:
            allowed.add(self.config.host.lower())
        if parsed.hostname.lower() in allowed:
            return True
        # Some privacy/browser extensions rewrite Origin while preserving the
        # browser-controlled Fetch Metadata signal. CSRF remains mandatory.
        return metadata_allows

    def _secure_headers(self, existing: list[tuple[str, str]]) -> list[tuple[str, str]]:
        names = {name.lower() for name, _value in existing}
        headers = list(existing)
        defaults = {
            "Cache-Control": "no-store",
            "Pragma": "no-cache",
            "Content-Security-Policy": (
                "default-src 'self'; base-uri 'none'; frame-ancestors 'none'; "
                "form-action 'self'; object-src 'none'; script-src 'self'; "
                "style-src 'self'; img-src 'self' data:; connect-src 'self'"
            ),
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "no-referrer",
            "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
            "Cross-Origin-Opener-Policy": "same-origin",
            "Cross-Origin-Resource-Policy": "same-origin",
        }
        if self.config.cookie_secure:
            defaults["Strict-Transport-Security"] = "max-age=31536000"
        for name, value in defaults.items():
            if name.lower() not in names:
                headers.append((name, value))
        return headers


class ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True
    server_version = "AgenticPortal"


class PortalRequestHandler(WSGIRequestHandler):
    server_version = "AgenticPortal"
    sys_version = ""

    def address_string(self) -> str:
        return self.client_address[0]

    def version_string(self) -> str:
        return self.server_version


def create_app(config: PortalConfig | None = None) -> PortalApp:
    return PortalApp(config or PortalConfig.from_environment())


def _loopback_host(host: str) -> bool:
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Portal local autenticado do Agentic/ARO")
    parser.add_argument("--host", help="Bind HTTP (padrão 127.0.0.1)")
    parser.add_argument("--port", type=int, help="Porta HTTP (padrão 8767)")
    parser.add_argument("--state", type=Path, help="Snapshot JSON sanitizado")
    parser.add_argument(
        "--allow-remote",
        action="store_true",
        help="Permite bind não-loopback; requer TLS ou --allow-insecure-http explícito",
    )
    parser.add_argument(
        "--allow-insecure-http",
        action="store_true",
        help="Aceita HTTP remoto sem cookie Secure; use apenas por decisão explícita",
    )
    parser.add_argument(
        "--generate-password-hash",
        action="store_true",
        help="Gera Argon2id PHC sem iniciar o servidor",
    )
    args = parser.parse_args(argv)
    if args.generate_password_hash:
        first = getpass.getpass("Senha do portal: ")
        second = getpass.getpass("Confirme a senha: ")
        if first != second:
            parser.error("as senhas não coincidem")
        if len(first) < 10:
            parser.error("use pelo menos 10 caracteres")
        print(hash_password(first, algorithm="argon2id"))
        return 0
    config = PortalConfig.from_environment()
    if args.host:
        config = dataclass_replace(config, host=args.host)
    if args.port:
        if not 1 <= args.port <= 65_535:
            parser.error("porta inválida")
        config = dataclass_replace(config, port=args.port)
    if args.state:
        config = dataclass_replace(config, state_path=args.state)
    if not _loopback_host(config.host) and not args.allow_remote:
        parser.error("bind remoto recusado sem --allow-remote")
    if (
        not _loopback_host(config.host)
        and not config.cookie_secure
        and not args.allow_insecure_http
    ):
        parser.error("bind remoto exige AGENTIC_PORTAL_COOKIE_SECURE=1 e TLS")
    app = create_app(config)
    ServerHandler.server_software = "AgenticPortal"
    with make_server(
        config.host,
        config.port,
        app,
        server_class=ThreadingWSGIServer,
        handler_class=PortalRequestHandler,
    ) as server:
        print(f"Agentic portal em http://{config.host}:{config.port}", flush=True)
        server.serve_forever()
    return 0


def dataclass_replace(config: PortalConfig, **changes: Any) -> PortalConfig:
    # Local wrapper avoids importing or touching the project's broader settings object.
    from dataclasses import replace

    return replace(config, **changes)


if __name__ == "__main__":
    raise SystemExit(main())

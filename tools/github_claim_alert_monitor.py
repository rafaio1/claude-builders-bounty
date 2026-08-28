#!/usr/bin/env python3
"""Bounded GitHub claim/deadline monitor with operational Telegram alerts.

This is deliberately separate from the financial Telegram gate. A claim,
escrow amount, bounty, or promised reward is not realized revenue.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path("/Agentic")
DEFAULT_STATE_PATH = ROOT / "state" / "github_claim_alert_state.json"
DEFAULT_ENV_PATH = ROOT / ".env"
SCHEMA_VERSION = "github-claim-alert/v1"
MAX_NOTIFICATIONS = 50
MAX_FETCHES = 30
MAX_ALERTS_PER_RUN = 5
MAX_ACTIVE_CLAIM_FETCHES = 15
MAX_COMMENTS_PER_CLAIM = 30
MAX_STATE_EVENTS = 5000
TRUSTED_HUMAN_ASSOCIATIONS = frozenset({"OWNER", "MEMBER", "COLLABORATOR"})
TERMINAL_CLAIM_STATUSES = frozenset({"released", "rejected"})
FINANCIAL_STAGE_BY_KIND = {
    "claim_accepted": 1,
    "payment_queued": 2,
    "payment_confirmed": 3,
}
FINANCIAL_STATUS_BY_STAGE = {
    1: ("accepted", "accepted_not_settled"),
    2: ("payment_queued", "payment_pending_not_settled"),
    3: (
        "payment_reported_requires_reconciliation",
        "settlement_candidate_requires_reconciliation",
    ),
}

ISO_RE = re.compile(
    r"\b(?P<ts>20\d{2}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z)\b",
    re.IGNORECASE,
)
DATE_ONLY_RE = re.compile(
    r"(?ix)\b(?:deadline[_ -]?date|deadline|due[_ -]?date|截止日期)\b"
    r"\s*[：:=\-]?\s*[\"']?(?P<date>20\d{2}-\d{2}-\d{2})\b"
)
REWARD_RE = re.compile(
    r"(?ix)\b(?P<amount>\d+(?:[.,]\d+)?)\s*(?P<currency>RTC|TP|USDT|USDC|USD|EUR|BRL)\b"
)
LABELED_REWARD_RE = re.compile(
    r"(?ix)(?:escrow|reward|bounty|payout|奖励|赏金)"
    r"[^\d\n]{0,24}(?P<amount>\d+(?:[.,]\d+)?)\s*"
    r"(?P<currency>RTC|TP|USDT|USDC|USD|EUR|BRL)\b"
)
RELEASE_RE = re.compile(
    r"(?i)(claim\s+(?:has\s+been\s+)?released|reclaim\s+freely|"
    r"claim\s+is\s+(?:open|available)|认领已释放|认领已被释放|重新开放)"
)
CONFIRMED_RE_TEMPLATE = (
    r"(?i)(?:claimed\s+by\s+@{login}\b|claim\s+confirmed\s+for\s+@{login}\b|"
    r"已认领[：:]\s*@{login}\b|@{login}\s*认领成功|"
    r"assigned\s+to\s+@{login}\b)"
)
ACTION_RE = re.compile(
    r"(?i)(action\s+required|claim\s+window|claim\s+deadline|"
    r"deadline|expires?|expiring|剩余|窗口|到\s*\*{0,2}20\d{2}-)"
)
CLAIM_CONTEXT_RE = re.compile(
    r"(?i)(claim|bount(?:y|ies)|reward|payout|escrow|认领|奖励|赏金)"
)
ACCEPTED_RE = re.compile(
    r"(?is)\b(?:claim|submission|deliverable|bounty)\b.{0,120}\b(?:accepted|approved)\b|"
    r"\b(?:accepted|approved)\b.{0,120}\b(?:claim|submission|deliverable|bounty|RTC)\b"
)
PAYMENT_QUEUED_RE = re.compile(
    r"(?is)\b(?:payout|payment|transfer)\b.{0,100}\b(?:queued|pending)\b|"
    r"\b(?:pending[_ -]?ids?|payout queued)\b"
)
PAYMENT_CONFIRMED_RE = re.compile(
    r"(?is)\b(?:confirmed on[- ]?chain|on[- ]?chain confirmed|payment confirmed|"
    r"payout confirmed|transfer confirmed|bounty paid)\b"
)
SETTLEMENT_EVIDENCE_RE = re.compile(
    r"(?i)\b(?:tx(?:id)?|transaction|pending[_ -]?id|on[- ]?chain|ledger|wallet)\b"
)
REJECTED_RE = re.compile(
    r"(?i)\b(?:claim|submission|deliverable|bounty)\b.{0,100}\b(?:declined|rejected|not accepted|not approved)\b|"
    r"\b(?:declined|rejected|not accepted|not approved)\b.{0,100}\b(?:claim|submission|deliverable|bounty)\b"
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_deadline(text: str) -> str | None:
    """Return the first valid deadline normalized as a UTC timestamp.

    An explicit date-only deadline is interpreted as the inclusive end of that
    UTC day.  Arbitrary dates are intentionally ignored: the date must be
    attached to a deadline label such as ``deadline_date`` or ``deadline``.
    """
    if not isinstance(text, str):
        return None
    for match in ISO_RE.finditer(text):
        raw = match.group("ts")
        try:
            datetime.fromisoformat(raw[:-1] + "+00:00")
        except ValueError:
            continue
        return raw[:-1] + "Z"
    for match in DATE_ONLY_RE.finditer(text):
        try:
            deadline_date = datetime.strptime(match.group("date"), "%Y-%m-%d").replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            continue
        return deadline_date.replace(
            hour=23,
            minute=59,
            second=59,
            tzinfo=timezone.utc,
        ).isoformat().replace("+00:00", "Z")
    return None


def _normalize_deadline_fields(record: dict[str, Any]) -> str | None:
    """Normalize ``deadline``/``deadline_date`` without discarding either."""
    raw_deadline = record.get("deadline")
    if isinstance(raw_deadline, str) and raw_deadline:
        if re.fullmatch(r"20\d{2}-\d{2}-\d{2}", raw_deadline):
            normalized = parse_deadline(f"deadline_date: {raw_deadline}")
        else:
            normalized = parse_deadline(f"deadline: {raw_deadline}")
        if normalized:
            record["deadline"] = normalized
            return normalized
    raw_date = record.get("deadline_date")
    if isinstance(raw_date, str) and raw_date:
        normalized = parse_deadline(f"deadline_date: {raw_date}")
        if normalized:
            record["deadline"] = normalized
            return normalized
    return None


def _author(latest: dict[str, Any]) -> tuple[str, str, str]:
    author = latest.get("author") or latest.get("user") or {}
    if isinstance(author, str):
        return author, "", str(latest.get("author_association") or "").upper()
    if not isinstance(author, dict):
        return "", "", str(latest.get("author_association") or "").upper()
    return (
        str(author.get("login") or ""),
        str(author.get("type") or ""),
        str(latest.get("author_association") or "").upper(),
    )


def _subject_identifier(notification: dict[str, Any]) -> str:
    subject = notification.get("subject") or {}
    url = str(subject.get("url") or "")
    match = re.search(r"/(?:issues|pulls)/(\d+)(?:$|\?)", url)
    if match:
        return match.group(1)
    return str(notification.get("id") or "unknown")


def _canonical_url(notification: dict[str, Any], latest: dict[str, Any]) -> str:
    direct = str(latest.get("html_url") or "")
    if direct.startswith("https://github.com/"):
        return direct
    subject = notification.get("subject") or {}
    api_url = str(subject.get("url") or "")
    match = re.match(
        r"https://api\.github\.com/repos/([^/]+/[^/]+)/(issues|pulls)/(\d+)$",
        api_url,
    )
    if match:
        owner_repo, kind, number = match.groups()
        web_kind = "issues" if kind == "issues" else "pull"
        return f"https://github.com/{owner_repo}/{web_kind}/{number}"
    return ""


def _potential_reward(text: str) -> str | None:
    match = LABELED_REWARD_RE.search(text) or REWARD_RE.search(text)
    if not match:
        return None
    amount = match.group("amount").replace(",", ".")
    return f"{amount} {match.group('currency').upper()}"


def classify_event(
    notification: dict[str, Any],
    latest: dict[str, Any],
    login: str = "rafaio1",
) -> dict[str, Any] | None:
    """Classify only high-signal GitHub claim and deadline events.

    Assignment and release confirmations require a bot-authored event. Human
    operational and financial events require GitHub's OWNER, MEMBER, or
    COLLABORATOR association in addition to their textual evidence.
    """
    if not isinstance(notification, dict) or not isinstance(latest, dict):
        return None
    subject = notification.get("subject") or {}
    if str(subject.get("type") or "") not in {"Issue", "PullRequest"}:
        return None
    body = str(latest.get("body") or "")
    if not body or len(body) > 500_000:
        return None

    author_login, author_type, author_association = _author(latest)
    is_bot = author_type == "Bot" and (
        author_login.endswith("[bot]") or "<!-- claim-bot -->" in body
    )
    trusted_human = (
        author_type == "User"
        and author_association in TRUSTED_HUMAN_ASSOCIATIONS
    )
    deadline = parse_deadline(body)
    login_pattern = re.compile(CONFIRMED_RE_TEMPLATE.format(login=re.escape(login)))

    kind: str | None = None
    reason: str | None = None
    assignment_match = login_pattern.search(body)
    direct_login_reference = bool(
        re.search(rf"(?i)(?:@|\b){re.escape(login)}\b", body)
    )
    external_actor = author_login.casefold() != login.casefold()
    potential_reward = _potential_reward(body)
    if assignment_match and not is_bot:
        return None
    if (
        trusted_human
        and external_actor
        and direct_login_reference
        and REJECTED_RE.search(body)
    ):
        kind = "claim_rejected"
        reason = "O mantenedor recusou explicitamente a claim ou o entregável."
    elif (
        trusted_human
        and
        external_actor
        and direct_login_reference
        and PAYMENT_CONFIRMED_RE.search(body)
        and SETTLEMENT_EVIDENCE_RE.search(body)
    ):
        kind = "payment_confirmed"
        reason = "A plataforma informou confirmação de pagamento; falta reconciliar saldo e transação."
    elif (
        trusted_human
        and external_actor
        and direct_login_reference
        and PAYMENT_QUEUED_RE.search(body)
    ):
        kind = "payment_queued"
        reason = "A plataforma informou que o pagamento foi enfileirado ou está pendente."
    elif (
        trusted_human
        and
        external_actor
        and direct_login_reference
        and ACCEPTED_RE.search(body)
    ):
        kind = "claim_accepted"
        reason = "O mantenedor aceitou explicitamente a claim ou o entregável."
    elif is_bot and assignment_match:
        kind = "claim_confirmed"
        reason = "A claim foi confirmada para o usuário."
    elif is_bot and direct_login_reference and RELEASE_RE.search(body):
        kind = "claim_released"
        reason = "A claim foi liberada ou reaberta e pode exigir nova ação."
    elif (
        trusted_human
        and deadline
        and ACTION_RE.search(body)
        and CLAIM_CONTEXT_RE.search(body)
    ):
        kind = "action_required"
        reason = "Há um prazo objetivo relacionado a claim ou recompensa."
    else:
        return None

    repository = str((notification.get("repository") or {}).get("full_name") or "")
    title = str(subject.get("title") or "")[:300]
    identifier = _subject_identifier(notification)
    url = _canonical_url(notification, latest)
    if not repository or not identifier or not url:
        return None

    return {
        "schema_version": SCHEMA_VERSION,
        "platform": "github",
        "kind": kind,
        "repository": repository,
        "identifier": identifier,
        "title": title,
        "url": url,
        "deadline": deadline,
        "actor_login": author_login,
        "actor_type": author_type,
        "author_association": author_association,
        "source_id": str(latest.get("id") or notification.get("id") or ""),
        "source_created_at": str(latest.get("created_at") or notification.get("updated_at") or ""),
        "reason": reason,
        "potential_reward": potential_reward,
        "revenue_status": {
            "claim_accepted": "accepted_not_settled",
            "payment_queued": "payment_pending_not_settled",
            "payment_confirmed": "settlement_candidate_requires_reconciliation",
            "claim_rejected": "rejected_not_revenue",
        }.get(kind, "potential_not_realized"),
    }


def fingerprint(event: dict[str, Any]) -> str:
    parts = (
        str(event.get("platform") or ""),
        str(event.get("repository") or ""),
        str(event.get("identifier") or ""),
        str(event.get("kind") or ""),
        str(event.get("deadline") or ""),
        str(event.get("source_id") or ""),
        str(event.get("milestone") or ""),
    )
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def default_state() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "last_poll_at": None,
        "seen": {},
        "active_claims": {},
        "event_history": {},
        "outbox": {},
        "notification_cursors": {},
        "active_claim_poll_offset": 0,
        "updated_at": None,
    }


def _ensure_state_shape(state: dict[str, Any]) -> dict[str, Any]:
    if isinstance(state.get("seen"), list):
        state["seen"] = {
            str(item): {"sent_at": None, "kind": "legacy", "url": ""}
            for item in state["seen"]
        }
    state.setdefault("seen", {})
    state.setdefault("active_claims", {})
    state.setdefault("event_history", {})
    state.setdefault("outbox", {})
    state.setdefault("notification_cursors", {})
    state.setdefault("active_claim_poll_offset", 0)
    if not all(
        isinstance(state.get(field), dict)
        for field in (
            "seen",
            "active_claims",
            "event_history",
            "outbox",
            "notification_cursors",
        )
    ):
        raise ValueError("malformed claim alert state")
    if any(
        not isinstance(claim, dict)
        for claim in state["active_claims"].values()
    ):
        raise ValueError("malformed active claim state")
    for claim in state["active_claims"].values():
        _normalize_deadline_fields(claim)
        claim.setdefault("status", "active")
        claim.setdefault("history", [])
        cursor = claim.setdefault("comment_cursor", {})
        if not isinstance(cursor, dict):
            cursor = {}
            claim["comment_cursor"] = cursor
        if not cursor.get("last_comment_id"):
            source_id = str(claim.get("source_id") or "")
            if source_id.isdigit():
                cursor["last_comment_id"] = int(source_id)
        if not cursor.get("last_comment_created_at") and claim.get("source_created_at"):
            cursor["last_comment_created_at"] = claim["source_created_at"]
    return state


def load_state(path: str | Path) -> dict[str, Any]:
    state_path = Path(path)
    if not state_path.exists():
        return default_state()
    data = json.loads(state_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("invalid or unsupported claim alert state")
    data = _ensure_state_shape(data)
    if not all(
        isinstance(data.get(field), dict)
        for field in (
            "seen",
            "active_claims",
            "event_history",
            "outbox",
            "notification_cursors",
        )
    ):
        raise ValueError("malformed claim alert state")
    return data


def save_state(path: str | Path, state: dict[str, Any]) -> None:
    """Atomically persist private state with mode 0600."""
    state_path = Path(path)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    _ensure_state_shape(state)
    state["schema_version"] = SCHEMA_VERSION
    state["updated_at"] = iso_utc(utc_now())
    payload = json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    fd, temporary = tempfile.mkstemp(prefix=f".{state_path.name}.", dir=state_path.parent)
    try:
        if hasattr(os, "fchmod"):
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, state_path)
        os.chmod(state_path, 0o600)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def format_telegram_message(event: dict[str, Any]) -> str:
    labels = {
        "claim_confirmed": "CLAIM CONFIRMADA",
        "claim_released": "CLAIM LIBERADA",
        "action_required": "PRAZO / AÇÃO NECESSÁRIA",
        "deadline_reminder": "LEMBRETE DE PRAZO",
        "claim_expired": "CLAIM EXPIRADA",
        "claim_accepted": "CLAIM ACEITA",
        "payment_queued": "PAGAMENTO ENFILEIRADO",
        "payment_confirmed": "PAGAMENTO INFORMADO COMO CONFIRMADO",
        "claim_rejected": "CLAIM RECUSADA",
    }
    label = labels.get(str(event.get("kind")), "EVENTO DE CLAIM")
    deadline = str(event.get("deadline") or "não informado")
    reward = str(event.get("potential_reward") or "não informado")
    lines = [
        f"<b>⚠️ {html.escape(label)}</b>",
        f"<b>Item:</b> {html.escape(str(event.get('repository') or ''))}#{html.escape(str(event.get('identifier') or ''))}",
        f"<b>Título:</b> {html.escape(str(event.get('title') or '')[:300])}",
        f"<b>Motivo:</b> {html.escape(str(event.get('reason') or ''))}",
        f"<b>Prazo UTC:</b> <code>{html.escape(deadline)}</code>",
        f"<b>Valor citado:</b> {html.escape(reward)}",
        f"<b>Status financeiro:</b> {html.escape(str(event.get('revenue_status') or 'não realizado'))}",
        f"<b>Link:</b> {html.escape(str(event.get('url') or ''))}",
        "",
        (
            "<b>Confirmação externa recebida, mas ainda não é receita realizada.</b> "
            "Reconcilie endereço, transação e saldo antes de contabilizar."
            if event.get("kind") == "payment_confirmed"
            else "<b>Não é receita realizada.</b> Confirme aceitação e liquidação antes de contabilizar."
        ),
    ]
    return "\n".join(lines)


def _load_env(path: str | Path) -> dict[str, str]:
    result: dict[str, str] = {}
    env_path = Path(path)
    if not env_path.exists():
        return result
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key.strip()] = value.strip().strip('"').strip("'")
    return result


def _telegram_send(text: str, env_path: str | Path, dry_run: bool = False) -> bool:
    if dry_run:
        print(text)
        return True
    env = _load_env(env_path)
    token = env.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = env.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        raise RuntimeError("Telegram operational alert credentials are not configured")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps(
        {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
    ).encode("utf-8")
    for attempt in range(3):
        request = urllib.request.Request(
            url,
            data=payload,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                data = json.loads(response.read().decode("utf-8"))
            if data.get("ok") is True:
                return True
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                try:
                    detail = json.loads(exc.read().decode("utf-8"))
                    wait = int(detail.get("parameters", {}).get("retry_after", 2))
                except (
                    AttributeError,
                    OSError,
                    TypeError,
                    UnicodeDecodeError,
                    ValueError,
                    json.JSONDecodeError,
                ):
                    wait = 2
                time.sleep(min(max(wait, 1), 15))
                continue
            if exc.code in {401, 403}:
                return False
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            pass
        if attempt < 2:
            time.sleep(2**attempt)
    return False


def _gh_api(endpoint: str, timeout: int = 30) -> Any:
    command = [
        "gh",
        "api",
        "-H",
        "Accept: application/vnd.github+json",
        endpoint,
    ]
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=os.environ.copy(),
    )
    if completed.returncode != 0:
        message = completed.stderr.strip().splitlines()[-1:] or ["GitHub API failed"]
        raise RuntimeError(message[0][:300])
    return json.loads(completed.stdout)


def _should_fetch(notification: dict[str, Any]) -> bool:
    subject = notification.get("subject") or {}
    if str(subject.get("type") or "") not in {"Issue", "PullRequest"}:
        return False
    reason = str(notification.get("reason") or "")
    if reason == "mention":
        return True
    title = str(subject.get("title") or "")
    if CLAIM_CONTEXT_RE.search(title):
        return True
    return bool(notification.get("unread")) and reason in {"author", "comment", "state_change"}


def _notification_endpoint(state: dict[str, Any], now: datetime) -> str:
    last = state.get("last_poll_at")
    since = now - timedelta(hours=12)
    if isinstance(last, str) and last:
        try:
            parsed = datetime.fromisoformat(last.replace("Z", "+00:00"))
            since = parsed - timedelta(minutes=5)
        except ValueError:
            pass
    query = urllib.parse.urlencode(
        {
            "all": "true",
            "participating": "true",
            "per_page": str(MAX_NOTIFICATIONS),
            "since": iso_utc(since),
        }
    )
    return f"notifications?{query}"


def _claim_key(event: dict[str, Any]) -> str:
    return f"{event.get('platform')}|{event.get('repository')}|{event.get('identifier')}"


EVENT_FIELDS = frozenset(
    {
        "schema_version",
        "platform",
        "kind",
        "repository",
        "identifier",
        "title",
        "url",
        "deadline",
        "deadline_date",
        "actor_login",
        "actor_type",
        "author_association",
        "source_id",
        "source_created_at",
        "reason",
        "potential_reward",
        "revenue_status",
        "milestone",
    }
)


def _event_snapshot(event: dict[str, Any]) -> dict[str, Any]:
    snapshot = {
        key: value
        for key, value in event.items()
        if key in EVENT_FIELDS and value is not None
    }
    _normalize_deadline_fields(snapshot)
    return snapshot


def _comment_id(value: Any) -> int:
    try:
        parsed = int(str(value))
    except (TypeError, ValueError):
        return 0
    return max(0, parsed)


def _claim_is_active(claim: dict[str, Any]) -> bool:
    return str(claim.get("status") or "active") not in TERMINAL_CLAIM_STATUSES


def _notification_for_claim(claim: dict[str, Any]) -> dict[str, Any] | None:
    repository = str(claim.get("repository") or "")
    identifier = str(claim.get("identifier") or "")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        return None
    if not identifier.isdigit():
        return None
    return {
        "id": f"active-claim-{repository}-{identifier}",
        "reason": "comment",
        "unread": True,
        "subject": {
            "title": str(claim.get("title") or "")[:300],
            "type": "PullRequest" if "/pull/" in str(claim.get("url") or "") else "Issue",
            "url": f"https://api.github.com/repos/{repository}/issues/{identifier}",
        },
        "repository": {"full_name": repository},
    }


def _comments_endpoint(claim: dict[str, Any]) -> str | None:
    notification = _notification_for_claim(claim)
    if notification is None:
        return None
    subject_url = str(notification["subject"]["url"])
    query: dict[str, str] = {
        "per_page": str(MAX_COMMENTS_PER_CLAIM),
    }
    cursor = claim.get("comment_cursor") or {}
    since = str(cursor.get("last_comment_created_at") or "")
    if since:
        query["since"] = since
    return (
        subject_url.removeprefix("https://api.github.com/")
        + "/comments?"
        + urllib.parse.urlencode(query)
    )


def _poll_active_claim_comments(
    state: dict[str, Any],
    login: str,
    now: datetime,
    fetch_budget: int,
) -> tuple[list[dict[str, Any]], int]:
    """Fetch every new comment, advancing a durable per-claim ID cursor.

    The single-page, ascending request is intentionally bounded.  If a claim
    has more than ``MAX_COMMENTS_PER_CLAIM`` new comments, the stored cursor
    advances only through the processed page so the next run continues from
    there instead of jumping to the latest comment.
    """
    active = [
        (key, claim)
        for key, claim in sorted(state["active_claims"].items())
        if isinstance(claim, dict) and _claim_is_active(claim)
    ]
    if not active or fetch_budget <= 0:
        return [], 0

    offset = int(state.get("active_claim_poll_offset") or 0) % len(active)
    rotated = active[offset:] + active[:offset]
    limit = min(fetch_budget, MAX_ACTIVE_CLAIM_FETCHES, len(rotated))
    candidates: list[dict[str, Any]] = []
    fetches = 0
    processed_claims = 0
    for _key, claim in rotated[:limit]:
        endpoint = _comments_endpoint(claim)
        if not endpoint:
            processed_claims += 1
            continue
        try:
            comments = _gh_api(endpoint)
        except (RuntimeError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
            claim["last_comment_poll_error"] = str(exc)[:300]
            claim["last_comment_poll_at"] = iso_utc(now)
            fetches += 1
            processed_claims += 1
            continue
        fetches += 1
        processed_claims += 1
        claim["last_comment_poll_at"] = iso_utc(now)
        claim.pop("last_comment_poll_error", None)
        if not isinstance(comments, list):
            claim["last_comment_poll_error"] = "GitHub comments response was not a list"
            continue

        notification = _notification_for_claim(claim)
        if notification is None:
            continue
        cursor = claim.setdefault("comment_cursor", {})
        last_id = _comment_id(cursor.get("last_comment_id"))
        ordered_comments = sorted(
            (comment for comment in comments if isinstance(comment, dict)),
            key=lambda comment: _comment_id(comment.get("id")),
        )
        new_comments = [
            comment
            for comment in ordered_comments
            if _comment_id(comment.get("id")) > last_id
        ][:MAX_COMMENTS_PER_CLAIM]
        for comment in new_comments:
            current_id = _comment_id(comment.get("id"))
            comment_timestamp = str(
                comment.get("created_at") or comment.get("updated_at") or ""
            )
            if not comment_timestamp:
                claim["last_comment_poll_error"] = (
                    f"comment {current_id} has no created_at/updated_at; cursor preserved"
                )
                break
            event = classify_event(notification, comment, login=login)
            if event:
                candidates.append(event)
            # Advance only after this exact comment has been inspected.
            last_id = current_id
            cursor["last_comment_id"] = current_id
            cursor["last_comment_created_at"] = comment_timestamp

    state["active_claim_poll_offset"] = (offset + processed_claims) % len(active)
    return candidates, fetches


def _claim_history_entry(
    event_id: str,
    event: dict[str, Any],
    detected_at: str,
) -> dict[str, Any]:
    fields = (
        "kind",
        "source_id",
        "source_created_at",
        "actor_login",
        "actor_type",
        "author_association",
        "url",
        "deadline",
        "potential_reward",
        "revenue_status",
        "milestone",
    )
    entry = {key: event.get(key) for key in fields if event.get(key) is not None}
    entry["event_id"] = event_id
    entry["detected_at"] = detected_at
    return entry


def _claim_financial_stage(claim: dict[str, Any]) -> int:
    try:
        explicit = int(claim.get("financial_stage") or 0)
    except (TypeError, ValueError):
        explicit = 0
    if "financial_stage" in claim and (
        explicit == 0 or explicit in FINANCIAL_STATUS_BY_STAGE
    ):
        return explicit
    kind = str(claim.get("last_financial_event") or "")
    if kind in FINANCIAL_STAGE_BY_KIND:
        return FINANCIAL_STAGE_BY_KIND[kind]
    status = str(claim.get("status") or "")
    return {
        "accepted": 1,
        "payment_queued": 2,
        "payment_reported_requires_reconciliation": 3,
    }.get(status, 0)


def _apply_claim_event(
    state: dict[str, Any],
    event_id: str,
    event: dict[str, Any],
    detected_at: str,
) -> None:
    key = _claim_key(event)
    claim = state["active_claims"].get(key)
    if not isinstance(claim, dict):
        claim = {}
    reminders_sent = list(claim.get("reminders_sent") or [])
    history = list(claim.get("history") or [])
    cursor = claim.get("comment_cursor")
    if not isinstance(cursor, dict):
        cursor = {}
    previous_stage = _claim_financial_stage(claim)
    previous_status = str(claim.get("status") or "active")
    previous_financial_event = claim.get("last_financial_event")

    claim.update(_event_snapshot(event))
    claim["reminders_sent"] = reminders_sent
    claim["history"] = history
    claim["comment_cursor"] = cursor
    kind = str(event.get("kind") or "")
    operational_status = {
        "claim_confirmed": "active",
        "action_required": "action_required",
        "deadline_reminder": "deadline_reminder",
        "claim_expired": "deadline_elapsed_pending_verification",
        "claim_released": "released",
        "claim_rejected": "rejected",
    }.get(kind, "monitoring")
    claim["operational_status"] = operational_status

    incoming_stage = FINANCIAL_STAGE_BY_KIND.get(kind, 0)
    if kind == "claim_rejected":
        claim["status"] = "rejected"
        claim["financial_stage"] = 0
        claim["financial_status"] = "rejected_not_revenue"
        claim["revenue_status"] = "rejected_not_revenue"
        claim["last_financial_event"] = kind
    elif kind == "claim_released":
        claim["status"] = "released"
        claim["financial_stage"] = 0
        claim.pop("financial_status", None)
        claim.pop("revenue_status", None)
        claim.pop("last_financial_event", None)
    elif incoming_stage and incoming_stage >= previous_stage:
        financial_status, revenue_status = FINANCIAL_STATUS_BY_STAGE[incoming_stage]
        claim["financial_stage"] = incoming_stage
        claim["financial_status"] = revenue_status
        claim["revenue_status"] = revenue_status
        claim["status"] = financial_status
        claim["last_financial_event"] = kind
    elif previous_stage:
        financial_status, revenue_status = FINANCIAL_STATUS_BY_STAGE[previous_stage]
        claim["financial_stage"] = previous_stage
        claim["financial_status"] = revenue_status
        claim["revenue_status"] = revenue_status
        claim["status"] = financial_status
        if previous_financial_event:
            claim["last_financial_event"] = previous_financial_event
    elif kind == "claim_expired":
        claim["status"] = "deadline_elapsed_pending_verification"
    elif kind == "action_required":
        claim["status"] = "action_required"
    elif kind == "claim_confirmed":
        claim["status"] = "active"
    else:
        claim["status"] = previous_status

    claim["last_event"] = kind
    claim["last_event_at"] = detected_at
    if claim["status"] in TERMINAL_CLAIM_STATUSES:
        claim["closed_at"] = detected_at
    else:
        claim.pop("closed_at", None)

    if not any(item.get("event_id") == event_id for item in history if isinstance(item, dict)):
        history.append(_claim_history_entry(event_id, event, detected_at))
        claim["history"] = history[-200:]

    # Initialize a newly tracked claim at its originating comment.  Existing
    # cursors are never jumped forward by a notification's latest-comment URL.
    if not cursor.get("last_comment_id"):
        source_id = _comment_id(event.get("source_id"))
        if source_id:
            cursor["last_comment_id"] = source_id
            cursor["last_comment_created_at"] = str(event.get("source_created_at") or detected_at)
    _normalize_deadline_fields(claim)
    state["active_claims"][key] = claim


def _register_event(
    state: dict[str, Any],
    event: dict[str, Any],
    detected_at: str,
) -> bool:
    snapshot = _event_snapshot(event)
    event_id = fingerprint(snapshot)
    if event_id in state["seen"]:
        seen_record = state["seen"].get(event_id)
        if not isinstance(seen_record, dict):
            seen_record = {}
        if event_id not in state["event_history"]:
            delivered_at = seen_record.get("sent_at")
            state["event_history"][event_id] = {
                **snapshot,
                "event_id": event_id,
                "detected_at": str(delivered_at or detected_at),
                "delivery_status": "delivered",
                "delivered_at": delivered_at,
            }
        return False
    existing_outbox = state["outbox"].get(event_id)
    if isinstance(existing_outbox, dict):
        if event_id not in state["event_history"]:
            state["event_history"][event_id] = {
                **snapshot,
                "event_id": event_id,
                "detected_at": str(existing_outbox.get("queued_at") or detected_at),
                "delivery_status": str(
                    existing_outbox.get("delivery_status") or "pending"
                ),
                "delivered_at": existing_outbox.get("delivered_at"),
            }
        return False
    if event_id in state["event_history"]:
        history_record = state["event_history"][event_id]
        if (
            event_id not in state["seen"]
            and event_id not in state["outbox"]
            and isinstance(history_record, dict)
        ):
            state["outbox"][event_id] = {
                "event": snapshot,
                "queued_at": str(history_record.get("detected_at") or detected_at),
                "delivery_status": "pending",
                "attempts": 0,
                "last_attempt_at": None,
                "last_error": None,
                "delivered_at": None,
            }
        return False

    state["event_history"][event_id] = {
        **snapshot,
        "event_id": event_id,
        "detected_at": detected_at,
        "delivery_status": "pending",
        "delivered_at": None,
    }
    state["outbox"][event_id] = {
        "event": snapshot,
        "queued_at": detected_at,
        "delivery_status": "pending",
        "attempts": 0,
        "last_attempt_at": None,
        "last_error": None,
        "delivered_at": None,
    }
    _apply_claim_event(state, event_id, snapshot, detected_at)
    return True


def _prune_state(state: dict[str, Any]) -> None:
    if len(state["seen"]) > MAX_STATE_EVENTS:
        state["seen"] = dict(
            sorted(
                state["seen"].items(),
                key=lambda pair: str(pair[1].get("sent_at") or ""),
            )[-MAX_STATE_EVENTS:]
        )

    pending_ids = {
        event_id
        for event_id, item in state["outbox"].items()
        if isinstance(item, dict) and item.get("delivery_status") != "delivered"
    }
    if len(state["event_history"]) > MAX_STATE_EVENTS + len(pending_ids):
        newest = sorted(
            state["event_history"].items(),
            key=lambda pair: str(pair[1].get("detected_at") or ""),
        )[-MAX_STATE_EVENTS:]
        keep = {event_id for event_id, _item in newest} | pending_ids
        state["event_history"] = {
            event_id: item
            for event_id, item in state["event_history"].items()
            if event_id in keep
        }
    if len(state["outbox"]) > MAX_STATE_EVENTS + len(pending_ids):
        delivered = sorted(
            (
                (event_id, item)
                for event_id, item in state["outbox"].items()
                if event_id not in pending_ids
            ),
            key=lambda pair: str(pair[1].get("delivered_at") or ""),
        )[-MAX_STATE_EVENTS:]
        keep = {event_id for event_id, _item in delivered} | pending_ids
        state["outbox"] = {
            event_id: item
            for event_id, item in state["outbox"].items()
            if event_id in keep
        }
    if len(state["notification_cursors"]) > MAX_STATE_EVENTS:
        state["notification_cursors"] = dict(
            sorted(
                state["notification_cursors"].items(),
                key=lambda pair: str(pair[1]),
            )[-MAX_STATE_EVENTS:]
        )


def _deliver_outbox(
    state_path: str | Path,
    state: dict[str, Any],
    env_path: str | Path,
    now: datetime,
    limit: int = MAX_ALERTS_PER_RUN,
) -> tuple[int, str | None]:
    sent = 0
    failure: str | None = None
    pending = sorted(
        (
            (event_id, item)
            for event_id, item in state["outbox"].items()
            if isinstance(item, dict) and item.get("delivery_status") != "delivered"
        ),
        key=lambda pair: str(pair[1].get("queued_at") or ""),
    )
    for event_id, item in pending[: max(limit, 0)]:
        event = item.get("event") or {}
        attempt_at = iso_utc(now)
        item["attempts"] = int(item.get("attempts") or 0) + 1
        item["last_attempt_at"] = attempt_at
        item["last_error"] = None
        # Record the attempt before crossing the external Telegram boundary.
        save_state(state_path, state)
        try:
            delivered = _telegram_send(format_telegram_message(event), env_path)
        except (RuntimeError, OSError) as exc:
            delivered = False
            failure = str(exc)[:300]
        if not delivered:
            failure = failure or "Telegram operational alert delivery failed"
            item["last_error"] = failure
            history_record = state["event_history"].get(event_id)
            if isinstance(history_record, dict):
                history_record["delivery_status"] = "pending"
                history_record["last_delivery_error"] = failure
            save_state(state_path, state)
            break

        delivered_at = iso_utc(now)
        item["delivery_status"] = "delivered"
        item["delivered_at"] = delivered_at
        item["last_error"] = None
        state["seen"][event_id] = {
            "sent_at": delivered_at,
            "kind": str(event.get("kind") or ""),
            "url": str(event.get("url") or ""),
        }
        history_record = state["event_history"].get(event_id)
        if isinstance(history_record, dict):
            history_record["delivery_status"] = "delivered"
            history_record["delivered_at"] = delivered_at
            history_record.pop("last_delivery_error", None)
        save_state(state_path, state)
        sent += 1
    return sent, failure


def _deadline_events(state: dict[str, Any], now: datetime) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    thresholds = ((24, "24h"), (6, "6h"), (1, "1h"))
    for key, claim in list(state["active_claims"].items()):
        if str(claim.get("status") or "active") in TERMINAL_CLAIM_STATUSES:
            continue
        deadline_raw = _normalize_deadline_fields(claim)
        if not deadline_raw:
            continue
        try:
            deadline = datetime.fromisoformat(str(deadline_raw).replace("Z", "+00:00"))
        except ValueError:
            continue
        remaining = (deadline - now).total_seconds()
        sent = set(claim.setdefault("reminders_sent", []))
        if remaining <= 0 and "expired" not in sent:
            event = dict(claim)
            event.update(
                {
                    "kind": "claim_expired",
                    "milestone": "expired",
                    "reason": "O prazo registrado para a claim terminou; confirme o estado oficial.",
                }
            )
            alerts.append(event)
            sent.add("expired")
            claim["reminders_sent"] = sorted(sent)
            continue
        for hours, label in thresholds:
            if 0 < remaining <= hours * 3600 and label not in sent:
                event = dict(claim)
                event.update(
                    {
                        "kind": "deadline_reminder",
                        "milestone": label,
                        "reason": f"Restam menos de {label} para o prazo conhecido da claim.",
                    }
                )
                alerts.append(event)
                sent.add(label)
                claim["reminders_sent"] = sorted(sent)
                break
    return alerts


def run_monitor(
    state_path: str | Path,
    env_path: str | Path,
    login: str,
    dry_run: bool = False,
) -> int:
    now = utc_now()
    state = load_state(state_path)

    pre_sent, pre_failure = (0, None)
    if not dry_run:
        pre_sent, pre_failure = _deliver_outbox(state_path, state, env_path, now)
    notifications = _gh_api(_notification_endpoint(state, now))
    if not isinstance(notifications, list):
        raise RuntimeError("GitHub notifications response was not a list")

    fetches = 1
    candidates, active_fetches = _poll_active_claim_comments(
        state,
        login,
        now,
        fetch_budget=max(MAX_FETCHES - fetches, 0),
    )
    fetches += active_fetches
    ordered = sorted(notifications[:MAX_NOTIFICATIONS], key=lambda item: item.get("updated_at", ""))
    notification_poll_complete = True
    for notification in ordered:
        if not _should_fetch(notification):
            continue
        subject = notification.get("subject") or {}
        latest_url = str(subject.get("latest_comment_url") or subject.get("url") or "")
        notification_key = str(notification.get("id") or "")
        if not notification_key:
            notification_key = hashlib.sha256(
                (
                    str(subject.get("url") or "")
                    + "|"
                    + str(notification.get("updated_at") or "")
                ).encode("utf-8")
            ).hexdigest()
        notification_marker = (
            str(notification.get("updated_at") or "")
            + "|"
            + hashlib.sha256(latest_url.encode("utf-8")).hexdigest()
        )
        if state["notification_cursors"].get(notification_key) == notification_marker:
            continue
        if fetches >= MAX_FETCHES:
            notification_poll_complete = False
            continue
        if not latest_url.startswith("https://api.github.com/"):
            notification_poll_complete = False
            continue
        endpoint = latest_url.removeprefix("https://api.github.com/")
        fetches += 1
        try:
            latest = _gh_api(endpoint)
        except (RuntimeError, subprocess.TimeoutExpired, json.JSONDecodeError):
            notification_poll_complete = False
            continue
        if not isinstance(latest, dict):
            notification_poll_complete = False
            continue
        event = classify_event(notification, latest, login=login)
        if event:
            subject_url = str(subject.get("url") or "")
            if (
                not event.get("potential_reward")
                and subject_url.startswith("https://api.github.com/")
                and subject_url != latest_url
                and fetches < MAX_FETCHES
            ):
                fetches += 1
                try:
                    subject_resource = _gh_api(
                        subject_url.removeprefix("https://api.github.com/")
                    )
                except (RuntimeError, subprocess.TimeoutExpired, json.JSONDecodeError):
                    subject_resource = None
                if isinstance(subject_resource, dict):
                    event["potential_reward"] = _potential_reward(
                        str(subject_resource.get("body") or "")
                    )
            candidates.append(event)
        state["notification_cursors"][notification_key] = notification_marker

    candidates.extend(_deadline_events(state, now))
    if dry_run:
        pending_items = [
            (event_id, item)
            for event_id, item in state["outbox"].items()
            if isinstance(item, dict) and item.get("delivery_status") != "delivered"
        ]
        previews = [
            item.get("event") or {}
            for _event_id, item in sorted(
                pending_items,
                key=lambda pair: str(pair[1].get("queued_at") or ""),
            )
        ]
        observed = (
            set(state["seen"])
            | set(state["event_history"])
            | set(state["outbox"])
        )
        for event in candidates:
            event_id = fingerprint(_event_snapshot(event))
            if event_id not in observed:
                previews.append(event)
                observed.add(event_id)
        sent = 0
        for event in previews[:MAX_ALERTS_PER_RUN]:
            if not _telegram_send(
                format_telegram_message(event),
                env_path,
                dry_run=True,
            ):
                raise RuntimeError("Telegram operational alert delivery failed")
            sent += 1
        print(
            json.dumps(
                {
                    "notifications": len(notifications),
                    "fetches": fetches,
                    "events_queued": 0,
                    "alerts_previewed": sent,
                    "outbox_pending": len(pending_items),
                    "notification_poll_complete": notification_poll_complete,
                }
            )
        )
        return 0

    detected_at = iso_utc(now)
    queued = sum(
        1 for event in candidates if _register_event(state, event, detected_at)
    )
    # Cursors, event history and the full pending outbox are durable before the
    # first Telegram attempt.  A delivery outage therefore cannot erase a
    # GitHub event or make the next run jump over already-inspected comments.
    if notification_poll_complete:
        state["last_poll_at"] = detected_at
    _prune_state(state)
    save_state(state_path, state)

    if pre_failure:
        sent, failure = 0, pre_failure
    else:
        sent, failure = _deliver_outbox(
            state_path,
            state,
            env_path,
            now,
            limit=MAX_ALERTS_PER_RUN - pre_sent,
        )
    pending = sum(
        1
        for item in state["outbox"].values()
        if isinstance(item, dict) and item.get("delivery_status") != "delivered"
    )
    print(
        json.dumps(
            {
                "notifications": len(notifications),
                "fetches": fetches,
                "events_queued": queued,
                "alerts_sent": pre_sent + sent,
                "outbox_pending": pending,
                "notification_poll_complete": notification_poll_complete,
            }
        )
    )
    if failure:
        raise RuntimeError(failure)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", default=str(DEFAULT_STATE_PATH))
    parser.add_argument("--env", default=str(DEFAULT_ENV_PATH))
    parser.add_argument("--login", default="rafaio1")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        return run_monitor(args.state, args.env, args.login, dry_run=args.dry_run)
    except (ValueError, RuntimeError, OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        print(f"claim alert monitor failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

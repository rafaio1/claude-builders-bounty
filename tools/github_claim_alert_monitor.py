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

ISO_RE = re.compile(
    r"\b(?P<ts>20\d{2}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z)\b",
    re.IGNORECASE,
)
REWARD_RE = re.compile(
    r"(?ix)\b(?P<amount>\d+(?:[.,]\d+)?)\s*(?P<currency>TP|USDT|USDC|USD|EUR|BRL)\b"
)
LABELED_REWARD_RE = re.compile(
    r"(?ix)(?:escrow|reward|bounty|payout|奖励|赏金)"
    r"[^\d\n]{0,24}(?P<amount>\d+(?:[.,]\d+)?)\s*"
    r"(?P<currency>TP|USDT|USDC|USD|EUR|BRL)\b"
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


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_deadline(text: str) -> str | None:
    """Return the first valid UTC timestamp found in claim/deadline text."""
    if not isinstance(text, str):
        return None
    for match in ISO_RE.finditer(text):
        raw = match.group("ts")
        try:
            datetime.fromisoformat(raw[:-1] + "+00:00")
        except ValueError:
            continue
        return raw[:-1] + "Z"
    return None


def _author(latest: dict[str, Any]) -> tuple[str, str]:
    author = latest.get("author") or latest.get("user") or {}
    if isinstance(author, str):
        return author, ""
    if not isinstance(author, dict):
        return "", ""
    return str(author.get("login") or ""), str(author.get("type") or "")


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
    maintainers can still produce an action_required event when an objective
    deadline and claim/reward context are both present.
    """
    if not isinstance(notification, dict) or not isinstance(latest, dict):
        return None
    subject = notification.get("subject") or {}
    if str(subject.get("type") or "") not in {"Issue", "PullRequest"}:
        return None
    body = str(latest.get("body") or "")
    if not body or len(body) > 500_000:
        return None

    author_login, author_type = _author(latest)
    is_bot = author_type == "Bot" and (
        author_login.endswith("[bot]") or "<!-- claim-bot -->" in body
    )
    deadline = parse_deadline(body)
    login_pattern = re.compile(CONFIRMED_RE_TEMPLATE.format(login=re.escape(login)))

    kind: str | None = None
    reason: str | None = None
    assignment_match = login_pattern.search(body)
    if assignment_match and not is_bot:
        return None
    if is_bot and assignment_match:
        kind = "claim_confirmed"
        reason = "A claim foi confirmada para o usuário."
    elif is_bot and RELEASE_RE.search(body):
        kind = "claim_released"
        reason = "A claim foi liberada ou reaberta e pode exigir nova ação."
    elif deadline and ACTION_RE.search(body) and CLAIM_CONTEXT_RE.search(body):
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
        "source_id": str(latest.get("id") or notification.get("id") or ""),
        "source_created_at": str(latest.get("created_at") or notification.get("updated_at") or ""),
        "reason": reason,
        "potential_reward": _potential_reward(body),
        "revenue_status": "potential_not_realized",
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
        "updated_at": None,
    }


def load_state(path: str | Path) -> dict[str, Any]:
    state_path = Path(path)
    if not state_path.exists():
        return default_state()
    data = json.loads(state_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("invalid or unsupported claim alert state")
    if not isinstance(data.get("seen"), dict) or not isinstance(data.get("active_claims"), dict):
        raise ValueError("malformed claim alert state")
    return data


def save_state(path: str | Path, state: dict[str, Any]) -> None:
    """Atomically persist private state with mode 0600."""
    state_path = Path(path)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(state.get("seen"), list):
        state["seen"] = {
            str(item): {"sent_at": None, "kind": "legacy", "url": ""}
            for item in state["seen"]
        }
    state.setdefault("active_claims", {})
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
        f"<b>Link:</b> {html.escape(str(event.get('url') or ''))}",
        "",
        "<b>Não é receita realizada.</b> Confirme aceitação e liquidação antes de contabilizar.",
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
    env = _load_env(env_path)
    token = env.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = env.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        raise RuntimeError("Telegram operational alert credentials are not configured")
    if dry_run:
        print(text)
        return True

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
                except Exception:
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


def _deadline_events(state: dict[str, Any], now: datetime) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    thresholds = ((24, "24h"), (6, "6h"), (1, "1h"))
    for key, claim in list(state["active_claims"].items()):
        deadline_raw = claim.get("deadline")
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
    notifications = _gh_api(_notification_endpoint(state, now))
    if not isinstance(notifications, list):
        raise RuntimeError("GitHub notifications response was not a list")

    candidates: list[dict[str, Any]] = []
    fetches = 0
    ordered = sorted(notifications[:MAX_NOTIFICATIONS], key=lambda item: item.get("updated_at", ""))
    for notification in ordered:
        if fetches >= MAX_FETCHES or not _should_fetch(notification):
            continue
        subject = notification.get("subject") or {}
        latest_url = str(subject.get("latest_comment_url") or subject.get("url") or "")
        if not latest_url.startswith("https://api.github.com/"):
            continue
        endpoint = latest_url.removeprefix("https://api.github.com/")
        latest = _gh_api(endpoint)
        fetches += 1
        event = classify_event(notification, latest, login=login)
        if event:
            subject_url = str(subject.get("url") or "")
            if (
                not event.get("potential_reward")
                and subject_url.startswith("https://api.github.com/")
                and subject_url != latest_url
                and fetches < MAX_FETCHES
            ):
                subject_resource = _gh_api(subject_url.removeprefix("https://api.github.com/"))
                fetches += 1
                if isinstance(subject_resource, dict):
                    event["potential_reward"] = _potential_reward(
                        str(subject_resource.get("body") or "")
                    )
            candidates.append(event)

    candidates.extend(_deadline_events(state, now))
    sent = 0
    for event in candidates:
        event_id = fingerprint(event)
        if event_id in state["seen"]:
            continue
        if sent >= MAX_ALERTS_PER_RUN:
            break
        if not _telegram_send(format_telegram_message(event), env_path, dry_run=dry_run):
            raise RuntimeError("Telegram operational alert delivery failed")
        sent += 1
        if not dry_run:
            state["seen"][event_id] = {
                "sent_at": iso_utc(now),
                "kind": event["kind"],
                "url": event["url"],
            }
            key = _claim_key(event)
            if event["kind"] == "claim_confirmed":
                stored = dict(event)
                stored["reminders_sent"] = []
                state["active_claims"][key] = stored
            elif event["kind"] in {"claim_released", "claim_expired"}:
                state["active_claims"].pop(key, None)

    if not dry_run:
        state["last_poll_at"] = iso_utc(now)
        if len(state["seen"]) > 5000:
            ordered_seen = sorted(
                state["seen"].items(), key=lambda pair: pair[1].get("sent_at", "")
            )[-5000:]
            state["seen"] = dict(ordered_seen)
        save_state(state_path, state)
    print(json.dumps({"notifications": len(notifications), "fetches": fetches, "alerts_sent": sent}))
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

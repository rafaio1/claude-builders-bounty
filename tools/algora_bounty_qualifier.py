#!/usr/bin/env python3
"""Discover and qualify Algora code bounties using official GitHub evidence.

The process is read-only. It never comments, attempts, claims, forks, opens a
pull request, or recognizes a bounty's face value as revenue.
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
import uuid
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import Request, urlopen

SCHEMA_VERSION = "1.0"
GITHUB_API_ROOT = "https://api.github.com"
SEARCH_QUERY = "commenter:app/algora-pbc is:issue is:open -label:Rewarded comments:<25"
DEFAULT_OUTPUT_PATH = Path("/Agentic/state/algora_bounty_qualifications.json")
DEFAULT_MANIFEST_PATH = Path("/Agentic/state/algora_bounty_qualifications_success.json")
DEFAULT_CACHE_PATH = Path("/Agentic/state/algora_bounty_qualification_cache.json")
MAX_RESPONSE_BYTES = 12 * 1024 * 1024
MAX_SOURCE_ROWS = 100
MAX_NEW_AUDITS_PER_RUN = 3
MIN_CORE_RATE_REMAINING = 20
MIN_SEARCH_RATE_REMAINING = 2
MIN_BOUNTY_CENTS = 2_000
MAX_BOUNTY_CENTS = 500_000
MIN_REPOSITORY_AGE_DAYS = 90
MAX_REPOSITORY_IDLE_DAYS = 90
QUALIFIED_CACHE_TTL_SECONDS = 10 * 60
TRANSIENT_CACHE_TTL_SECONDS = 30 * 60
REJECTED_CACHE_TTL_SECONDS = 7 * 24 * 60 * 60
MAX_CACHE_ENTRIES = 500
BOT_LOGIN = "algora-pbc[bot]"
BOT_ID = 121443259
API_ENDPOINT_PATTERN = re.compile(
    r"^(?:[A-Za-z0-9_.~/-]|%[0-9A-Fa-f]{2})+$"
)
REPOSITORY_API_PATTERN = re.compile(
    r"^https://api\.github\.com/repos/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)$"
)
ISSUE_API_PATTERN = re.compile(
    r"^https://api\.github\.com/repos/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/issues/([1-9][0-9]*)$"
)
AMOUNT_PATTERN = (
    r"(?:[1-9]\d{0,2}(?:,\d{3})+(?:\.\d{1,2})?"
    r"|(?:0|[1-9]\d*)(?:\.\d{1,2})?)"
)
BOUNTY_HEADER_PATTERN = re.compile(
    rf"(?i)^(?:#{{1,6}}[ \t]+)?💎[ \t]*(?:\*\*)?"
    rf"(?P<currency>US[ \t]*\$|\$)[ \t]*(?P<amount>{AMOUNT_PATTERN})"
    rf"(?:\*\*)?[ \t]+bount(?:y|ies)\b(?P<tail>.*)$"
)
SPONSOR_LINK_PATTERN = re.compile(
    r"\]\(https://(?:console\.)?algora\.io/(?:org/)?"
    r"(?P<slug>[A-Za-z0-9_-]{1,80})(?:[/#?][^)]*)?\)",
    re.IGNORECASE,
)
COMMAND_PATTERN = re.compile(
    r"(?im)^\s*/(?P<kind>attempt|claim)\s+#(?P<issue>[1-9][0-9]*)\b"
)
MARKDOWN_ATTEMPT_ROW_PATTERN = re.compile(r"(?m)^\s*\|\s*(?P<cell>[^|\n]+)\|")
HTML_ATTEMPT_ROW_PATTERN = re.compile(
    r"(?is)<tr\b[^>]*>\s*<td\b[^>]*>(?P<cell>.*?)</td>.*?</tr>"
)
BOT_COMPETITION_PATTERN = re.compile(
    r"already attempting|submitted a \[pull request\][^\n]{0,300}\bclaims?\b",
    re.IGNORECASE,
)
AWARD_PATTERN = re.compile(
    rf"(?is)@(?P<login>[A-Za-z0-9](?:[A-Za-z0-9-]{{0,37}}[A-Za-z0-9])?)"
    rf"[^\n]{{0,80}}(?:has been awarded|You(?:'|’)ve been awarded(?:\s+a)?)"
    rf"\s+\*\*(?P<currency>US[ \t]*\$|\$)"
    rf"(?P<amount>{AMOUNT_PATTERN})\*\*"
)
REWARD_ACTION_PATTERN = re.compile(
    r"(?i)\[Reward\]\(https://(?:console\.)?algora\.io/claims/"
    r"[A-Za-z0-9_-]{8,128}\)"
)
BOARD_ROW_PATTERN = re.compile(r"<tr\b[^>]*>(?P<body>.*?)</tr>", re.IGNORECASE | re.DOTALL)
BOARD_ISSUE_PATTERN = re.compile(
    r"href=[\"']https://github\.com/(?P<owner>[A-Za-z0-9_.-]+)/"
    r"(?P<repo>[A-Za-z0-9_.-]+)/issues/(?P<number>[1-9][0-9]*)"
    r"(?:[?#][^\"']*)?[\"']",
    re.IGNORECASE,
)
BOARD_AMOUNT_PATTERN = re.compile(
    rf">\s*(?:US[ \t]*)?\$\s*(?P<amount>{AMOUNT_PATTERN})\s*</div>",
    re.IGNORECASE,
)
TRIVIAL_SCOPE_MARKERS = (
    "fix typo",
    "readme typo",
    "formatting only",
    "remove commented-out",
    "rename variable",
)
UNAUTOMATABLE_SCOPE_MARKERS = (
    "physical device",
    "real device",
    "requires hardware",
    "hardware required",
    "wear os",
    "publish on social",
    "social media post",
    "proprietary sdk",
    "private api",
)
TERMINAL_CANDIDATE_ERRORS = {
    "github_http_404",
    "github_http_410",
    "incomplete_issue_comments",
    "incomplete_issue_timeline",
    "incomplete_repository_tree",
}


class QualifierError(RuntimeError):
    """Official evidence could not prove a safe qualification result."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


JsonFetcher = Callable[[str, Mapping[str, Any] | None], Any]
TextFetcher = Callable[[str], str]


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_now() -> str:
    return utc_now().isoformat()


def parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _mapping(value: Any, *, code: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise QualifierError(code, "official response schema changed")
    return value


def _strict_int(value: Any, *, minimum: int = 0) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        return None
    return value


def _canonical_hash(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def _github_url(path: str, params: Mapping[str, Any] | None = None) -> str:
    path = path.lstrip("/")
    url = f"{GITHUB_API_ROOT}/{path}"
    if params:
        url = f"{url}?{urlencode(params)}"
    return url


def gh_get_json(endpoint: str, params: Mapping[str, Any] | None = None) -> Any:
    """Run a bounded, argument-safe authenticated GitHub GET request."""
    normalized = endpoint.lstrip("/")
    if not API_ENDPOINT_PATTERN.fullmatch(normalized) or ".." in normalized.split("/"):
        raise QualifierError("untrusted_github_endpoint", "refusing an invalid endpoint")
    command = [
        "/usr/bin/gh",
        "api",
        "-X",
        "GET",
        normalized,
        "-H",
        "Accept: application/vnd.github+json",
        "-H",
        "X-GitHub-Api-Version: 2022-11-28",
    ]
    for key, value in sorted((params or {}).items()):
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", str(key)):
            raise QualifierError("invalid_github_parameter", "invalid parameter name")
        command.extend(("-f", f"{key}={value}"))
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=35,
        )
    except subprocess.TimeoutExpired as error:
        raise QualifierError("github_timeout", "GitHub request timed out") from error
    except OSError as error:
        raise QualifierError("github_cli_unavailable", "GitHub CLI is unavailable") from error
    if result.returncode != 0:
        match = re.search(r"HTTP\s+([0-9]{3})", result.stderr)
        code = f"github_http_{match.group(1)}" if match else "github_request_failed"
        raise QualifierError(code, "GitHub request failed")
    if len(result.stdout.encode("utf-8")) > MAX_RESPONSE_BYTES:
        raise QualifierError("github_response_too_large", "GitHub response exceeded limit")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise QualifierError("invalid_github_json", "GitHub returned invalid JSON") from error


def _fetch_all_pages(fetch_json: JsonFetcher, path: str, params: Mapping[str, Any] | None) -> list[Any]:
    """Fetch all pages for a GitHub list endpoint using page iteration."""
    results: list[Any] = []
    page = 1
    per_page = 100
    base_params = dict(params or {})
    base_params["per_page"] = per_page
    while True:
        base_params["page"] = page
        chunk = fetch_json(path, base_params)
        if not isinstance(chunk, list):
            raise QualifierError("invalid_paginated_response", "paginated response is not a list")
        results.extend(chunk)
        if len(chunk) < per_page:
            break
        page += 1
        if page > 20:  # safety cap: 2000 items max
            raise QualifierError("pagination_limit_exceeded", "too many pages for safe autonomous fetch")
    return results



def algora_get_text(url: str) -> str:
    """Fetch a bounded public Algora board without cookies or credentials."""
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "algora.io"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in {None, 443}
        or parsed.query
        or parsed.fragment
        or not re.fullmatch(r"/[A-Za-z0-9_-]{1,80}/bounties", parsed.path)
    ):
        raise QualifierError("untrusted_algora_url", "refusing an invalid Algora URL")
    request = Request(
        url,
        headers={
            "Accept": "text/html",
            "User-Agent": "Agentic-ReadOnly-Algora-Qualifier/1.0",
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=25) as response:
            content_type = str(response.headers.get("Content-Type") or "")
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as error:
        raise QualifierError(
            f"algora_http_{error.code}", "Algora board request failed"
        ) from error
    except (URLError, TimeoutError, OSError) as error:
        raise QualifierError("algora_board_unavailable", "Algora board unavailable") from error
    if "text/html" not in content_type.casefold():
        raise QualifierError("invalid_algora_content_type", "Algora board was not HTML")
    if len(raw) > MAX_RESPONSE_BYTES:
        raise QualifierError("algora_response_too_large", "Algora board exceeded limit")
    return raw.decode("utf-8", errors="replace")


def atomic_json_write(path: Path, payload: Mapping[str, Any]) -> None:
    destination = path.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{destination.name}.", dir=destination.parent
    )
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def load_cache(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": SCHEMA_VERSION, "entries": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise QualifierError("invalid_cache", "could not read cache") from error
    entries = payload.get("entries") if isinstance(payload, Mapping) else None
    if not isinstance(entries, Mapping):
        raise QualifierError("invalid_cache", "cache schema changed")
    return {"schema_version": SCHEMA_VERSION, "entries": dict(entries)}


def check_rate_budget(fetch_json: JsonFetcher) -> dict[str, int]:
    payload = _mapping(fetch_json("rate_limit", None), code="invalid_rate_schema")
    resources = _mapping(payload.get("resources"), code="invalid_rate_schema")
    core = _mapping(resources.get("core"), code="invalid_rate_schema")
    search = _mapping(resources.get("search"), code="invalid_rate_schema")
    values = {
        "core_limit": _strict_int(core.get("limit"), minimum=1),
        "core_remaining_before": _strict_int(core.get("remaining")),
        "core_reset_epoch": _strict_int(core.get("reset"), minimum=1),
        "search_limit": _strict_int(search.get("limit"), minimum=1),
        "search_remaining_before": _strict_int(search.get("remaining")),
        "search_reset_epoch": _strict_int(search.get("reset"), minimum=1),
    }
    if any(value is None for value in values.values()):
        raise QualifierError("invalid_rate_schema", "GitHub rate budget is invalid")
    if int(values["core_remaining_before"]) < MIN_CORE_RATE_REMAINING:
        raise QualifierError("github_core_rate_budget_low", "GitHub core rate is too low")
    if int(values["search_remaining_before"]) < MIN_SEARCH_RATE_REMAINING:
        raise QualifierError("github_search_rate_budget_low", "GitHub search rate is too low")
    return {key: int(value) for key, value in values.items()}


def parse_search(payload: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    document = _mapping(payload, code="invalid_search_schema")
    if document.get("incomplete_results") is not False:
        raise QualifierError("incomplete_search_results", "GitHub search was incomplete")
    items = document.get("items")
    if not isinstance(items, list) or len(items) > MAX_SOURCE_ROWS:
        raise QualifierError("invalid_search_schema", "GitHub search items are invalid")
    candidates: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for index, raw in enumerate(items):
        if not isinstance(raw, Mapping):
            rejected.append({"index": index, "reasons": ["invalid_search_item"]})
            continue
        repo_match = REPOSITORY_API_PATTERN.fullmatch(str(raw.get("repository_url") or ""))
        issue_match = ISSUE_API_PATTERN.fullmatch(str(raw.get("url") or ""))
        reasons: list[str] = []
        if repo_match is None or issue_match is None:
            reasons.append("invalid_github_identity")
        elif repo_match.groups() != issue_match.groups()[:2]:
            reasons.append("repository_issue_identity_mismatch")
        if raw.get("state") != "open":
            reasons.append("search_issue_not_open")
        if "pull_request" in raw:
            reasons.append("search_record_is_pull_request")
        comments = _strict_int(raw.get("comments"))
        if comments is None or comments >= 25:
            reasons.append("search_comment_bound_exceeded")
        updated_at = parse_timestamp(raw.get("updated_at"))
        if updated_at is None:
            reasons.append("invalid_search_updated_at")
        if reasons:
            rejected.append(
                {
                    "url": raw.get("html_url"),
                    "reasons": sorted(set(reasons)),
                }
            )
            continue
        assert issue_match is not None and updated_at is not None
        owner, repo_slug, issue_number = issue_match.groups()
        candidate = {
            "repo": f"{owner}/{repo_slug}",
            "issue_number": int(issue_number),
            "title": str(raw.get("title") or "").strip(),
            "url": str(raw.get("html_url") or ""),
            "github_updated_at": updated_at.isoformat(),
            "search_comment_count": comments,
            "search_item_hash": _canonical_hash(raw),
        }
        candidate["candidate_key"] = _canonical_hash(candidate)
        candidates.append(candidate)
    candidates.sort(
        key=lambda row: (row["github_updated_at"], row["repo"], row["issue_number"]),
        reverse=True,
    )
    return candidates, rejected


def _amount_to_cents(raw: str) -> int | None:
    try:
        amount = Decimal(raw.replace(",", ""))
    except InvalidOperation:
        return None
    if amount <= 0 or amount.as_tuple().exponent < -2:
        return None
    return int(amount * 100)


def _valid_bot_comment(comment: Mapping[str, Any]) -> bool:
    user = comment.get("user")
    return (
        isinstance(user, Mapping)
        and str(user.get("login") or "").casefold() == BOT_LOGIN.casefold()
        and user.get("type") == "Bot"
        and _strict_int(user.get("id"), minimum=1) == BOT_ID
    )


def _parse_bounty_components(
    bot_comments: list[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    active: list[dict[str, Any]] = []
    withdrawn: list[dict[str, Any]] = []
    malformed: list[str] = []
    for comment in bot_comments:
        body = str(comment.get("body") or "").replace("\r\n", "\n")
        comment_id = _strict_int(comment.get("id"), minimum=1)
        for line_number, raw_line in enumerate(body.splitlines(), start=1):
            stripped = raw_line.strip()
            looks_like_header = "💎" in stripped and "$" in stripped and "bount" in stripped.casefold()
            if not looks_like_header:
                continue
            starts_strike = stripped.startswith("~~")
            ends_strike = stripped.endswith("~~")
            if starts_strike != ends_strike:
                malformed.append(f"comment:{comment_id}:line:{line_number}:asymmetric_strike")
                continue
            normalized = stripped[2:-2].strip() if starts_strike else stripped
            match = BOUNTY_HEADER_PATTERN.fullmatch(normalized)
            if match is None:
                malformed.append(f"comment:{comment_id}:line:{line_number}:unknown_header")
                continue
            sponsor_match = SPONSOR_LINK_PATTERN.search(match.group("tail"))
            cents = _amount_to_cents(match.group("amount"))
            if cents is None:
                malformed.append(f"comment:{comment_id}:line:{line_number}:missing_component")
                continue
            if sponsor_match is None and not starts_strike:
                malformed.append(f"comment:{comment_id}:line:{line_number}:missing_sponsor")
                continue
            slug = sponsor_match.group("slug").casefold() if sponsor_match else None
            if slug in {"awards", "bounties", "claims", "docs", "legal", "login"}:
                malformed.append(f"comment:{comment_id}:line:{line_number}:invalid_sponsor")
                continue
            component = {
                "sponsor_slug": slug,
                "amount_cents": cents,
                "comment_id": comment_id,
                "comment_url": str(comment.get("html_url") or ""),
                "line_number": line_number,
            }
            (withdrawn if starts_strike else active).append(component)
    return active, withdrawn, sorted(set(malformed))


def _parse_awards(bot_comments: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    awards: list[dict[str, Any]] = []
    for comment in bot_comments:
        body = str(comment.get("body") or "")
        for match in AWARD_PATTERN.finditer(body):
            cents = _amount_to_cents(match.group("amount"))
            if cents is not None:
                awards.append(
                    {
                        "login": match.group("login"),
                        "amount_cents": cents,
                        "comment_id": _strict_int(comment.get("id"), minimum=1),
                        "comment_url": str(comment.get("html_url") or ""),
                    }
                )
    return awards


def _attempt_table_counts(
    bot_comments: list[Mapping[str, Any]],
) -> tuple[int, int, int]:
    active = 0
    inactive = 0
    malformed = 0
    for comment in bot_comments:
        body = str(comment.get("body") or "")
        first_cells = [
            html.unescape(re.sub(r"<[^>]+>", "", match.group("cell"))).strip()
            for match in MARKDOWN_ATTEMPT_ROW_PATTERN.finditer(body)
        ]
        first_cells.extend(
            html.unescape(re.sub(r"<[^>]+>", "", match.group("cell"))).strip()
            for match in HTML_ATTEMPT_ROW_PATTERN.finditer(body)
        )
        for cell in first_cells:
            lowered = cell.casefold()
            if lowered in {"attempt", "---"} or set(cell) <= {"-", ":", " "}:
                continue
            if "@" not in cell and not any(symbol in cell for symbol in ("🟢", "🔴", "🟡")):
                continue
            if cell.startswith("🟢"):
                active += 1
            elif cell.startswith("🔴"):
                inactive += 1
            else:
                malformed += 1
    return active, inactive, malformed


def _parse_open_board(
    document: str, *, repo_name: str, issue_number: int
) -> dict[str, Any]:
    if "id=\"bounties-container\"" not in document or "phx-value-tab=\"open\"" not in document:
        raise QualifierError("invalid_algora_board_schema", "Algora board schema changed")
    matches: list[dict[str, Any]] = []
    for row_match in BOARD_ROW_PATTERN.finditer(document):
        row = html.unescape(row_match.group("body"))
        issue_match = BOARD_ISSUE_PATTERN.search(row)
        if issue_match is None:
            continue
        row_repo = f"{issue_match.group('owner')}/{issue_match.group('repo')}"
        row_number = int(issue_match.group("number"))
        if row_repo.casefold() != repo_name.casefold() or row_number != issue_number:
            continue
        amounts = {
            cents
            for amount_match in BOARD_AMOUNT_PATTERN.finditer(row)
            if (cents := _amount_to_cents(amount_match.group("amount"))) is not None
        }
        if len(amounts) != 1:
            raise QualifierError("invalid_algora_board_row", "Algora board amount is ambiguous")
        matches.append(
            {
                "amount_cents": next(iter(amounts)),
            }
        )
    if len(matches) > 1:
        raise QualifierError("duplicate_algora_board_row", "Algora board issue is duplicated")
    return {
        "present": len(matches) == 1,
        "amount_cents": matches[0]["amount_cents"] if matches else None,
    }


def _recent_merged_prs(pulls: list[Any], *, now: datetime) -> int:
    threshold = now - timedelta(days=120)
    return sum(
        1
        for row in pulls
        if isinstance(row, Mapping)
        and (merged := parse_timestamp(row.get("merged_at"))) is not None
        and merged >= threshold
    )


def audit_candidate(
    candidate: Mapping[str, Any],
    fetch_json: JsonFetcher,
    *,
    now: datetime,
    fetch_text: TextFetcher = algora_get_text,
) -> dict[str, Any]:
    repo_name = str(candidate.get("repo") or "")
    issue_number = _strict_int(candidate.get("issue_number"), minimum=1)
    if "/" not in repo_name or issue_number is None:
        raise QualifierError("invalid_candidate_identity", "candidate identity is invalid")
    owner, repo_slug = repo_name.split("/", 1)
    repo_path = f"repos/{quote(owner, safe='')}/{quote(repo_slug, safe='')}"
    repo = _mapping(fetch_json(repo_path, None), code="invalid_repo_schema")
    issue = _mapping(
        fetch_json(f"{repo_path}/issues/{issue_number}", None),
        code="invalid_issue_schema",
    )
    comments = _fetch_all_pages(fetch_json, f"{repo_path}/issues/{issue_number}/comments", None)
    timeline = _fetch_all_pages(fetch_json, f"{repo_path}/issues/{issue_number}/timeline", None)
    if not isinstance(comments, list) or not isinstance(timeline, list):
        raise QualifierError("invalid_issue_activity_schema", "issue activity is invalid")
    comment_count = _strict_int(issue.get("comments"))
    if comment_count is None or comment_count != len(comments):
        raise QualifierError("incomplete_issue_comments", "issue comments are incomplete")
    default_branch = str(repo.get("default_branch") or "")
    if not default_branch:
        raise QualifierError("missing_default_branch", "repository has no default branch")
    tree = _mapping(
        fetch_json(
            f"{repo_path}/git/trees/{quote(default_branch, safe='')}", {"recursive": 1}
        ),
        code="invalid_tree_schema",
    )
    pulls = fetch_json(
        f"{repo_path}/pulls",
        {"state": "closed", "sort": "updated", "direction": "desc", "per_page": 20},
    )
    if not isinstance(pulls, list):
        raise QualifierError("invalid_pulls_schema", "pull request history is invalid")

    reasons: list[str] = []
    if str(repo.get("full_name") or "").casefold() != repo_name.casefold():
        reasons.append("repository_identity_mismatch")
    for key, reason in (
        ("archived", "repository_archived_or_unknown"),
        ("disabled", "repository_disabled_or_unknown"),
        ("fork", "repository_is_fork_or_unknown"),
        ("private", "repository_not_public"),
    ):
        if repo.get(key) is not False:
            reasons.append(reason)
    created = parse_timestamp(repo.get("created_at"))
    pushed = parse_timestamp(repo.get("pushed_at"))
    age_days = (now - created).total_seconds() / 86400 if created else -1.0
    idle_days = (now - pushed).total_seconds() / 86400 if pushed else 999999.0
    if age_days < MIN_REPOSITORY_AGE_DAYS:
        reasons.append("repository_too_new_for_payout_confidence")
    if idle_days > MAX_REPOSITORY_IDLE_DAYS:
        reasons.append("repository_not_recently_active")
    if _strict_int(issue.get("number"), minimum=1) != issue_number:
        reasons.append("issue_identity_mismatch")
    if str(issue.get("repository_url") or "") != _github_url(repo_path):
        reasons.append("issue_repository_mismatch")
    if issue.get("state") != "open" or issue.get("state_reason") == "completed":
        reasons.append("github_issue_not_open")
    if "pull_request" in issue:
        reasons.append("github_record_is_pull_request")
    if issue.get("locked") is not False:
        reasons.append("github_issue_locked_or_unknown")
    assignees = issue.get("assignees")
    if not isinstance(assignees, list) or assignees:
        reasons.append("github_issue_assigned_or_unknown")
    association = str(issue.get("author_association") or "").upper()
    author = issue.get("user")
    author_login = str(author.get("login") or "") if isinstance(author, Mapping) else ""
    if not author_login:
        reasons.append("issue_author_unknown")
    if author_login.casefold() == "rafaio1":
        reasons.append("self_owned_issue")
    labels = issue.get("labels")
    label_names = {
        str(row.get("name") or "").casefold()
        for row in labels
        if isinstance(row, Mapping)
    } if isinstance(labels, list) else set()
    if "rewarded" in label_names:
        reasons.append("algora_rewarded_label_present")

    bot_identity_conflicts = [
        row
        for row in comments
        if isinstance(row, Mapping)
        and str(row.get("user", {}).get("login") or "").casefold() == BOT_LOGIN.casefold()
        and not _valid_bot_comment(row)
    ]
    if bot_identity_conflicts:
        reasons.append("official_algora_bot_identity_conflict")
    bot_comments = [
        row for row in comments if isinstance(row, Mapping) and _valid_bot_comment(row)
    ]
    active_components, withdrawn_components, malformed_headers = _parse_bounty_components(
        bot_comments
    )
    awards = _parse_awards(bot_comments)
    if malformed_headers:
        reasons.append("official_algora_bounty_format_unknown")
    if withdrawn_components and not active_components:
        reasons.append("official_algora_bounty_withdrawn")
    if not active_components:
        reasons.append("official_algora_active_bounty_not_proven")
    bounty_cents = sum(int(row["amount_cents"]) for row in active_components)
    if active_components and bounty_cents < MIN_BOUNTY_CENTS:
        reasons.append("bounty_below_minimum")
    elif bounty_cents > MAX_BOUNTY_CENTS:
        reasons.append("bounty_value_requires_manual_fraud_review")
    if awards:
        reasons.append("official_algora_bounty_already_awarded")

    sponsor_totals: dict[str, int] = {}
    for component in active_components:
        sponsor = str(component["sponsor_slug"])
        sponsor_totals[sponsor] = sponsor_totals.get(sponsor, 0) + int(
            component["amount_cents"]
        )
    board_results: list[dict[str, Any]] = []
    for sponsor, expected_cents in sorted(sponsor_totals.items()):
        board_url = f"https://algora.io/{sponsor}/bounties"
        try:
            board = _parse_open_board(
                fetch_text(board_url), repo_name=repo_name, issue_number=issue_number
            )
            board_result = {
                "sponsor_slug": sponsor,
                "board_url": board_url,
                "present": board["present"],
                "expected_component_cents": expected_cents,
                "board_amount_cents": board["amount_cents"],
                "amount_matches": board["amount_cents"] == expected_cents,
                "error_code": None,
            }
        except QualifierError as error:
            board_result = {
                "sponsor_slug": sponsor,
                "board_url": board_url,
                "present": False,
                "expected_component_cents": expected_cents,
                "board_amount_cents": None,
                "amount_matches": False,
                "error_code": error.code,
            }
        board_results.append(board_result)
    board_unavailable = any(row["error_code"] for row in board_results)
    board_conflict = bool(active_components) and (
        len(board_results) != len(sponsor_totals)
        or any(not row["present"] or not row["amount_matches"] for row in board_results)
    )
    if board_unavailable:
        reasons.append("canonical_algora_open_board_unavailable")
    elif board_conflict:
        reasons.append("canonical_algora_open_board_conflict")

    latest_bot_update = max(
        (
            timestamp
            for row in bot_comments
            if (timestamp := parse_timestamp(row.get("updated_at"))) is not None
        ),
        default=None,
    )
    pending_command_comments: list[Mapping[str, Any]] = []
    claim_command_comments: list[Mapping[str, Any]] = []
    for row in comments:
        if not isinstance(row, Mapping) or _valid_bot_comment(row):
            continue
        for match in COMMAND_PATTERN.finditer(str(row.get("body") or "")):
            if int(match.group("issue")) != issue_number:
                continue
            created_at = parse_timestamp(row.get("created_at"))
            if match.group("kind").casefold() == "claim":
                claim_command_comments.append(row)
            elif latest_bot_update is None or created_at is None or created_at > latest_bot_update:
                pending_command_comments.append(row)
    active_attempt_rows, inactive_attempt_rows, malformed_attempt_rows = (
        _attempt_table_counts(bot_comments)
    )
    reward_action_count = sum(
        len(REWARD_ACTION_PATTERN.findall(str(row.get("body") or "")))
        for row in bot_comments
    )
    bot_competition_comments = [
        row
        for row in bot_comments
        if BOT_COMPETITION_PATTERN.search(str(row.get("body") or ""))
    ]
    if (
        pending_command_comments
        or claim_command_comments
        or active_attempt_rows
        or malformed_attempt_rows
        or reward_action_count
        or bot_competition_comments
    ):
        reasons.append("algora_attempt_or_claim_activity_present")
    linked_pr_events = []
    for row in timeline:
        if not isinstance(row, Mapping):
            continue
        source = row.get("source")
        source_issue = source.get("issue") if isinstance(source, Mapping) else None
        if (
            row.get("event") in {"cross-referenced", "connected"}
            and isinstance(source_issue, Mapping)
            and isinstance(source_issue.get("pull_request"), Mapping)
        ):
            linked_pr_events.append(row)
    if linked_pr_events:
        reasons.append("linked_pull_request_activity_present")

    tree_rows = tree.get("tree")
    if not isinstance(tree_rows, list) or tree.get("truncated") is not False:
        raise QualifierError("incomplete_repository_tree", "repository tree is incomplete")
    paths = {
        str(row.get("path"))
        for row in tree_rows
        if isinstance(row, Mapping) and isinstance(row.get("path"), str)
    }
    license_info = repo.get("license")
    spdx = str(license_info.get("spdx_id") or "") if isinstance(license_info, Mapping) else ""
    has_root_license_file = any(
        re.fullmatch(r"(?i)(?:licen[cs]e|copying)(?:\.[A-Za-z0-9._-]+)?", path)
        is not None
        for path in paths
    )
    license_present = bool(
        (spdx and spdx not in {"NOASSERTION", "OTHER"}) or has_root_license_file
    )
    if not license_present:
        reasons.append("license_not_proven")
    has_ci = any(
        path.startswith(".github/workflows/") and path.endswith((".yml", ".yaml"))
        for path in paths
    )
    has_tests = any(
        path.startswith(("test/", "tests/", "__tests__/"))
        or "/tests/" in path
        or "/__tests__/" in path
        or re.search(r"(?:^|/)[^/]+(?:_test|\.test|\.spec)\.[^/]+$", path) is not None
        for path in paths
    )
    if not has_ci:
        reasons.append("continuous_integration_not_proven")
    if not has_tests:
        reasons.append("test_suite_not_proven")
    merged_count = _recent_merged_prs(pulls, now=now)
    if merged_count < 1:
        reasons.append("recent_merged_pr_history_missing")

    title = str(issue.get("title") or candidate.get("title") or "").strip()
    body = str(issue.get("body") or "")
    combined = f"{title}\n{body}".casefold()
    clarity = {
        "substantive_body": len(body.strip()) >= 160,
        "acceptance_criteria": any(
            marker in body.casefold()
            for marker in ("acceptance criteria", "definition of done", "requirements", "- [ ]")
        ),
        "test_expectation": "test" in body.casefold(),
        "expected_behavior": any(
            marker in body.casefold() for marker in ("expected", "should", "must")
        ),
    }
    if sum(clarity.values()) < 3:
        reasons.append("scope_not_sufficiently_testable")
    trivial_markers = sorted(marker for marker in TRIVIAL_SCOPE_MARKERS if marker in combined)
    if trivial_markers:
        reasons.append("scope_appears_trivial_or_inflated")
    unavailable_markers = sorted(
        marker for marker in UNAUTOMATABLE_SCOPE_MARKERS if marker in combined
    )
    if unavailable_markers:
        reasons.append("scope_requires_unavailable_human_or_hardware_evidence")

    reasons = sorted(set(reasons))
    decision = "qualified" if not reasons else "rejected"
    ttl = (
        QUALIFIED_CACHE_TTL_SECONDS
        if decision == "qualified"
        else TRANSIENT_CACHE_TTL_SECONDS
        if board_unavailable
        else REJECTED_CACHE_TTL_SECONDS
    )
    face_value = round(bounty_cents / 100.0, 2)
    bounty_comment_urls = sorted(
        {
            str(row["comment_url"])
            for row in (*active_components, *withdrawn_components)
            if row.get("comment_url")
        }
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "candidate_key": candidate.get("candidate_key"),
        "repo": repo_name,
        "issue_number": issue_number,
        "title": title,
        "url": candidate.get("url"),
        "decision": decision,
        "rejection_reasons": reasons,
        "verified_at": now.isoformat(),
        "valid_until": (now + timedelta(seconds=ttl)).isoformat(),
        "gates": {
            "official_algora_bot_identity": bool(bot_comments) and not bot_identity_conflicts,
            "official_algora_active_bounty": bool(active_components) and not malformed_headers,
            "canonical_algora_open_board": bool(board_results)
            and all(row["present"] and row["amount_matches"] for row in board_results),
            "bounty_not_awarded": not awards,
            "repository_public_active": (
                repo.get("archived") is False
                and repo.get("disabled") is False
                and repo.get("fork") is False
                and repo.get("private") is False
            ),
            "repository_age_sufficient": age_days >= MIN_REPOSITORY_AGE_DAYS,
            "repository_recent": idle_days <= MAX_REPOSITORY_IDLE_DAYS,
            "license_present": license_present,
            "issue_open_unassigned": (
                issue.get("state") == "open"
                and issue.get("locked") is False
                and isinstance(assignees, list)
                and not assignees
            ),
            "payment_authority_proven": bool(active_components)
            and bool(board_results)
            and all(row["present"] and row["amount_matches"] for row in board_results),
            "no_attempt_or_claim_activity": not (
                pending_command_comments
                or claim_command_comments
                or active_attempt_rows
                or malformed_attempt_rows
                or reward_action_count
                or bot_competition_comments
            ),
            "no_linked_pull_request_activity": not linked_pr_events,
            "ci_present": has_ci,
            "tests_present": has_tests,
            "recent_merged_pr_history": merged_count >= 1,
            "scope_testable": sum(clarity.values()) >= 3,
            "scope_nontrivial": not trivial_markers,
            "scope_automatable": not unavailable_markers,
            "application_allowed": False,
            "implementation_allowed": False,
            "revenue_recognition_allowed": False,
        },
        "quality": {
            "clarity_signals": clarity,
            "repository_age_days": round(age_days, 2),
            "repository_idle_days": round(idle_days, 2),
            "recent_merged_prs_sample": merged_count,
            "issue_author_association": association or None,
            "pending_attempt_command_count": len(pending_command_comments),
            "claim_command_count": len(claim_command_comments),
            "active_attempt_table_row_count": active_attempt_rows,
            "inactive_attempt_table_row_count": inactive_attempt_rows,
            "malformed_attempt_table_row_count": malformed_attempt_rows,
            "bot_competition_comment_count": len(bot_competition_comments),
            "reward_action_link_count": reward_action_count,
            "official_award_count": len(awards),
            "active_bounty_component_count": len(active_components),
            "withdrawn_bounty_component_count": len(withdrawn_components),
            "malformed_bounty_header_count": len(malformed_headers),
            "linked_pull_request_event_count": len(linked_pr_events),
            "trivial_scope_markers": trivial_markers,
            "unautomatable_scope_markers": unavailable_markers,
            "demo_video_required_by_algora": True,
        },
        "evidence": {
            "search_api_url": _github_url(
                "search/issues",
                {"q": SEARCH_QUERY, "sort": "updated", "order": "desc", "per_page": 100},
            ),
            "repository_api_url": _github_url(repo_path),
            "issue_api_url": _github_url(f"{repo_path}/issues/{issue_number}"),
            "comments_api_url": _github_url(
                f"{repo_path}/issues/{issue_number}/comments", {"per_page": 100}
            ),
            "timeline_api_url": _github_url(
                f"{repo_path}/issues/{issue_number}/timeline", {"per_page": 100}
            ),
            "tree_api_url": _github_url(
                f"{repo_path}/git/trees/{quote(default_branch, safe='')}", {"recursive": 1}
            ),
            "pull_history_api_url": _github_url(
                f"{repo_path}/pulls",
                {"state": "closed", "sort": "updated", "direction": "desc", "per_page": 20},
            ),
            "official_bounty_comment_urls": bounty_comment_urls,
            "active_bounty_components": active_components,
            "withdrawn_bounty_components": withdrawn_components,
            "malformed_bounty_headers": malformed_headers,
            "official_awards": awards,
            "canonical_board_results": board_results,
            "repository_node_id": repo.get("node_id"),
            "issue_node_id": issue.get("node_id"),
            "license_spdx": spdx or None,
        },
        "financial_truth": {
            "face_value_usd": face_value,
            "expected_revenue_usd": None,
            "receivable_usd": 0.0,
            "realized_revenue_usd": 0.0,
        },
        "next_action": (
            "await_algora_oauth_age_payout_and_fresh_attempt_gates"
            if decision == "qualified"
            else "pivot_to_next_candidate"
        ),
    }


def terminal_rejection(
    candidate: Mapping[str, Any], *, now: datetime, error_code: str
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "candidate_key": candidate.get("candidate_key"),
        "repo": candidate.get("repo"),
        "issue_number": candidate.get("issue_number"),
        "title": candidate.get("title"),
        "url": candidate.get("url"),
        "decision": "rejected",
        "rejection_reasons": ["github_candidate_unavailable_or_exceeds_bounded_review"],
        "audit_error_code": error_code,
        "verified_at": now.isoformat(),
        "valid_until": (now + timedelta(seconds=REJECTED_CACHE_TTL_SECONDS)).isoformat(),
        "gates": {
            "application_allowed": False,
            "implementation_allowed": False,
            "revenue_recognition_allowed": False,
        },
        "financial_truth": {
            "face_value_usd": None,
            "expected_revenue_usd": None,
            "receivable_usd": 0.0,
            "realized_revenue_usd": 0.0,
        },
        "next_action": "pivot_to_next_candidate",
    }


def _cache_entry_is_fresh(entry: Any, *, now: datetime) -> bool:
    return isinstance(entry, Mapping) and (
        valid_until := parse_timestamp(entry.get("valid_until"))
    ) is not None and valid_until > now


def qualify_market(
    search_payload: Any,
    cache_payload: Mapping[str, Any],
    fetch_json: JsonFetcher,
    *,
    now: datetime | None = None,
    run_id: str | None = None,
    fetch_text: TextFetcher = algora_get_text,
) -> tuple[dict[str, Any], dict[str, Any]]:
    current = (now or utc_now()).astimezone(UTC)
    candidates, source_rejections = parse_search(search_payload)
    source_hash = _canonical_hash(search_payload)
    rate = check_rate_budget(fetch_json)
    raw_entries = cache_payload.get("entries")
    if not isinstance(raw_entries, Mapping):
        raise QualifierError("invalid_cache", "cache entries are invalid")
    entries = {
        str(key): dict(value)
        for key, value in raw_entries.items()
        if _cache_entry_is_fresh(value, now=current)
    }
    audited: list[str] = []
    for candidate in candidates:
        key = str(candidate["candidate_key"])
        if key in entries:
            continue
        try:
            entries[key] = audit_candidate(
                candidate, fetch_json, now=current, fetch_text=fetch_text
            )
        except QualifierError as error:
            if error.code not in TERMINAL_CANDIDATE_ERRORS:
                raise
            entries[key] = terminal_rejection(candidate, now=current, error_code=error.code)
        audited.append(key)
        if len(audited) >= MAX_NEW_AUDITS_PER_RUN:
            break
    records = [
        entries[str(candidate["candidate_key"])]
        for candidate in candidates
        if str(candidate["candidate_key"]) in entries
        and _cache_entry_is_fresh(entries[str(candidate["candidate_key"])], now=current)
    ]
    qualified = [row for row in records if row.get("decision") == "qualified"]
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id or uuid.uuid4().hex,
        "generated_at": current.isoformat(),
        "valid_until": (current + timedelta(minutes=10)).isoformat(),
        "source": {
            "platform": "algora",
            "official_search_query": SEARCH_QUERY,
            "official_search_api_url": _github_url(
                "search/issues",
                {"q": SEARCH_QUERY, "sort": "updated", "order": "desc", "per_page": 100},
            ),
            "source_hash": source_hash,
            "reported_total_count": search_payload.get("total_count"),
            "source_row_count": len(search_payload.get("items", [])),
            "valid_candidate_count": len(candidates),
            "source_rejection_count": len(source_rejections),
            "source_rejections": source_rejections,
        },
        "github_rate_budget": rate,
        "audit_policy": {
            "max_new_candidates_per_run": MAX_NEW_AUDITS_PER_RUN,
            "official_bot_login": BOT_LOGIN,
            "minimum_bounty_usd": MIN_BOUNTY_CENTS / 100.0,
            "maximum_automatic_review_bounty_usd": MAX_BOUNTY_CENTS / 100.0,
            "qualified_cache_ttl_seconds": QUALIFIED_CACHE_TTL_SECONDS,
            "rejected_cache_ttl_seconds": REJECTED_CACHE_TTL_SECONDS,
        },
        "newly_audited_candidate_keys": audited,
        "qualification_count": len(records),
        "qualified_count": len(qualified),
        "qualifications": records,
        "qualified_candidates": qualified,
        "workflow_contract": {
            "allowed_now": ["read_github", "qualify", "cache_receipts"],
            "application_allowed": False,
            "implementation_allowed": False,
            "requires_before_application": [
                "user_algora_github_oauth_verified",
                "user_age_and_payout_country_eligibility_verified",
                "user_payout_method_verified",
                "fresh_bounty_attempt_claim_and_pr_revalidation",
            ],
            "requires_before_implementation": [
                "accepted_attempt_or_maintainer_confirmation",
                "isolated_worktree",
                "repository_tests_green",
            ],
            "requires_before_claim": ["working_implementation", "tests_green", "short_demo_video"],
        },
        "financial_truth": {
            "qualified_face_value_usd": round(
                sum(float(row["financial_truth"]["face_value_usd"]) for row in qualified), 2
            ),
            "expected_revenue_usd": None,
            "receivable_usd": 0.0,
            "realized_revenue_usd": 0.0,
        },
    }
    payload["source_hash"] = _canonical_hash(
        {
            "source": payload["source"],
            "qualifications": records,
            "workflow_contract": payload["workflow_contract"],
        }
    )
    ordered = sorted(
        entries.items(),
        key=lambda item: str(item[1].get("verified_at") or ""),
        reverse=True,
    )[:MAX_CACHE_ENTRIES]
    return payload, {
        "schema_version": SCHEMA_VERSION,
        "updated_at": current.isoformat(),
        "entries": dict(ordered),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH))
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST_PATH))
    parser.add_argument("--cache", default=str(DEFAULT_CACHE_PATH))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_id = uuid.uuid4().hex
    output_path = Path(args.output)
    manifest_path = Path(args.manifest)
    cache_path = Path(args.cache)
    atomic_json_write(
        manifest_path,
        {
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "status": "collecting",
            "started_at": iso_now(),
            "output": str(output_path.resolve()),
        },
    )
    try:
        search_payload = gh_get_json(
            "search/issues",
            {"q": SEARCH_QUERY, "sort": "updated", "order": "desc", "per_page": 100},
        )
        cache = load_cache(cache_path)
        payload, updated_cache = qualify_market(
            search_payload,
            cache,
            gh_get_json,
            run_id=run_id,
        )
        atomic_json_write(cache_path, updated_cache)
        atomic_json_write(output_path, payload)
        atomic_json_write(
            manifest_path,
            {
                "schema_version": SCHEMA_VERSION,
                "run_id": run_id,
                "source_hash": payload["source_hash"],
                "status": "complete",
                "completed_at": iso_now(),
                "valid_until": payload["valid_until"],
                "output": str(output_path.resolve()),
                "qualification_count": payload["qualification_count"],
                "qualified_count": payload["qualified_count"],
                "application_allowed": False,
                "implementation_allowed": False,
                "receivable_usd": 0.0,
                "realized_revenue_usd": 0.0,
            },
        )
        print(
            json.dumps(
                {
                    "status": "ok",
                    "run_id": run_id,
                    "qualification_count": payload["qualification_count"],
                    "qualified_count": payload["qualified_count"],
                    "newly_audited_count": len(
                        payload["newly_audited_candidate_keys"]
                    ),
                    "receivable_usd": 0.0,
                    "realized_revenue_usd": 0.0,
                },
                sort_keys=True,
            )
        )
        return 0
    except (QualifierError, OSError, ValueError) as error:
        code = error.code if isinstance(error, QualifierError) else type(error).__name__
        atomic_json_write(
            manifest_path,
            {
                "schema_version": SCHEMA_VERSION,
                "run_id": run_id,
                "status": "failed",
                "failed_at": iso_now(),
                "output": str(output_path.resolve()),
                "error_code": code,
                "receivable_usd": 0.0,
                "realized_revenue_usd": 0.0,
            },
        )
        print(json.dumps({"status": "failed", "error_code": code}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

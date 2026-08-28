#!/usr/bin/env python3
"""Discover and qualify Opire code bounties without claiming or submitting work.

Only the official Opire API and GitHub API are read.  A qualified record is a
lead, not a receivable: this process never comments, claims, forks, opens a PR,
or recognizes revenue.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import uuid
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen

SCHEMA_VERSION = "1.0"
OPIRE_API_ROOT = "https://api.opire.dev"
GITHUB_API_ROOT = "https://api.github.com"
OPIRE_REWARDS_PATH = "/rewards"
DEFAULT_OUTPUT_PATH = Path("/Agentic/state/opire_bounty_qualifications.json")
DEFAULT_MANIFEST_PATH = Path("/Agentic/state/opire_bounty_qualifications_success.json")
DEFAULT_CACHE_PATH = Path("/Agentic/state/opire_bounty_qualification_cache.json")
USER_AGENT = "Agentic-Opire-Bounty-Qualifier/1.0"
MAX_HTTP_ATTEMPTS = 4
HTTP_TIMEOUT_SECONDS = 20
MAX_RESPONSE_BYTES = 12 * 1024 * 1024
MAX_SOURCE_ROWS = 100
MAX_NEW_AUDITS_PER_RUN = 1
MIN_GITHUB_RATE_REMAINING = 16
MIN_BOUNTY_CENTS = 2_000
MAX_BOUNTY_CENTS = 500_000
MIN_REPOSITORY_AGE_DAYS = 90
MAX_REPOSITORY_IDLE_DAYS = 90
QUALIFIED_CACHE_TTL_SECONDS = 15 * 60
REJECTED_CACHE_TTL_SECONDS = 2 * 60 * 60
MAX_CACHE_ENTRIES = 500
GITHUB_ISSUE_PATTERN = re.compile(
    r"^https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/issues/([1-9][0-9]*)$"
)
OPIRE_COMMAND_PATTERN = re.compile(r"(?im)^\s*/(?:try|claim)\b")
UNAUTOMATABLE_SCOPE_MARKERS = (
    "physical device",
    "real device",
    "requires hardware",
    "hardware required",
    "wear os",
    "record a video",
    "video demonstration",
    "proprietary sdk",
    "private api",
)
GH_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_]+$")
CANDIDATE_TERMINAL_ERROR_CODES = {
    "api_http_404",
    "api_http_410",
    "incomplete_issue_comments",
    "incomplete_issue_timeline",
    "incomplete_repository_tree",
    "untrusted_api_redirect",
}


class QualifierError(RuntimeError):
    """Official evidence could not prove a safe qualification result."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


JsonFetcher = Callable[[str], Any]


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


def timestamp_from_millis(value: Any) -> datetime | None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    try:
        return datetime.fromtimestamp(value / 1000.0, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None


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
    if not path.startswith("/"):
        raise ValueError("GitHub API path must be absolute")
    url = f"{GITHUB_API_ROOT}{path}"
    if params:
        url = f"{url}?{urlencode(params)}"
    return url


def _opire_url() -> str:
    return f"{OPIRE_API_ROOT}{OPIRE_REWARDS_PATH}?{urlencode({'page': 1, 'itemsPerPage': MAX_SOURCE_ROWS, 'minPrice': MIN_BOUNTY_CENTS // 100, 'usersTrying': 'NOBODY'})}"


def _retryable_status(status: int) -> bool:
    return status == 429 or 500 <= status <= 599


def resolve_github_token() -> str | None:
    """Resolve auth without printing or placing the token in process arguments."""
    for name in ("GITHUB_TOKEN", "GH_TOKEN"):
        value = os.environ.get(name, "").strip()
        if value:
            return value
    token_file = os.environ.get("GITHUB_TOKEN_FILE", "").strip()
    if token_file:
        try:
            value = Path(token_file).read_text(encoding="utf-8").strip()
        except OSError:
            value = ""
        if value:
            return value
    gh_config_dir = Path(os.environ.get("GH_CONFIG_DIR", "~/.config/gh")).expanduser()
    try:
        hosts_text = (gh_config_dir / "hosts.yml").read_text(encoding="utf-8")
    except OSError:
        hosts_text = ""
    for match in re.finditer(r"(?m)^\s*oauth_token:\s*([^\s#]+)\s*$", hosts_text):
        value = match.group(1).strip("'\"")
        if len(value) >= 20 and GH_TOKEN_PATTERN.fullmatch(value):
            return value
    try:
        result = subprocess.run(
            ["/usr/bin/gh", "auth", "token"],
            check=False,
            capture_output=True,
            text=True,
            timeout=8,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() if result.returncode == 0 and result.stdout.strip() else None


def http_get_json(url: str, *, github_token: str | None = None) -> Any:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in {
        "api.opire.dev",
        "api.github.com",
    }:
        raise QualifierError("untrusted_api_host", "refusing an untrusted API URL")
    original = (parsed.scheme, parsed.hostname, parsed.path, parsed.query)
    last_code = "api_unavailable"
    for attempt in range(MAX_HTTP_ATTEMPTS):
        headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
        if parsed.hostname == "api.github.com":
            headers.update(
                {
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                }
            )
            if github_token:
                headers["Authorization"] = f"Bearer {github_token}"
        try:
            request = Request(url, headers=headers, method="GET")
            with urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
                final = urlparse(str(response.geturl()))
                if (final.scheme, final.hostname, final.path, final.query) != original:
                    raise QualifierError("untrusted_api_redirect", "API redirected unexpectedly")
                content_type = str(getattr(response, "headers", {}).get("Content-Type") or "")
                if content_type.split(";", 1)[0].strip().casefold() not in {
                    "application/json",
                    "application/vnd.github+json",
                }:
                    raise QualifierError("invalid_api_content_type", "API did not return JSON")
                status = int(getattr(response, "status", response.getcode()))
                if status != 200:
                    raise QualifierError("unexpected_api_status", f"API returned HTTP {status}")
                raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise QualifierError("api_response_too_large", "API response exceeded limit")
            try:
                return json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                last_code = "invalid_api_json"
                if attempt + 1 >= MAX_HTTP_ATTEMPTS:
                    raise QualifierError(last_code, "API returned invalid JSON") from error
        except HTTPError as error:
            last_code = f"api_http_{error.code}"
            if not _retryable_status(error.code):
                raise QualifierError(last_code, "API request was rejected") from error
        except QualifierError:
            raise
        except (TimeoutError, URLError, OSError) as error:
            last_code = "api_unavailable"
            if attempt + 1 >= MAX_HTTP_ATTEMPTS:
                raise QualifierError(last_code, "API could not be reached") from error
        if attempt + 1 < MAX_HTTP_ATTEMPTS:
            time.sleep(2**attempt)
    raise QualifierError(last_code, "API retry budget exhausted")


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
        raise QualifierError("invalid_cache", "could not read qualifier cache") from error
    entries = payload.get("entries") if isinstance(payload, Mapping) else None
    if not isinstance(entries, Mapping):
        raise QualifierError("invalid_cache", "qualifier cache schema changed")
    return {"schema_version": SCHEMA_VERSION, "entries": dict(entries)}


def parse_opire_rewards(payload: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not isinstance(payload, list) or len(payload) > MAX_SOURCE_ROWS:
        raise QualifierError("invalid_opire_schema", "Opire rewards response is invalid")
    candidates: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for index, raw in enumerate(payload):
        if not isinstance(raw, Mapping):
            rejected.append({"index": index, "reason": "invalid_reward_record"})
            continue
        reward_id = str(raw.get("id") or "").strip()
        url = str(raw.get("url") or "").strip().rstrip("/")
        match = GITHUB_ISSUE_PATTERN.fullmatch(url)
        price = raw.get("pendingPrice")
        cents = _strict_int(price.get("value")) if isinstance(price, Mapping) else None
        unit = str(price.get("unit") or "") if isinstance(price, Mapping) else ""
        trying = raw.get("tryingUsers")
        claimers = raw.get("claimerUsers")
        project = raw.get("project")
        reasons: list[str] = []
        if not reward_id:
            reasons.append("missing_reward_id")
        if match is None:
            reasons.append("not_canonical_github_issue_url")
        if cents is None or unit != "USD_CENT":
            reasons.append("invalid_usd_price")
        if not isinstance(trying, list) or trying:
            reasons.append("opire_trying_users_not_zero")
        if not isinstance(claimers, list) or claimers:
            reasons.append("opire_claimers_not_zero")
        if raw.get("platform") != "GitHub":
            reasons.append("unsupported_platform")
        if not isinstance(project, Mapping) or project.get("isPublic") is not True:
            reasons.append("project_not_proven_public")
        created_at = timestamp_from_millis(raw.get("createdAt"))
        if created_at is None:
            reasons.append("invalid_reward_created_at")
        if reasons:
            rejected.append(
                {
                    "reward_id": reward_id or None,
                    "url": url or None,
                    "reasons": sorted(set(reasons)),
                }
            )
            continue
        assert match is not None and cents is not None and created_at is not None
        owner, repo, issue_number = match.groups()
        candidate = {
            "reward_id": reward_id,
            "url": url,
            "repo": f"{owner}/{repo}",
            "issue_number": int(issue_number),
            "title": str(raw.get("title") or "").strip(),
            "bounty_cents": cents,
            "face_value_usd": round(cents / 100.0, 2),
            "created_at": created_at.isoformat(),
            "source_record_hash": _canonical_hash(raw),
        }
        candidate["candidate_key"] = _canonical_hash(candidate)
        candidates.append(candidate)
    candidates.sort(key=lambda row: (row["created_at"], row["reward_id"]), reverse=True)
    return candidates, rejected


def check_github_rate(fetch_json: JsonFetcher) -> dict[str, int]:
    payload = _mapping(fetch_json(_github_url("/rate_limit")), code="invalid_rate_schema")
    resources = _mapping(payload.get("resources"), code="invalid_rate_schema")
    core = _mapping(resources.get("core"), code="invalid_rate_schema")
    limit = _strict_int(core.get("limit"), minimum=1)
    remaining = _strict_int(core.get("remaining"))
    reset = _strict_int(core.get("reset"), minimum=1)
    if limit is None or remaining is None or reset is None:
        raise QualifierError("invalid_rate_schema", "GitHub rate budget is invalid")
    if remaining < MIN_GITHUB_RATE_REMAINING:
        raise QualifierError("github_rate_budget_low", "GitHub rate budget is too low")
    return {"limit": limit, "remaining_before": remaining, "reset_epoch": reset}


def _recent_merged_prs(pulls: list[Any], *, now: datetime) -> int:
    threshold = now - timedelta(days=120)
    count = 0
    for raw in pulls:
        if not isinstance(raw, Mapping):
            continue
        merged_at = parse_timestamp(raw.get("merged_at"))
        if merged_at is not None and merged_at >= threshold:
            count += 1
    return count


def audit_candidate(
    candidate: Mapping[str, Any], fetch_json: JsonFetcher, *, now: datetime
) -> dict[str, Any]:
    repo_name = str(candidate.get("repo") or "")
    issue_number = _strict_int(candidate.get("issue_number"), minimum=1)
    if "/" not in repo_name or issue_number is None:
        raise QualifierError("invalid_candidate_identity", "candidate identity is invalid")
    owner, repo_slug = repo_name.split("/", 1)
    repo_path = f"/repos/{quote(owner, safe='')}/{quote(repo_slug, safe='')}"
    repo = _mapping(fetch_json(_github_url(repo_path)), code="invalid_repo_schema")
    issue = _mapping(
        fetch_json(_github_url(f"{repo_path}/issues/{issue_number}")),
        code="invalid_issue_schema",
    )
    comments_raw = fetch_json(
        _github_url(f"{repo_path}/issues/{issue_number}/comments", {"per_page": 100})
    )
    timeline_raw = fetch_json(
        _github_url(f"{repo_path}/issues/{issue_number}/timeline", {"per_page": 100})
    )
    if not isinstance(comments_raw, list) or not isinstance(timeline_raw, list):
        raise QualifierError("invalid_issue_activity_schema", "issue activity is invalid")
    comment_count = _strict_int(issue.get("comments"))
    if comment_count is None or comment_count != len(comments_raw) or len(comments_raw) >= 100:
        raise QualifierError("incomplete_issue_comments", "issue comments are incomplete")
    if len(timeline_raw) >= 100:
        raise QualifierError("incomplete_issue_timeline", "issue timeline is incomplete")
    default_branch = str(repo.get("default_branch") or "")
    if not default_branch:
        raise QualifierError("missing_default_branch", "repository has no default branch")
    tree = _mapping(
        fetch_json(
            _github_url(
                f"{repo_path}/git/trees/{quote(default_branch, safe='')}",
                {"recursive": 1},
            )
        ),
        code="invalid_tree_schema",
    )
    pulls_raw = fetch_json(
        _github_url(
            f"{repo_path}/pulls",
            {"state": "closed", "sort": "updated", "direction": "desc", "per_page": 20},
        )
    )
    if not isinstance(pulls_raw, list):
        raise QualifierError("invalid_pulls_schema", "pull request history is invalid")

    reasons: list[str] = []
    if str(repo.get("full_name") or "").casefold() != repo_name.casefold():
        reasons.append("repository_identity_mismatch")
    if repo.get("archived") is not False:
        reasons.append("repository_archived_or_unknown")
    if repo.get("disabled") is not False:
        reasons.append("repository_disabled_or_unknown")
    if repo.get("fork") is not False:
        reasons.append("repository_is_fork_or_unknown")
    if repo.get("private") is not False:
        reasons.append("repository_not_public")
    created = parse_timestamp(repo.get("created_at"))
    repository_age_days = (now - created).total_seconds() / 86400 if created else -1.0
    if repository_age_days < MIN_REPOSITORY_AGE_DAYS:
        reasons.append("repository_too_new_for_payout_confidence")
    pushed = parse_timestamp(repo.get("pushed_at"))
    repository_idle_days = (now - pushed).total_seconds() / 86400 if pushed else 999999.0
    if repository_idle_days > MAX_REPOSITORY_IDLE_DAYS:
        reasons.append("repository_not_recently_active")
    license_info = repo.get("license")
    spdx = str(license_info.get("spdx_id") or "") if isinstance(license_info, Mapping) else ""
    license_present = bool(spdx and spdx not in {"NOASSERTION", "OTHER"})
    if not license_present:
        reasons.append("license_not_proven")

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
    if association not in {"OWNER", "MEMBER", "COLLABORATOR"}:
        reasons.append("issue_payment_authority_not_proven")
    author = issue.get("user")
    author_login = str(author.get("login") or "") if isinstance(author, Mapping) else ""
    if not author_login:
        reasons.append("issue_author_unknown")
    if author_login.casefold() == "rafaio1":
        reasons.append("self_owned_issue")

    command_comments = [
        row
        for row in comments_raw
        if isinstance(row, Mapping)
        and OPIRE_COMMAND_PATTERN.search(str(row.get("body") or ""))
    ]
    if command_comments:
        reasons.append("opire_attempt_or_claim_comment_present")
    linked_pr_events = []
    for raw in timeline_raw:
        if not isinstance(raw, Mapping):
            continue
        source = raw.get("source")
        source_issue = source.get("issue") if isinstance(source, Mapping) else None
        if (
            raw.get("event") in {"cross-referenced", "connected"}
            and isinstance(source_issue, Mapping)
            and isinstance(source_issue.get("pull_request"), Mapping)
        ):
            linked_pr_events.append(raw)
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
    recent_merged_prs = _recent_merged_prs(pulls_raw, now=now)
    if recent_merged_prs < 1:
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
    scope_markers = sorted(
        marker for marker in UNAUTOMATABLE_SCOPE_MARKERS if marker in combined
    )
    if scope_markers:
        reasons.append("scope_requires_unavailable_human_or_hardware_evidence")

    cents = _strict_int(candidate.get("bounty_cents"), minimum=1)
    if cents is None or cents < MIN_BOUNTY_CENTS:
        reasons.append("bounty_below_minimum")
    if cents is None or cents > MAX_BOUNTY_CENTS:
        reasons.append("bounty_value_requires_manual_fraud_review")
    reasons = sorted(set(reasons))
    decision = "qualified" if not reasons else "rejected"
    ttl = QUALIFIED_CACHE_TTL_SECONDS if decision == "qualified" else REJECTED_CACHE_TTL_SECONDS
    return {
        "schema_version": SCHEMA_VERSION,
        "candidate_key": candidate.get("candidate_key"),
        "reward_id": candidate.get("reward_id"),
        "repo": repo_name,
        "issue_number": issue_number,
        "title": title,
        "url": candidate.get("url"),
        "decision": decision,
        "rejection_reasons": reasons,
        "verified_at": now.isoformat(),
        "valid_until": (now + timedelta(seconds=ttl)).isoformat(),
        "gates": {
            "official_opire_usd_reward": cents is not None,
            "opire_trying_users_zero": True,
            "opire_claimers_zero": True,
            "repository_public_active": (
                repo.get("archived") is False
                and repo.get("disabled") is False
                and repo.get("fork") is False
                and repo.get("private") is False
            ),
            "repository_age_sufficient": repository_age_days >= MIN_REPOSITORY_AGE_DAYS,
            "repository_recent": repository_idle_days <= MAX_REPOSITORY_IDLE_DAYS,
            "license_present": license_present,
            "issue_open_unassigned": (
                issue.get("state") == "open"
                and issue.get("locked") is False
                and isinstance(assignees, list)
                and not assignees
            ),
            "payment_authority_proven": association in {"OWNER", "MEMBER", "COLLABORATOR"},
            "no_attempt_or_claim_comments": not command_comments,
            "no_linked_pull_request_activity": not linked_pr_events,
            "ci_present": has_ci,
            "tests_present": has_tests,
            "recent_merged_pr_history": recent_merged_prs >= 1,
            "scope_testable": sum(clarity.values()) >= 3,
            "scope_automatable": not scope_markers,
            "application_allowed": False,
            "implementation_allowed": False,
            "revenue_recognition_allowed": False,
        },
        "quality": {
            "clarity_signals": clarity,
            "repository_age_days": round(repository_age_days, 2),
            "repository_idle_days": round(repository_idle_days, 2),
            "recent_merged_prs_sample": recent_merged_prs,
            "attempt_or_claim_comment_count": len(command_comments),
            "linked_pull_request_event_count": len(linked_pr_events),
            "unautomatable_scope_markers": scope_markers,
        },
        "evidence": {
            "opire_api_url": _opire_url(),
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
            "repository_node_id": repo.get("node_id"),
            "issue_node_id": issue.get("node_id"),
            "license_spdx": spdx or None,
        },
        "financial_truth": {
            "face_value_usd": round((cents or 0) / 100.0, 2),
            "expected_revenue_usd": None,
            "receivable_usd": 0.0,
            "realized_revenue_usd": 0.0,
        },
        "next_action": (
            "await_opire_login_stripe_connect_and_fresh_claim_gates"
            if decision == "qualified"
            else "pivot_to_next_candidate"
        ),
    }


def _cache_entry_is_fresh(entry: Any, *, now: datetime) -> bool:
    if not isinstance(entry, Mapping):
        return False
    valid_until = parse_timestamp(entry.get("valid_until"))
    return valid_until is not None and valid_until > now


def unavailable_candidate_receipt(
    candidate: Mapping[str, Any], *, now: datetime, error_code: str
) -> dict[str, Any]:
    """Turn a proven missing GitHub resource into a durable negative receipt."""
    cents = _strict_int(candidate.get("bounty_cents"), minimum=1) or 0
    unavailable_codes = {"api_http_404", "api_http_410", "untrusted_api_redirect"}
    rejection_reason = (
        "github_issue_or_repository_unavailable"
        if error_code in unavailable_codes
        else "github_candidate_exceeds_bounded_review"
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "candidate_key": candidate.get("candidate_key"),
        "reward_id": candidate.get("reward_id"),
        "repo": candidate.get("repo"),
        "issue_number": candidate.get("issue_number"),
        "title": candidate.get("title"),
        "url": candidate.get("url"),
        "decision": "rejected",
        "rejection_reasons": [rejection_reason],
        "audit_error_code": error_code,
        "verified_at": now.isoformat(),
        "valid_until": (now + timedelta(seconds=REJECTED_CACHE_TTL_SECONDS)).isoformat(),
        "gates": {
            "official_opire_usd_reward": True,
            "github_resource_available": False,
            "application_allowed": False,
            "implementation_allowed": False,
            "revenue_recognition_allowed": False,
        },
        "evidence": {"opire_api_url": _opire_url(), "github_url": candidate.get("url")},
        "financial_truth": {
            "face_value_usd": round(cents / 100.0, 2),
            "expected_revenue_usd": None,
            "receivable_usd": 0.0,
            "realized_revenue_usd": 0.0,
        },
        "next_action": "pivot_to_next_candidate",
    }


def qualify_market(
    opire_payload: Any,
    cache_payload: Mapping[str, Any],
    fetch_json: JsonFetcher,
    *,
    now: datetime | None = None,
    run_id: str | None = None,
    github_authenticated: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    current = (now or utc_now()).astimezone(UTC)
    candidates, source_rejections = parse_opire_rewards(opire_payload)
    source_hash = _canonical_hash(opire_payload)
    rate = check_github_rate(fetch_json)
    raw_entries = cache_payload.get("entries")
    if not isinstance(raw_entries, Mapping):
        raise QualifierError("invalid_cache", "qualifier cache entries are invalid")
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
            entries[key] = audit_candidate(candidate, fetch_json, now=current)
        except QualifierError as error:
            if error.code not in CANDIDATE_TERMINAL_ERROR_CODES:
                raise
            entries[key] = unavailable_candidate_receipt(
                candidate,
                now=current,
                error_code=error.code,
            )
        audited.append(key)
        if len(audited) >= MAX_NEW_AUDITS_PER_RUN:
            break
    current_records = [
        entries[str(candidate["candidate_key"])]
        for candidate in candidates
        if str(candidate["candidate_key"]) in entries
        and _cache_entry_is_fresh(entries[str(candidate["candidate_key"])], now=current)
    ]
    qualified = [record for record in current_records if record.get("decision") == "qualified"]
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id or uuid.uuid4().hex,
        "generated_at": current.isoformat(),
        "valid_until": (current + timedelta(minutes=15)).isoformat(),
        "source": {
            "platform": "opire",
            "official_api_url": _opire_url(),
            "source_hash": source_hash,
            "source_row_count": len(opire_payload),
            "valid_candidate_count": len(candidates),
            "source_rejection_count": len(source_rejections),
            "source_rejections": source_rejections,
        },
        "github_rate_budget": rate,
        "audit_policy": {
            "max_new_candidates_per_run": MAX_NEW_AUDITS_PER_RUN,
            "github_authenticated": github_authenticated,
            "minimum_bounty_usd": MIN_BOUNTY_CENTS / 100.0,
            "maximum_automatic_review_bounty_usd": MAX_BOUNTY_CENTS / 100.0,
            "qualified_cache_ttl_seconds": QUALIFIED_CACHE_TTL_SECONDS,
            "rejected_cache_ttl_seconds": REJECTED_CACHE_TTL_SECONDS,
        },
        "newly_audited_candidate_keys": audited,
        "qualification_count": len(current_records),
        "qualified_count": len(qualified),
        "qualifications": current_records,
        "qualified_candidates": qualified,
        "workflow_contract": {
            "allowed_now": ["read_official_opire_api", "read_github", "qualify", "cache_receipts"],
            "application_allowed": False,
            "implementation_allowed": False,
            "requires_before_application": [
                "user_opire_oauth_login_verified",
                "user_terms_and_age_verified",
                "user_stripe_connect_payout_verified",
                "fresh_opire_reward_revalidation",
                "fresh_github_issue_competition_revalidation",
            ],
            "requires_before_implementation": [
                "accepted_attempt_or_maintainer_confirmation",
                "isolated_worktree",
                "repository_tests_green",
            ],
        },
        "financial_truth": {
            "qualified_face_value_usd": round(
                sum(float(record["financial_truth"]["face_value_usd"]) for record in qualified),
                2,
            ),
            "expected_revenue_usd": None,
            "receivable_usd": 0.0,
            "realized_revenue_usd": 0.0,
        },
    }
    payload["source_hash"] = _canonical_hash(
        {
            "source": payload["source"],
            "qualifications": current_records,
            "workflow_contract": payload["workflow_contract"],
        }
    )
    ordered = sorted(
        entries.items(),
        key=lambda item: str(item[1].get("verified_at") or ""),
        reverse=True,
    )[:MAX_CACHE_ENTRIES]
    cache = {
        "schema_version": SCHEMA_VERSION,
        "updated_at": current.isoformat(),
        "entries": dict(ordered),
    }
    return payload, cache


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
        token = resolve_github_token()

        def fetch(url: str) -> Any:
            return http_get_json(url, github_token=token)

        opire_payload = fetch(_opire_url())
        cache = load_cache(cache_path)
        payload, updated_cache = qualify_market(
            opire_payload,
            cache,
            fetch,
            run_id=run_id,
            github_authenticated=bool(token),
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
                    "audited_one": bool(payload["newly_audited_candidate_keys"]),
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

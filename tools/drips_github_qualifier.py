#!/usr/bin/env python3
"""Qualify at most one Drips candidate per run against live public GitHub data.

This process is deliberately read-only. It never authenticates, applies for
work, comments, opens a pull request, or treats Drips Points as USD revenue.
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

GITHUB_API_ROOT = "https://api.github.com"
SCHEMA_VERSION = "1.0"
DEFAULT_DRIPS_PATH = Path("/Agentic/state/drips_wave_candidates.json")
DEFAULT_DRIPS_MANIFEST_PATH = Path("/Agentic/state/drips_wave_candidates_success.json")
DEFAULT_OUTPUT_PATH = Path("/Agentic/state/drips_github_qualifications.json")
DEFAULT_MANIFEST_PATH = Path("/Agentic/state/drips_github_qualifications_success.json")
DEFAULT_CACHE_PATH = Path("/Agentic/state/drips_github_qualification_cache.json")
MAX_HTTP_ATTEMPTS = 4
HTTP_TIMEOUT_SECONDS = 20
MAX_RESPONSE_BYTES = 12 * 1024 * 1024
MIN_RATE_REMAINING = 16
QUALIFIED_CACHE_TTL_SECONDS = 15 * 60
REJECTED_CACHE_TTL_SECONDS = 60 * 60
MAX_CACHE_ENTRIES = 200
MIN_SCORE = 75.0
USER_AGENT = "Agentic-Drips-GitHub-Qualifier/1.0"
REPO_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
CODE_SPAN_PATTERN = re.compile(r"`([^`\r\n]{1,180})`")
TRIVIAL_PATTERNS = (
    "typo",
    "readme only",
    "commented-out",
    "commented out",
    "dead code",
    "rename variable",
    "formatting only",
    "lint only",
    "bump dependency",
    "update dependency",
    "code quality] remove",
)
GH_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_]+$")
GITHUB_TOKEN: str | None = None


class QualifierError(RuntimeError):
    """Live evidence could not prove a safe qualification result."""

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


def http_get_json(url: str) -> Any:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "api.github.com":
        raise QualifierError("untrusted_github_host", "refusing a non-GitHub API URL")
    last_code = "github_api_unavailable"
    for attempt in range(MAX_HTTP_ATTEMPTS):
        try:
            headers = {
                "Accept": "application/vnd.github+json",
                "User-Agent": USER_AGENT,
                "X-GitHub-Api-Version": "2022-11-28",
            }
            if GITHUB_TOKEN:
                headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
            request = Request(url, headers=headers, method="GET")
            with urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
                final = urlparse(str(response.geturl()))
                if (
                    final.scheme != "https"
                    or final.hostname != "api.github.com"
                    or final.path != parsed.path
                    or final.query != parsed.query
                ):
                    raise QualifierError(
                        "untrusted_github_redirect",
                        "GitHub API redirected unexpectedly",
                    )
                content_type = getattr(response, "headers", {}).get("Content-Type")
                if (
                    str(content_type or "").split(";", 1)[0].strip().casefold()
                    not in {"application/json", "application/vnd.github+json"}
                ):
                    raise QualifierError(
                        "invalid_github_content_type",
                        "GitHub API did not return JSON",
                    )
                status = int(getattr(response, "status", response.getcode()))
                if status != 200:
                    raise QualifierError(
                        "unexpected_github_status",
                        f"GitHub API returned HTTP {status}",
                    )
                raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise QualifierError(
                    "github_response_too_large",
                    "GitHub API response exceeded the size limit",
                )
            try:
                return json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                last_code = "invalid_github_json"
                if attempt + 1 >= MAX_HTTP_ATTEMPTS:
                    raise QualifierError(last_code, "GitHub API returned invalid JSON") from error
        except HTTPError as error:
            last_code = f"github_http_{error.code}"
            if not _retryable_status(error.code):
                raise QualifierError(last_code, "GitHub API request was rejected") from error
        except QualifierError:
            raise
        except (TimeoutError, URLError, OSError) as error:
            last_code = "github_api_unavailable"
            if attempt + 1 >= MAX_HTTP_ATTEMPTS:
                raise QualifierError(last_code, "GitHub API could not be reached") from error
        if attempt + 1 < MAX_HTTP_ATTEMPTS:
            time.sleep(2**attempt)
    raise QualifierError(last_code, "GitHub API retry budget exhausted")


def atomic_json_write(path: Path, payload: Mapping[str, Any]) -> None:
    destination = path.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        dir=destination.parent,
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


def load_json(path: Path, *, code: str) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise QualifierError(code, f"could not read {path}") from error
    return _mapping(value, code=code)


def validate_drips_snapshot(
    payload: Mapping[str, Any],
    manifest: Mapping[str, Any],
    *,
    now: datetime,
) -> None:
    if manifest.get("status") != "complete":
        raise QualifierError("drips_manifest_incomplete", "Drips scan is not complete")
    if payload.get("run_id") != manifest.get("run_id"):
        raise QualifierError("drips_run_mismatch", "Drips run ids do not match")
    if payload.get("source_hash") != manifest.get("source_hash"):
        raise QualifierError("drips_hash_mismatch", "Drips source hashes do not match")
    valid_until = parse_timestamp(payload.get("valid_until"))
    if valid_until is None or valid_until <= now + timedelta(seconds=60):
        raise QualifierError("drips_snapshot_stale", "Drips snapshot is too close to expiry")
    scan = _mapping(payload.get("scan"), code="invalid_drips_scan")
    if scan.get("drips_detail_evidence_complete") is not True:
        raise QualifierError("drips_detail_incomplete", "Drips details were not fully checked")
    if payload.get("financial_truth", {}).get("realized_revenue_usd") != 0.0:
        raise QualifierError("invalid_financial_truth", "discovery cannot contain revenue")
    if not isinstance(payload.get("candidates"), list):
        raise QualifierError("invalid_drips_candidates", "Drips candidate list is invalid")


def check_rate_budget(fetch_json: JsonFetcher) -> dict[str, int]:
    payload = _mapping(fetch_json(_github_url("/rate_limit")), code="invalid_rate_schema")
    resources = _mapping(payload.get("resources"), code="invalid_rate_schema")
    core = _mapping(resources.get("core"), code="invalid_rate_schema")
    remaining = _strict_int(core.get("remaining"))
    limit = _strict_int(core.get("limit"), minimum=1)
    reset = _strict_int(core.get("reset"), minimum=1)
    if remaining is None or limit is None or reset is None:
        raise QualifierError("invalid_rate_schema", "GitHub rate budget is invalid")
    if remaining < MIN_RATE_REMAINING:
        raise QualifierError("github_rate_budget_low", "GitHub public rate budget is too low")
    return {"limit": limit, "remaining_before": remaining, "reset_epoch": reset}


def _candidate_key(candidate: Mapping[str, Any]) -> str:
    stable = {
        "drips_issue_id": candidate.get("drips_issue_id"),
        "repo": candidate.get("repo"),
        "issue_number": candidate.get("issue_number"),
        "github_updated_at": candidate.get("github_updated_at"),
        "points": candidate.get("points"),
        "complexity": candidate.get("complexity"),
        "pending_applications_count": candidate.get("pending_applications_count"),
    }
    return _canonical_hash(stable)


def _reference_tokens(body: str) -> list[str]:
    references: set[str] = set()
    for raw in CODE_SPAN_PATTERN.findall(body):
        value = raw.strip().replace("\\", "/")
        if (
            not value
            or value.startswith(("http://", "https://", "--"))
            or " " in value
            or value in {"true", "false", "null"}
        ):
            continue
        value = value.removeprefix("./").lstrip("/").split("#", 1)[0]
        value = re.sub(r":\d+(?::\d+)?$", "", value)
        if "/" in value or re.search(r"\.[A-Za-z0-9]{1,8}$", value):
            references.add(value.rstrip("/"))
    return sorted(reference for reference in references if reference)


def _path_is_grounded(reference: str, tree_paths: set[str]) -> bool:
    if reference in tree_paths or any(path.startswith(f"{reference}/") for path in tree_paths):
        return True
    parent = reference.rsplit("/", 1)[0] if "/" in reference else ""
    return bool(parent) and (
        parent in tree_paths or any(path.startswith(f"{parent}/") for path in tree_paths)
    )


def _recent_merged_prs(pulls: list[Any], *, now: datetime) -> int:
    count = 0
    threshold = now - timedelta(days=120)
    for raw in pulls:
        if not isinstance(raw, Mapping) or raw.get("merged_at") is None:
            continue
        merged_at = parse_timestamp(raw.get("merged_at"))
        if merged_at is not None and merged_at >= threshold:
            count += 1
    return count


def audit_candidate(
    candidate: Mapping[str, Any],
    fetch_json: JsonFetcher,
    *,
    now: datetime,
    drips_source_hash: str,
    wave_end_at: str,
) -> dict[str, Any]:
    repo_name = str(candidate.get("repo") or "")
    issue_number = _strict_int(candidate.get("issue_number"), minimum=1)
    if not REPO_PATTERN.fullmatch(repo_name) or issue_number is None:
        raise QualifierError("invalid_candidate_identity", "candidate identity is invalid")
    owner, repo_slug = repo_name.split("/", 1)
    repo_path = f"/repos/{quote(owner, safe='')}/{quote(repo_slug, safe='')}"
    repo = _mapping(fetch_json(_github_url(repo_path)), code="invalid_repo_schema")
    issue = _mapping(
        fetch_json(_github_url(f"{repo_path}/issues/{issue_number}")),
        code="invalid_issue_schema",
    )
    comments_raw = fetch_json(
        _github_url(
            f"{repo_path}/issues/{issue_number}/comments",
            {"per_page": 100},
        )
    )
    timeline_raw = fetch_json(
        _github_url(
            f"{repo_path}/issues/{issue_number}/timeline",
            {"per_page": 100},
        )
    )
    if not isinstance(comments_raw, list) or not isinstance(timeline_raw, list):
        raise QualifierError(
            "invalid_issue_activity_schema",
            "issue comments or timeline are invalid",
        )
    issue_comment_count = _strict_int(issue.get("comments"))
    if issue_comment_count is None or issue_comment_count != len(comments_raw):
        raise QualifierError(
            "incomplete_issue_comments",
            "issue comments could not be proven complete",
        )
    if len(timeline_raw) >= 100:
        raise QualifierError(
            "incomplete_issue_timeline",
            "issue timeline may be paginated beyond the bounded request",
        )
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
            {
                "state": "closed",
                "sort": "updated",
                "direction": "desc",
                "per_page": 20,
            },
        )
    )
    if not isinstance(pulls_raw, list):
        raise QualifierError("invalid_pulls_schema", "pull request history is invalid")

    reasons: list[str] = []
    full_name = str(repo.get("full_name") or "")
    if full_name.casefold() != repo_name.casefold():
        reasons.append("repository_identity_mismatch")
    if repo.get("archived") is not False:
        reasons.append("repository_archived_or_unknown")
    if repo.get("disabled") is not False:
        reasons.append("repository_disabled_or_unknown")
    if repo.get("fork") is not False:
        reasons.append("repository_is_fork_or_unknown")
    if repo.get("private") is not False:
        reasons.append("repository_not_public")
    license_info = repo.get("license")
    spdx = str(license_info.get("spdx_id") or "") if isinstance(license_info, Mapping) else ""
    license_present = bool(spdx and spdx not in {"NOASSERTION", "OTHER"})
    if not license_present:
        reasons.append("license_not_proven")
    pushed_at = parse_timestamp(repo.get("pushed_at"))
    recent_push = pushed_at is not None and pushed_at >= now - timedelta(days=90)
    if not recent_push:
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
    author = issue.get("user")
    author_login = str(author.get("login") or "") if isinstance(author, Mapping) else ""
    if not author_login:
        reasons.append("issue_author_unknown")
    if author_login.casefold() == "rafaio1":
        reasons.append("self_owned_issue")
    application_comments = [
        raw
        for raw in comments_raw
        if isinstance(raw, Mapping)
        and "wave:application-id" in str(raw.get("body") or "").casefold()
    ]
    if application_comments:
        reasons.append("github_application_comment_present")
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
    tree_paths = {
        str(row.get("path"))
        for row in tree_rows
        if isinstance(row, Mapping) and isinstance(row.get("path"), str)
    }
    has_ci = any(
        path.startswith(".github/workflows/") and path.endswith((".yml", ".yaml"))
        for path in tree_paths
    )
    has_tests = any(
        path.startswith(("test/", "tests/", "__tests__/"))
        or "/tests/" in path
        or "/__tests__/" in path
        or re.search(r"(?:^|/)[^/]+(?:_test|\.test|\.spec)\.[^/]+$", path) is not None
        for path in tree_paths
    )
    if not has_ci:
        reasons.append("continuous_integration_not_proven")
    if not has_tests:
        reasons.append("test_suite_not_proven")

    title = str(issue.get("title") or candidate.get("title") or "").strip()
    body = str(issue.get("body") or "")
    combined = f"{title}\n{body}".casefold()
    trivial_scope = any(pattern in combined for pattern in TRIVIAL_PATTERNS)
    if trivial_scope:
        reasons.append("scope_appears_trivial_or_inflated")
    references = _reference_tokens(body)
    missing_references = [
        reference for reference in references if not _path_is_grounded(reference, tree_paths)
    ]
    if missing_references:
        reasons.append("referenced_repository_paths_missing")

    clarity_signals = {
        "substantive_body": len(body.strip()) >= 200,
        "acceptance_criteria": any(
            marker in body.casefold()
            for marker in ("acceptance criteria", "definition of done", "requirements", "- [ ]")
        ),
        "test_expectation": "test" in body.casefold(),
        "expected_behavior": any(
            marker in body.casefold() for marker in ("expected", "should", "must")
        ),
    }
    clarity_count = sum(clarity_signals.values())
    if clarity_count < 3:
        reasons.append("scope_not_sufficiently_testable")

    points = _strict_int(candidate.get("points"), minimum=1)
    complexity = str(candidate.get("complexity") or "").casefold()
    expected_points = {"small": 100, "medium": 150, "large": 200}.get(complexity)
    if points is None or expected_points != points:
        reasons.append("points_complexity_inconsistent")
    labels = issue.get("labels")
    if not isinstance(labels, list):
        reasons.append("github_labels_unknown")
        label_points: list[int] = []
    else:
        label_points = []
        for raw in labels:
            name = str(raw.get("name") or "") if isinstance(raw, Mapping) else str(raw)
            match = re.search(
                r"(?:^|\D)(100|150|200)[-_ ]?points?(?:$|\D)",
                name.casefold(),
            )
            if match:
                label_points.append(int(match.group(1)))
    label_points = sorted(set(label_points))
    if len(label_points) > 1:
        reasons.append("github_points_labels_ambiguous")
    elif label_points and points != label_points[0]:
        reasons.append("drips_github_points_mismatch")
    broad_scope_markers = (
        "integration test",
        "benchmark",
        "coverage",
        "smart contract",
        "documentation",
        "end-to-end",
        "e2e",
    )
    scope_exceeds_declared_complexity = complexity == "small" and sum(
        marker in combined for marker in broad_scope_markers
    ) >= 2
    if scope_exceeds_declared_complexity:
        reasons.append("scope_exceeds_declared_complexity")
    pending = _strict_int(candidate.get("pending_applications_count"))
    if pending != 0:
        reasons.append("competition_not_zero")

    active_wave = candidate.get("wave_id")
    if not isinstance(active_wave, str) or not active_wave:
        reasons.append("active_wave_identity_missing")
    drips_end = parse_timestamp(wave_end_at)
    effort_hours = {"small": 8, "medium": 16, "large": 24}.get(complexity, 48)
    deadline_margin_hours = (
        (drips_end - now).total_seconds() / 3600.0 - effort_hours - 24.0
        if drips_end is not None
        else -1.0
    )
    if deadline_margin_hours < 0:
        reasons.append("insufficient_wave_deadline_margin")

    recent_merged_prs = _recent_merged_prs(pulls_raw, now=now)
    if recent_merged_prs < 1:
        reasons.append("recent_merged_pr_history_missing")

    point_score = {100: 15.0, 150: 22.5, 200: 30.0}.get(points or 0, 0.0)
    deadline_score = min(20.0, max(0.0, deadline_margin_hours / 24.0 * 10.0))
    competition_score = 20.0 if pending == 0 else 0.0
    clarity_score = 15.0 * clarity_count / len(clarity_signals)
    reliability_score = sum(
        (
            4.0 if license_present else 0.0,
            3.0 if has_ci else 0.0,
            3.0 if has_tests else 0.0,
            2.0 if recent_push else 0.0,
            3.0 if recent_merged_prs >= 1 else 0.0,
        )
    )
    score = round(
        point_score + deadline_score + competition_score + clarity_score + reliability_score,
        4,
    )
    if score < MIN_SCORE:
        reasons.append("qualification_score_below_threshold")
    reasons = sorted(set(reasons))
    decision = "qualified" if not reasons else "rejected"
    cache_ttl = (
        QUALIFIED_CACHE_TTL_SECONDS if decision == "qualified" else REJECTED_CACHE_TTL_SECONDS
    )
    valid_until = now + timedelta(seconds=cache_ttl)
    return {
        "schema_version": SCHEMA_VERSION,
        "candidate_key": _candidate_key(candidate),
        "candidate_id": str(candidate.get("id") or ""),
        "drips_issue_id": str(candidate.get("drips_issue_id") or ""),
        "drips_source_hash": drips_source_hash,
        "repo": repo_name,
        "issue_number": issue_number,
        "title": title,
        "decision": decision,
        "score": score,
        "minimum_score": MIN_SCORE,
        "rejection_reasons": reasons,
        "verified_at": now.isoformat(),
        "valid_until": valid_until.isoformat(),
        "gates": {
            "repository_identity": full_name.casefold() == repo_name.casefold(),
            "repository_public_active": (
                repo.get("archived") is False
                and repo.get("disabled") is False
                and repo.get("fork") is False
                and repo.get("private") is False
            ),
            "license_present": license_present,
            "recent_repository_activity": recent_push,
            "github_issue_open_unassigned": (
                issue.get("state") == "open"
                and issue.get("locked") is False
                and isinstance(assignees, list)
                and not assignees
            ),
            "repository_tree_complete": True,
            "referenced_paths_grounded": not missing_references,
            "ci_present": has_ci,
            "tests_present": has_tests,
            "scope_nontrivial": not trivial_scope,
            "scope_testable": clarity_count >= 3,
            "no_application_comments": not application_comments,
            "no_linked_pull_request_activity": not linked_pr_events,
            "points_labels_consistent": len(label_points) <= 1
            and (not label_points or points == label_points[0]),
            "scope_matches_declared_complexity": not scope_exceeds_declared_complexity,
            "recent_merged_pr_history": recent_merged_prs >= 1,
            "deadline_margin": deadline_margin_hours >= 0,
            "application_allowed": False,
            "implementation_allowed": False,
            "automation_eligible": False,
        },
        "quality": {
            "clarity_signals": clarity_signals,
            "referenced_paths": references,
            "missing_referenced_paths": missing_references,
            "github_points_labels": label_points,
            "application_comment_count": len(application_comments),
            "linked_pull_request_event_count": len(linked_pr_events),
            "recent_merged_prs_sample": recent_merged_prs,
            "deadline_margin_hours": round(deadline_margin_hours, 2),
        },
        "evidence": {
            "repository_api_url": _github_url(repo_path),
            "issue_api_url": _github_url(f"{repo_path}/issues/{issue_number}"),
            "issue_comments_api_url": _github_url(
                f"{repo_path}/issues/{issue_number}/comments",
                {"per_page": 100},
            ),
            "issue_timeline_api_url": _github_url(
                f"{repo_path}/issues/{issue_number}/timeline",
                {"per_page": 100},
            ),
            "tree_api_url": _github_url(
                f"{repo_path}/git/trees/{quote(default_branch, safe='')}",
                {"recursive": 1},
            ),
            "pull_history_api_url": _github_url(
                f"{repo_path}/pulls",
                {
                    "state": "closed",
                    "sort": "updated",
                    "direction": "desc",
                    "per_page": 20,
                },
            ),
            "repository_node_id": repo.get("node_id"),
            "issue_node_id": issue.get("node_id"),
            "default_branch": default_branch,
            "repository_pushed_at": repo.get("pushed_at"),
            "issue_updated_at": issue.get("updated_at"),
            "license_spdx": spdx or None,
        },
        "financial_truth": {
            "points": points,
            "points_value_usd": None,
            "expected_revenue_usd": None,
            "realized_revenue_usd": 0.0,
        },
        "next_action": (
            "await_identity_kyc_quota_turnstile_and_fresh_application_checks"
            if decision == "qualified"
            else "pivot_to_next_candidate"
        ),
    }


def _load_cache(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": SCHEMA_VERSION, "entries": {}}
    payload = load_json(path, code="invalid_qualification_cache")
    entries = payload.get("entries")
    if not isinstance(entries, Mapping):
        raise QualifierError("invalid_qualification_cache", "cache entries are invalid")
    return {"schema_version": SCHEMA_VERSION, "entries": dict(entries)}


def _cache_entry_is_fresh(entry: Any, *, now: datetime) -> bool:
    if not isinstance(entry, Mapping):
        return False
    valid_until = parse_timestamp(entry.get("valid_until"))
    return valid_until is not None and valid_until > now


def qualify_market(
    drips_payload: Mapping[str, Any],
    drips_manifest: Mapping[str, Any],
    cache_payload: Mapping[str, Any],
    fetch_json: JsonFetcher = http_get_json,
    *,
    now: datetime | None = None,
    run_id: str | None = None,
    github_authenticated: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    current = (now or utc_now()).astimezone(UTC)
    validate_drips_snapshot(drips_payload, drips_manifest, now=current)
    rate = check_rate_budget(fetch_json)
    candidates = drips_payload.get("candidates")
    assert isinstance(candidates, list)
    active_wave = _mapping(drips_payload.get("active_wave"), code="invalid_active_wave")
    wave_end_at = str(active_wave.get("end_at") or "")
    if parse_timestamp(wave_end_at) is None:
        raise QualifierError("invalid_active_wave", "Drips Wave end time is invalid")
    raw_entries = cache_payload.get("entries")
    if not isinstance(raw_entries, Mapping):
        raise QualifierError("invalid_qualification_cache", "cache entries are invalid")
    entries = {
        str(key): dict(value)
        for key, value in raw_entries.items()
        if _cache_entry_is_fresh(value, now=current)
    }
    audited_key: str | None = None
    for raw in candidates:
        candidate = _mapping(raw, code="invalid_drips_candidate")
        key = _candidate_key(candidate)
        if key in entries:
            continue
        entries[key] = audit_candidate(
            candidate,
            fetch_json,
            now=current,
            drips_source_hash=str(drips_payload["source_hash"]),
            wave_end_at=wave_end_at,
        )
        audited_key = key
        break

    current_records: list[Mapping[str, Any]] = []
    for raw in candidates:
        candidate = _mapping(raw, code="invalid_drips_candidate")
        entry = entries.get(_candidate_key(candidate))
        if entry is not None and _cache_entry_is_fresh(entry, now=current):
            current_record = dict(entry)
            current_record["current_drips_source_hash"] = drips_payload.get("source_hash")
            current_records.append(current_record)
    qualified = [record for record in current_records if record.get("decision") == "qualified"]
    drips_valid_until = parse_timestamp(drips_payload.get("valid_until"))
    assert drips_valid_until is not None
    output_valid_until = min(
        [drips_valid_until]
        + [
            timestamp
            for timestamp in (
                parse_timestamp(record.get("valid_until")) for record in current_records
            )
            if timestamp is not None
        ]
    )
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id or uuid.uuid4().hex,
        "generated_at": current.isoformat(),
        "valid_until": output_valid_until.isoformat(),
        "drips_run_id": drips_payload.get("run_id"),
        "drips_source_hash": drips_payload.get("source_hash"),
        "drips_candidate_count": len(candidates),
        "github_rate_budget": rate,
        "audit_policy": {
            "max_new_candidates_per_run": 1,
            "public_github_only": True,
            "authenticated_github": github_authenticated,
            "minimum_score": MIN_SCORE,
            "qualified_cache_ttl_seconds": QUALIFIED_CACHE_TTL_SECONDS,
            "rejected_cache_ttl_seconds": REJECTED_CACHE_TTL_SECONDS,
        },
        "newly_audited_candidate_key": audited_key,
        "qualification_count": len(current_records),
        "qualified_count": len(qualified),
        "qualifications": current_records,
        "qualified_candidates": qualified,
        "workflow_contract": {
            "allowed_now": ["read_public_github", "qualify", "cache_receipts"],
            "application_allowed": False,
            "implementation_allowed": False,
            "requires_before_application": [
                "user_oauth_login",
                "user_terms_acceptance",
                "user_completed_kyc",
                "valid_turnstile_challenge",
                "authenticated_quota_remaining",
                "fresh_drips_issue_and_application_revalidation",
                "fresh_github_revalidation",
            ],
            "requires_before_implementation": ["official_maintainer_assignment"],
        },
        "financial_truth": {
            "points_are_usd": False,
            "expected_revenue_usd": None,
            "realized_revenue_usd": 0.0,
        },
    }
    hash_payload = {
        "drips_source_hash": payload["drips_source_hash"],
        "qualifications": current_records,
        "workflow_contract": payload["workflow_contract"],
    }
    payload["source_hash"] = _canonical_hash(hash_payload)
    ordered_entries = sorted(
        entries.items(),
        key=lambda item: str(item[1].get("verified_at") or ""),
        reverse=True,
    )[:MAX_CACHE_ENTRIES]
    cache = {
        "schema_version": SCHEMA_VERSION,
        "updated_at": current.isoformat(),
        "entries": dict(ordered_entries),
    }
    return payload, cache


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--drips", default=str(DEFAULT_DRIPS_PATH))
    parser.add_argument("--drips-manifest", default=str(DEFAULT_DRIPS_MANIFEST_PATH))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH))
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST_PATH))
    parser.add_argument("--cache", default=str(DEFAULT_CACHE_PATH))
    return parser.parse_args()


def main() -> int:
    global GITHUB_TOKEN
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
        GITHUB_TOKEN = resolve_github_token()
        drips_payload = load_json(Path(args.drips), code="invalid_drips_output")
        drips_manifest = load_json(
            Path(args.drips_manifest),
            code="invalid_drips_manifest",
        )
        cache = _load_cache(cache_path)
        payload, updated_cache = qualify_market(
            drips_payload,
            drips_manifest,
            cache,
            fetch_json=http_get_json,
            run_id=run_id,
            github_authenticated=bool(GITHUB_TOKEN),
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
                    "audited_one": payload["newly_audited_candidate_key"] is not None,
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
                "realized_revenue_usd": 0.0,
            },
        )
        print(json.dumps({"status": "failed", "error_code": code}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

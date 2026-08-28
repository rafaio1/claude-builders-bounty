#!/usr/bin/env python3
"""Build a bounded, fail-closed Drips Wave opportunity queue.

The public Drips API is used only for discovery and official-state
revalidation.  This tool never authenticates, applies for work, starts an
implementation, or treats Points / a Wave reward pool as realized revenue.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import time
import uuid
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

API_ROOT = "https://wave-api.drips.network"
APP_ROOT = "https://www.drips.network"
PROGRAM_ID = "fdc01c95-806f-4b6a-998b-a6ed37e0d81b"
PROGRAM_SLUG = "stellar"
SCHEMA_VERSION = "1.0"
DEFAULT_OUTPUT_PATH = Path("/Agentic/state/drips_wave_candidates.json")
DEFAULT_MANIFEST_PATH = Path("/Agentic/state/drips_wave_candidates_success.json")
DEFAULT_MAX_PAGES = 5
DEFAULT_TOP_CANDIDATES = 10
MAX_PAGES = 10
MAX_TOP_CANDIDATES = 20
PAGE_LIMIT = 50
DETAIL_REVALIDATION_LIMIT = 20
MAX_HTTP_ATTEMPTS = 4
HTTP_TIMEOUT_SECONDS = 20
MAX_RESPONSE_BYTES = 20 * 1024 * 1024
MAX_RETRY_AFTER_SECONDS = 10.0
SNAPSHOT_TTL_SECONDS = 720
MAX_WINDOW_COLLECTION_ATTEMPTS = 2
USER_AGENT = "Agentic-Drips-Scanner/1.0"
REPO_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
DRIFT_ERROR_CODES = frozenset(
    {
        "duplicate_issue_overlap",
        "issue_identity_conflict",
        "pagination_shape_drift",
        "pagination_total_drift",
    }
)


class ScannerError(RuntimeError):
    """A public-market snapshot could not be proven safe to consume."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


JsonFetcher = Callable[[str], Any]


def iso_now() -> str:
    return datetime.now(UTC).isoformat()


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


def _official_url(path: str, params: Mapping[str, Any] | None = None) -> str:
    if not path.startswith("/"):
        raise ValueError("official API path must be absolute")
    url = f"{API_ROOT}{path}"
    if params:
        url = f"{url}?{urlencode(params)}"
    return url


def _retryable_http_status(status: int) -> bool:
    return status == 429 or 500 <= status <= 599


def _retry_after_seconds(headers: Any) -> float | None:
    if headers is None or not hasattr(headers, "get"):
        return None
    raw = headers.get("Retry-After")
    if raw is None:
        return None
    value = str(raw).strip()
    try:
        seconds = float(value)
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(value)
        except (TypeError, ValueError, OverflowError):
            return None
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=UTC)
        seconds = (retry_at.astimezone(UTC) - datetime.now(UTC)).total_seconds()
    return min(MAX_RETRY_AFTER_SECONDS, max(0.0, seconds))


def _validate_response(response: Any, requested_url: str) -> None:
    if not hasattr(response, "geturl"):
        raise ScannerError("invalid_http_response", "official API response has no final URL")
    expected = urlparse(requested_url)
    final = urlparse(str(response.geturl()))
    if (
        final.scheme != "https"
        or final.hostname != "wave-api.drips.network"
        or final.path != expected.path
        or final.query != expected.query
    ):
        raise ScannerError("untrusted_redirect", "official API redirected unexpectedly")
    headers = getattr(response, "headers", None)
    content_type = headers.get("Content-Type") if hasattr(headers, "get") else None
    if str(content_type or "").split(";", 1)[0].strip().casefold() != "application/json":
        raise ScannerError("invalid_content_type", "official API did not return JSON")


def http_get_json(url: str) -> Any:
    """Read one official JSON endpoint with bounded retry and response size."""
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "wave-api.drips.network":
        raise ScannerError("untrusted_api_host", "refusing a non-Drips API URL")
    last_code = "official_api_unavailable"
    for attempt in range(MAX_HTTP_ATTEMPTS):
        retry_delay: float | None = None
        try:
            request = Request(
                url,
                headers={"Accept": "application/json", "User-Agent": USER_AGENT},
                method="GET",
            )
            with urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
                _validate_response(response, url)
                status = int(getattr(response, "status", response.getcode()))
                if status != 200:
                    raise ScannerError(
                        "unexpected_http_status",
                        f"official API returned HTTP {status}",
                    )
                raw = response.read(MAX_RESPONSE_BYTES + 1)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise ScannerError("response_too_large", "official API response exceeded limit")
            try:
                return json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                last_code = "invalid_json"
                if attempt + 1 >= MAX_HTTP_ATTEMPTS:
                    raise ScannerError(last_code, "official API returned invalid JSON") from error
        except HTTPError as error:
            last_code = f"http_{error.code}"
            if not _retryable_http_status(error.code):
                raise ScannerError(last_code, "official API request was rejected") from error
            retry_delay = _retry_after_seconds(getattr(error, "headers", None))
        except ScannerError:
            raise
        except (TimeoutError, URLError, OSError) as error:
            last_code = "official_api_unavailable"
            if attempt + 1 >= MAX_HTTP_ATTEMPTS:
                raise ScannerError(last_code, "official API could not be reached") from error
        if attempt + 1 < MAX_HTTP_ATTEMPTS:
            time.sleep(retry_delay if retry_delay is not None else 2**attempt)
    raise ScannerError(last_code, "official API retry budget exhausted")


def _mapping(payload: Any, *, code: str) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping):
        raise ScannerError(code, "official API object schema changed")
    return payload


def _positive_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value > 0 else None


def _nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value >= 0 else None


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def select_active_wave(
    waves_payload: Any,
    *,
    now: datetime | None = None,
    program_id: str = PROGRAM_ID,
) -> Mapping[str, Any]:
    payload = _mapping(waves_payload, code="invalid_waves_schema")
    rows = payload.get("data")
    pagination = payload.get("pagination")
    if not isinstance(rows, list) or not isinstance(pagination, Mapping):
        raise ScannerError("invalid_waves_schema", "waves data must be a list")
    total = _nonnegative_int(pagination.get("total"))
    if (
        total is None
        or total != len(rows)
        or pagination.get("hasNextPage") is not False
    ):
        raise ScannerError("invalid_waves_pagination", "active Waves list is incomplete")
    current = (now or datetime.now(UTC)).astimezone(UTC)
    active: list[Mapping[str, Any]] = []
    for raw in rows:
        if not isinstance(raw, Mapping):
            continue
        start = parse_timestamp(raw.get("startDate"))
        end = parse_timestamp(raw.get("endDate"))
        if (
            raw.get("waveProgramId") == program_id
            and str(raw.get("status") or "").casefold() == "active"
            and start is not None
            and end is not None
            and start <= current < end
        ):
            active.append(raw)
    if len(active) != 1:
        raise ScannerError(
            "active_wave_ambiguous",
            "expected exactly one official active Wave",
        )
    wave = active[0]
    if _positive_int(wave.get("waveNumber")) is None:
        raise ScannerError("invalid_active_wave", "active Wave number is invalid")
    try:
        budget = Decimal(str(wave.get("budgetUSD")))
    except (InvalidOperation, ValueError) as error:
        raise ScannerError("invalid_active_wave", "active Wave budget is invalid") from error
    if not budget.is_finite() or budget <= 0 or budget > Decimal(1000000000):
        raise ScannerError("invalid_active_wave", "active Wave budget must be positive")
    return wave


def validate_program(program_payload: Any) -> Mapping[str, Any]:
    program = _mapping(program_payload, code="invalid_program_schema")
    if program.get("id") != PROGRAM_ID or program.get("slug") != PROGRAM_SLUG:
        raise ScannerError("unexpected_program", "official program identity changed")
    if program.get("paused") is not False:
        raise ScannerError("program_paused", "official program is paused or ambiguous")
    return program


def _issue_identity_key(issue: Mapping[str, Any]) -> str | None:
    repo = issue.get("repo")
    number = _positive_int(issue.get("gitHubIssueNumber"))
    if not isinstance(repo, Mapping) or number is None:
        return None
    repo_name = str(repo.get("gitHubRepoFullName") or "").strip().casefold()
    if not REPO_PATTERN.fullmatch(repo_name):
        return None
    return f"{repo_name}#{number}"


def _fetch_issue_window_once(
    fetch_json: JsonFetcher,
    *,
    max_pages: int,
) -> tuple[list[Mapping[str, Any]], dict[str, Any]]:
    if not 1 <= max_pages <= MAX_PAGES:
        raise ValueError(f"max_pages must be between 1 and {MAX_PAGES}")
    records: dict[str, Mapping[str, Any]] = {}
    identities: dict[str, str] = {}
    totals: list[int] = []
    reported_page_counts: list[int] = []
    pages_collected = 0
    total_pages = 0
    has_next_page = False
    for page in range(1, max_pages + 1):
        url = _official_url(
            "/api/issues",
            {
                "limit": PAGE_LIMIT,
                "page": page,
                "waveProgramId": PROGRAM_ID,
                "state": "open",
                "sortBy": "updatedAt",
                "sortOrder": "desc",
                "applicantAssigned": "false",
                "hasApplications": "false",
                "hasPr": "false",
                "isInWaveProgram": "true",
                "eligibleForWaveProgram": "true",
            },
        )
        payload = _mapping(fetch_json(url), code="invalid_issues_schema")
        rows = payload.get("data")
        pagination = payload.get("pagination")
        if not isinstance(rows, list) or not isinstance(pagination, Mapping):
            raise ScannerError("invalid_issues_schema", "issues page schema changed")
        if _positive_int(pagination.get("page")) != page:
            raise ScannerError("pagination_mismatch", "official API returned the wrong page")
        if _positive_int(pagination.get("limit")) != PAGE_LIMIT:
            raise ScannerError("pagination_mismatch", "official API changed the page limit")
        total = _nonnegative_int(pagination.get("total"))
        reported_total_pages = _nonnegative_int(pagination.get("totalPages"))
        if total is None or reported_total_pages is None:
            raise ScannerError("invalid_pagination", "official pagination is incomplete")
        raw_has_next_page = pagination.get("hasNextPage")
        if not isinstance(raw_has_next_page, bool):
            raise ScannerError("invalid_pagination", "hasNextPage must be boolean")
        expected_total_pages = (total + PAGE_LIMIT - 1) // PAGE_LIMIT
        if reported_total_pages != expected_total_pages:
            raise ScannerError(
                "pagination_shape_drift",
                "official page count does not match total and limit",
            )
        if raw_has_next_page != (page < reported_total_pages):
            raise ScannerError(
                "pagination_shape_drift",
                "official next-page flag is inconsistent",
            )
        if totals and total != totals[0]:
            raise ScannerError("pagination_total_drift", "issue total changed within scan")
        if reported_page_counts and reported_total_pages != reported_page_counts[0]:
            raise ScannerError(
                "pagination_total_drift",
                "issue page count changed within scan",
            )
        if raw_has_next_page and len(rows) != PAGE_LIMIT:
            raise ScannerError(
                "pagination_shape_drift",
                "official pagination cannot advance safely",
            )
        totals.append(total)
        reported_page_counts.append(reported_total_pages)
        total_pages = reported_total_pages
        has_next_page = raw_has_next_page
        pages_collected += 1
        for raw in rows:
            if not isinstance(raw, Mapping):
                raise ScannerError("invalid_issue_record", "issue row is not an object")
            issue_id = str(raw.get("id") or "")
            if not issue_id:
                raise ScannerError("invalid_issue_record", "issue row has no official id")
            if issue_id in records:
                raise ScannerError(
                    "duplicate_issue_overlap",
                    "duplicate issue appeared within one paginated scan",
                )
            identity = _issue_identity_key(raw)
            if identity is not None:
                previous_id = identities.get(identity)
                if previous_id is not None and previous_id != issue_id:
                    raise ScannerError(
                        "issue_identity_conflict",
                        "one GitHub issue maps to multiple official ids",
                    )
                identities[identity] = issue_id
            records[issue_id] = raw
        if not has_next_page:
            break
    ordered_records = [records[key] for key in sorted(records)]
    return ordered_records, {
        "pages_requested": max_pages,
        "pages_collected": pages_collected,
        "page_limit": PAGE_LIMIT,
        "records_collected": len(records),
        "total_reported_first": totals[0] if totals else 0,
        "total_reported_last": totals[-1] if totals else 0,
        "total_drift": (max(totals) - min(totals)) if totals else 0,
        "total_pages_reported": total_pages,
        "has_next_page_after_window": has_next_page,
        "scan_window_complete": True,
        "global_market_complete": not has_next_page,
        "window_source_hash": _canonical_hash(ordered_records),
    }


def fetch_issue_window(
    fetch_json: JsonFetcher,
    *,
    max_pages: int,
) -> tuple[list[Mapping[str, Any]], dict[str, Any]]:
    """Collect one consistent bounded window, retrying drift only once."""
    for attempt in range(1, MAX_WINDOW_COLLECTION_ATTEMPTS + 1):
        try:
            records, metadata = _fetch_issue_window_once(fetch_json, max_pages=max_pages)
            metadata["window_collection_attempts"] = attempt
            metadata["drift_retry_used"] = attempt > 1
            return records, metadata
        except ScannerError as error:
            if error.code not in DRIFT_ERROR_CODES or attempt >= MAX_WINDOW_COLLECTION_ATTEMPTS:
                raise
    raise AssertionError("bounded issue-window retry loop did not terminate")


def candidate_gate_reasons(
    issue: Mapping[str, Any],
    *,
    program_id: str = PROGRAM_ID,
) -> list[str]:
    reasons: list[str] = []
    issue_id = str(issue.get("id") or "")
    try:
        uuid.UUID(issue_id)
    except (ValueError, AttributeError):
        reasons.append("invalid_drips_issue_id")
    if issue.get("waveProgramId") != program_id:
        reasons.append("wrong_wave_program")
    if str(issue.get("state") or "").casefold() != "open":
        reasons.append("issue_not_open")
    if issue.get("gitHubClosedAt") is not None:
        reasons.append("github_issue_closed")
    if issue.get("assignedApplicant") is not None:
        reasons.append("already_assigned")
    pending = _nonnegative_int(issue.get("pendingApplicationsCount"))
    if pending is None:
        reasons.append("pending_applications_unknown")
    elif pending != 0:
        reasons.append("active_competition")
    assignees = issue.get("assignees")
    if not isinstance(assignees, list):
        reasons.append("github_assignees_unknown")
    elif assignees:
        reasons.append("github_issue_assigned")
    if issue.get("completedAt") is not None:
        reasons.append("issue_completed")
    if issue.get("resolvedInWave") is not None:
        reasons.append("issue_already_resolved")
    if issue.get("prLink") is not None:
        reasons.append("pull_request_already_linked")
    if _positive_int(issue.get("points")) is None:
        reasons.append("points_missing")
    number = _positive_int(issue.get("gitHubIssueNumber"))
    if number is None:
        reasons.append("invalid_github_issue_number")
    if not str(issue.get("title") or "").strip():
        reasons.append("missing_title")
    repo = issue.get("repo")
    if not isinstance(repo, Mapping):
        reasons.append("repo_missing")
    else:
        repo_name = str(repo.get("gitHubRepoFullName") or "")
        repo_url = str(repo.get("gitHubRepoUrl") or "")
        parsed = urlparse(repo_url)
        path = parsed.path.strip("/")
        if not REPO_PATTERN.fullmatch(repo_name):
            reasons.append("invalid_repo_name")
        if (
            parsed.scheme != "https"
            or parsed.hostname not in {"github.com", "www.github.com"}
            or path.casefold() != repo_name.casefold()
        ):
            reasons.append("repo_url_mismatch")
    return sorted(set(reasons))


def _effort_weight(complexity: Any) -> float:
    value = str(complexity or "").casefold()
    return {
        "trivial": 1.0,
        "small": 1.0,
        "medium": 2.0,
        "large": 4.0,
        "high": 4.0,
    }.get(value, 8.0)


def ranking_components(
    issue: Mapping[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, float]:
    points = float(_positive_int(issue.get("points")) or 0)
    weight = _effort_weight(issue.get("complexity"))
    updated = parse_timestamp(issue.get("gitHubUpdatedAt"))
    current = (now or datetime.now(UTC)).astimezone(UTC)
    age_hours = 24.0 * 365.0 if updated is None else max(
        0.0,
        (current - updated).total_seconds() / 3600.0,
    )
    body = str(issue.get("body") or "").casefold()
    clarity_bonus = 100.0 if "acceptance criteria" in body else 0.0
    efficiency = points / weight if weight else 0.0
    score = efficiency * 1_000.0 + clarity_bonus - min(age_hours, 10_000.0)
    return {
        "points": points,
        "effort_weight": weight,
        "points_per_effort_unit": round(efficiency, 4),
        "clarity_bonus": clarity_bonus,
        "freshness_penalty_hours": round(min(age_hours, 10_000.0), 4),
        "score": round(score, 4),
    }


def rank_issues(
    issues: list[Mapping[str, Any]],
    *,
    now: datetime | None = None,
) -> list[Mapping[str, Any]]:
    eligible = [issue for issue in issues if not candidate_gate_reasons(issue)]
    return sorted(
        eligible,
        key=lambda issue: (
            -ranking_components(issue, now=now)["score"],
            str((issue.get("repo") or {}).get("gitHubRepoFullName") or "").casefold(),
            int(issue.get("gitHubIssueNumber") or 0),
            str(issue.get("id") or ""),
        ),
    )


def _candidate_record(
    issue: Mapping[str, Any],
    *,
    wave: Mapping[str, Any],
    now: datetime,
) -> dict[str, Any]:
    issue_id = str(issue["id"])
    repo = str(_mapping(issue["repo"], code="invalid_candidate_repo")["gitHubRepoFullName"])
    number = int(issue["gitHubIssueNumber"])
    return {
        "id": f"drips:{issue_id}",
        "platform": "drips_wave",
        "program_id": PROGRAM_ID,
        "wave_id": str(wave["id"]),
        "wave_number": int(wave["waveNumber"]),
        "drips_issue_id": issue_id,
        "repo": repo,
        "issue_number": number,
        "title": str(issue["title"]),
        "source_url": f"https://github.com/{repo}/issues/{number}",
        "official_evidence_url": _official_url(f"/api/issues/{issue_id}"),
        "application_surface_url": f"{APP_ROOT}/wave/{PROGRAM_SLUG}/issues",
        "status": "application_candidate",
        "points": int(issue["points"]),
        "complexity": issue.get("complexity"),
        "pending_applications_count": 0,
        "assigned_applicant": None,
        "github_assignees": [],
        "github_created_at": issue.get("gitHubCreatedAt"),
        "github_updated_at": issue.get("gitHubUpdatedAt"),
        "ranking": ranking_components(issue, now=now),
        "reward": {
            "model": "pro_rata_points_share",
            "wave_pool_budget_usd": str(wave["budgetUSD"]),
            "wave_pool_is_not_issue_bounty": True,
            "issue_fixed_reward_usd": None,
            "points_value_usd": None,
            "expected_revenue_usd": None,
            "realized_revenue_usd": 0.0,
            "payment_status": "not_earned",
        },
        "gates": {
            "oauth_login": "unverified",
            "terms_acceptance": "unverified",
            "kyc": "unverified",
            "turnstile": "unverified",
            "application_quota": "unverified",
            "account_restriction_status": "unverified",
            "issue_ownership": "unverified",
            "github_live_issue": "unverified",
            "repository_health": "unverified",
            "scope_quality_review": "unverified",
            "human_action_required": True,
            "automation_eligible": False,
            "application_allowed": False,
            "application_receipt": "missing",
            "maintainer_assignment": "missing",
            "implementation_allowed": False,
            "fresh_revalidation_required": True,
        },
        "next_action": (
            "complete_personal_login_terms_and_kyc_then_run_live_github_quality_"
            "quota_and_application_revalidation"
        ),
    }


def _source_hash(payload: Mapping[str, Any]) -> str:
    canonical = {
        "program": payload["program"],
        "active_wave": payload["active_wave"],
        "window_source_hash": payload["scan"]["window_source_hash"],
        "detail_source_hash": payload["scan"]["detail_source_hash"],
        "candidate_ids": [candidate["id"] for candidate in payload["candidates"]],
        "workflow_contract": payload["workflow_contract"],
    }
    return _canonical_hash(canonical)


def scan_market(
    fetch_json: JsonFetcher = http_get_json,
    *,
    now: datetime | None = None,
    max_pages: int = DEFAULT_MAX_PAGES,
    top_candidates: int = DEFAULT_TOP_CANDIDATES,
    run_id: str | None = None,
) -> dict[str, Any]:
    if not 1 <= top_candidates <= MAX_TOP_CANDIDATES:
        raise ValueError(f"top_candidates must be between 1 and {MAX_TOP_CANDIDATES}")
    current = (now or datetime.now(UTC)).astimezone(UTC)
    program = validate_program(
        fetch_json(_official_url(f"/api/wave-programs/{PROGRAM_ID}"))
    )
    wave = select_active_wave(
        fetch_json(
            _official_url(
                f"/api/wave-programs/{PROGRAM_ID}/waves",
                {"limit": 100, "status": "active"},
            )
        ),
        now=current,
    )
    issues, scan = fetch_issue_window(fetch_json, max_pages=max_pages)
    ranked = rank_issues(issues, now=current)
    detail_limit = min(len(ranked), max(top_candidates, DETAIL_REVALIDATION_LIMIT))
    revalidated: list[Mapping[str, Any]] = []
    detail_snapshots: list[Mapping[str, Any]] = []
    detail_became_ineligible = 0
    detail_fetch_errors = 0
    for issue in ranked[:detail_limit]:
        issue_id = str(issue.get("id") or "")
        try:
            detail = _mapping(
                fetch_json(_official_url(f"/api/issues/{issue_id}")),
                code="invalid_issue_detail_schema",
            )
        except ScannerError as error:
            if error.code == "http_404":
                detail_became_ineligible += 1
            else:
                detail_fetch_errors += 1
            continue
        detail_snapshots.append(detail)
        if str(detail.get("id") or "") != issue_id or candidate_gate_reasons(detail):
            detail_became_ineligible += 1
            continue
        revalidated.append(detail)
    if detail_limit and detail_fetch_errors == detail_limit:
        raise ScannerError(
            "detail_revalidation_unavailable",
            "no candidate detail could be revalidated",
        )
    revalidated = rank_issues(revalidated, now=current)[:top_candidates]
    candidates = [_candidate_record(issue, wave=wave, now=current) for issue in revalidated]
    scan.update(
        {
            "eligible_before_detail_revalidation": len(ranked),
            "details_requested": detail_limit,
            "details_became_ineligible": detail_became_ineligible,
            "detail_fetch_errors": detail_fetch_errors,
            "detail_source_hash": _canonical_hash(
                sorted(detail_snapshots, key=lambda row: str(row.get("id") or ""))
            ),
            "details_changed_or_unavailable": (
                detail_became_ineligible + detail_fetch_errors
            ),
            "candidates_after_detail_revalidation": len(candidates),
            "drips_detail_evidence_complete": detail_fetch_errors == 0,
            "github_live_evidence_complete": False,
            "candidate_evidence_complete": False,
        }
    )
    wave_end = parse_timestamp(wave.get("endDate"))
    if wave_end is None:
        raise ScannerError("invalid_active_wave", "active Wave end time is invalid")
    valid_until = min(current + timedelta(seconds=SNAPSHOT_TTL_SECONDS), wave_end)
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id or uuid.uuid4().hex,
        "generated_at": current.isoformat(),
        "valid_until": valid_until.isoformat(),
        "snapshot_ttl_seconds": SNAPSHOT_TTL_SECONDS,
        "program": {
            "id": PROGRAM_ID,
            "slug": PROGRAM_SLUG,
            "name": str(program.get("name") or ""),
            "paused": False,
            "official_url": f"{APP_ROOT}/wave/{PROGRAM_SLUG}",
            "official_api_url": _official_url(f"/api/wave-programs/{PROGRAM_ID}"),
        },
        "active_wave": {
            "id": str(wave["id"]),
            "number": int(wave["waveNumber"]),
            "start_at": str(wave["startDate"]),
            "end_at": str(wave["endDate"]),
            "reward_pool_budget_usd": str(wave["budgetUSD"]),
            "reward_pool_is_not_issue_bounty": True,
            "status": "active",
        },
        "scan": scan,
        "financial_truth": {
            "realized_revenue_usd": 0.0,
            "points_are_currency": False,
            "points_have_fixed_usd_value": False,
            "individual_issue_reward_guaranteed": False,
            "reward_allocation_model": "pro_rata_after_confirmed_contribution",
        },
        "workflow_contract": {
            "current_stage": "awaiting_personal_identity_gate",
            "allowed_now": ["discover", "rank", "revalidate_official_state"],
            "application_requires": [
                "user_terms_acceptance",
                "user_oauth_login",
                "user_completed_kyc",
                "valid_turnstile_challenge",
                "account_not_restricted",
                "issue_not_owned_by_user",
                "application_quota_remaining",
                "organization_assignment_quota_remaining",
                "live_github_issue_and_repository_quality_review",
                "fresh_issue_revalidation",
                "fresh_zero_application_revalidation",
            ],
            "implementation_requires": ["official_maintainer_assignment"],
            "settlement_requires": ["canonical_wallet_or_provider_transaction"],
            "forbidden_now": [
                "submit_application",
                "start_implementation",
                "book_points_or_pool_as_revenue",
            ],
        },
        "candidate_count": len(candidates),
        "candidates": candidates,
    }
    payload["source_hash"] = _source_hash(payload)
    return payload


def atomic_json_write(path: Path, payload: Mapping[str, Any]) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pages", type=int, default=DEFAULT_MAX_PAGES)
    parser.add_argument("--top", type=int, default=DEFAULT_TOP_CANDIDATES)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH))
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST_PATH))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not 1 <= args.pages <= MAX_PAGES:
        raise SystemExit(f"--pages must be between 1 and {MAX_PAGES}")
    if not 1 <= args.top <= MAX_TOP_CANDIDATES:
        raise SystemExit(f"--top must be between 1 and {MAX_TOP_CANDIDATES}")
    run_id = uuid.uuid4().hex
    manifest_path = Path(args.manifest)
    output_path = Path(args.output)
    atomic_json_write(
        manifest_path,
        {
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "status": "collecting",
            "started_at": iso_now(),
            "candidate_output": str(output_path.resolve()),
        },
    )
    try:
        payload = scan_market(
            max_pages=args.pages,
            top_candidates=args.top,
            run_id=run_id,
        )
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
                "snapshot_ttl_seconds": payload["snapshot_ttl_seconds"],
                "candidate_output": str(output_path.resolve()),
                "candidate_count": payload["candidate_count"],
                "drips_detail_evidence_complete": payload["scan"][
                    "drips_detail_evidence_complete"
                ],
                "github_live_evidence_complete": False,
                "candidate_evidence_complete": False,
                "global_market_complete": payload["scan"]["global_market_complete"],
                "realized_revenue_usd": 0.0,
            },
        )
        print(
            json.dumps(
                {
                    "status": "ok",
                    "run_id": run_id,
                    "wave_number": payload["active_wave"]["number"],
                    "candidates": payload["candidate_count"],
                    "global_market_complete": payload["scan"]["global_market_complete"],
                    "realized_revenue_usd": 0.0,
                },
                sort_keys=True,
            )
        )
        return 0
    except (ScannerError, OSError, ValueError) as error:
        code = error.code if isinstance(error, ScannerError) else type(error).__name__
        atomic_json_write(
            manifest_path,
            {
                "schema_version": SCHEMA_VERSION,
                "run_id": run_id,
                "status": "failed",
                "failed_at": iso_now(),
                "candidate_output": str(output_path.resolve()),
                "error_code": code,
                "realized_revenue_usd": 0.0,
            },
        )
        print(json.dumps({"status": "failed", "error_code": code}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

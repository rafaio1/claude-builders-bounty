"""Safety and state-contract tests for the public Drips Wave scanner."""

from __future__ import annotations

import email.message
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse

import pytest

sys.path.insert(0, "/Agentic/tools")
import drips_wave_scanner as scanner

NOW = datetime(2026, 8, 28, 15, 0, tzinfo=UTC)
WAVE_ID = "22222222-2222-4222-8222-222222222222"


def program() -> dict:
    return {
        "id": scanner.PROGRAM_ID,
        "slug": scanner.PROGRAM_SLUG,
        "name": "Stellar",
        "paused": False,
    }


def waves() -> dict:
    return {
        "data": [
            {
                "id": WAVE_ID,
                "waveProgramId": scanner.PROGRAM_ID,
                "waveNumber": 8,
                "startDate": "2026-08-24T12:00:00Z",
                "endDate": "2026-08-31T12:00:00Z",
                "budgetUSD": "75000.00",
                "status": "active",
            }
        ],
        "pagination": {
            "page": 1,
            "limit": 100,
            "total": 1,
            "totalPages": 1,
            "hasNextPage": False,
            "hasPreviousPage": False,
        },
    }


def issue(
    *,
    issue_id: str = "11111111-1111-4111-8111-111111111111",
    repo: str = "stellar/example",
    number: int = 42,
    points: int = 200,
    complexity: str | None = "large",
    pending: int = 0,
) -> dict:
    return {
        "id": issue_id,
        "waveProgramId": scanner.PROGRAM_ID,
        "gitHubIssueNumber": number,
        "title": "Add a typed client with acceptance criteria",
        "body": "## Acceptance Criteria\n- [ ] tests pass",
        "state": "open",
        "gitHubClosedAt": None,
        "pendingApplicationsCount": pending,
        "assignedApplicant": None,
        "assignees": [],
        "completedAt": None,
        "resolvedInWave": None,
        "prLink": None,
        "points": points,
        "complexity": complexity,
        "gitHubCreatedAt": "2026-08-28T12:00:00Z",
        "gitHubUpdatedAt": "2026-08-28T14:00:00Z",
        "repo": {
            "gitHubRepoFullName": repo,
            "gitHubRepoUrl": f"https://github.com/{repo}",
        },
    }


def page(
    rows: list[dict],
    *,
    page_number: int = 1,
    has_next: bool = False,
    total: int | None = None,
    total_pages: int | None = None,
) -> dict:
    return {
        "data": rows,
        "pagination": {
            "page": page_number,
            "limit": scanner.PAGE_LIMIT,
            "total": len(rows) if total is None else total,
            "totalPages": (
                (page_number + 1 if has_next else page_number)
                if total_pages is None
                else total_pages
            ),
            "hasNextPage": has_next,
            "hasPreviousPage": page_number > 1,
        },
    }


def fake_fetcher(rows: list[dict], *, detail_overrides: dict[str, dict] | None = None):
    details = {row["id"]: dict(row) for row in rows}
    details.update(detail_overrides or {})

    def fetch(url: str):
        parsed = urlparse(url)
        if parsed.path == f"/api/wave-programs/{scanner.PROGRAM_ID}":
            return program()
        if parsed.path == f"/api/wave-programs/{scanner.PROGRAM_ID}/waves":
            return waves()
        if parsed.path == "/api/issues":
            page_number = int(parse_qs(parsed.query)["page"][0])
            return page(rows if page_number == 1 else [], page_number=page_number)
        if parsed.path.startswith("/api/issues/"):
            return details[parsed.path.rsplit("/", 1)[1]]
        raise AssertionError(url)

    return fetch


def test_select_active_wave_requires_current_official_window():
    selected = scanner.select_active_wave(waves(), now=NOW)
    assert selected["id"] == WAVE_ID
    with pytest.raises(scanner.ScannerError, match="exactly one"):
        scanner.select_active_wave(waves(), now=datetime(2026, 9, 1, tzinfo=UTC))


def test_active_wave_rejects_nonfinite_budget_and_incomplete_listing():
    invalid_budget = waves()
    invalid_budget["data"][0]["budgetUSD"] = "NaN"
    with pytest.raises(scanner.ScannerError) as error:
        scanner.select_active_wave(invalid_budget, now=NOW)
    assert error.value.code == "invalid_active_wave"

    incomplete = waves()
    incomplete["pagination"]["hasNextPage"] = True
    with pytest.raises(scanner.ScannerError) as error:
        scanner.select_active_wave(incomplete, now=NOW)
    assert error.value.code == "invalid_waves_pagination"


def test_program_must_be_exact_and_unpaused():
    assert scanner.validate_program(program())["name"] == "Stellar"
    paused = program()
    paused["paused"] = True
    with pytest.raises(scanner.ScannerError) as error:
        scanner.validate_program(paused)
    assert error.value.code == "program_paused"


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ({"pendingApplicationsCount": 1}, "active_competition"),
        ({"assignedApplicant": {"gitHubUsername": "other"}}, "already_assigned"),
        ({"assignees": [{"login": "other"}]}, "github_issue_assigned"),
        ({"state": "closed"}, "issue_not_open"),
        ({"gitHubClosedAt": "2026-08-28T14:00:00Z"}, "github_issue_closed"),
        ({"completedAt": "2026-08-28T14:00:00Z"}, "issue_completed"),
        ({"resolvedInWave": WAVE_ID}, "issue_already_resolved"),
        ({"prLink": "https://github.com/stellar/example/pull/1"}, "pull_request_already_linked"),
        ({"points": 0}, "points_missing"),
        ({"waveProgramId": "other"}, "wrong_wave_program"),
    ],
)
def test_candidate_gate_rejects_nonexclusive_or_terminal_work(mutation, reason):
    row = issue()
    row.update(mutation)
    assert reason in scanner.candidate_gate_reasons(row)


def test_candidate_gate_requires_matching_official_github_repo_url():
    row = issue()
    row["repo"] = {
        "gitHubRepoFullName": "stellar/example",
        "gitHubRepoUrl": "https://evil.example/stellar/example",
    }
    assert "repo_url_mismatch" in scanner.candidate_gate_reasons(row)


def test_numeric_schema_is_strict_and_rejects_numeric_strings():
    row = issue()
    row["points"] = "200"
    row["pendingApplicationsCount"] = "0"
    reasons = scanner.candidate_gate_reasons(row)
    assert "points_missing" in reasons
    assert "pending_applications_unknown" in reasons


def test_ranking_is_deterministic_and_never_a_usd_conversion():
    small = issue(
        issue_id="33333333-3333-4333-8333-333333333333",
        number=43,
        points=100,
        complexity="small",
    )
    large = issue(points=200, complexity="large")
    ranked = scanner.rank_issues([large, small], now=NOW)
    assert ranked[0]["id"] == small["id"]
    components = scanner.ranking_components(small, now=NOW)
    assert components["points_per_effort_unit"] == 100.0
    assert "usd" not in json.dumps(components).lower()


def test_detail_revalidation_drops_candidate_that_gained_competition():
    row = issue()
    changed = dict(row)
    changed["pendingApplicationsCount"] = 1
    payload = scanner.scan_market(
        fake_fetcher([row], detail_overrides={row["id"]: changed}),
        now=NOW,
        max_pages=1,
        top_candidates=5,
        run_id="run-a",
    )
    assert payload["candidate_count"] == 0
    assert payload["scan"]["details_changed_or_unavailable"] == 1


def test_candidate_output_is_fail_closed_about_identity_assignment_and_money():
    row = issue()
    payload = scanner.scan_market(
        fake_fetcher([row]),
        now=NOW,
        max_pages=1,
        top_candidates=5,
        run_id="run-b",
    )
    candidate = payload["candidates"][0]
    assert candidate["gates"]["application_allowed"] is False
    assert candidate["gates"]["implementation_allowed"] is False
    assert candidate["gates"]["kyc"] == "unverified"
    assert candidate["gates"]["human_action_required"] is True
    assert candidate["gates"]["automation_eligible"] is False
    assert candidate["gates"]["github_live_issue"] == "unverified"
    assert candidate["gates"]["scope_quality_review"] == "unverified"
    assert candidate["reward"]["issue_fixed_reward_usd"] is None
    assert candidate["reward"]["points_value_usd"] is None
    assert candidate["reward"]["realized_revenue_usd"] == 0.0
    assert payload["financial_truth"]["realized_revenue_usd"] == 0.0
    assert payload["active_wave"]["reward_pool_is_not_issue_bounty"] is True
    assert payload["scan"]["drips_detail_evidence_complete"] is True
    assert payload["scan"]["github_live_evidence_complete"] is False
    assert payload["scan"]["candidate_evidence_complete"] is False
    assert payload["valid_until"] == "2026-08-28T15:12:00+00:00"


def test_scan_is_bounded_and_honest_about_global_completeness(monkeypatch):
    monkeypatch.setattr(scanner, "PAGE_LIMIT", 1)
    row = issue()
    row2 = issue(
        issue_id="44444444-4444-4444-8444-444444444444",
        number=43,
    )

    def fetch(url: str):
        parsed = urlparse(url)
        if parsed.path == f"/api/wave-programs/{scanner.PROGRAM_ID}":
            return program()
        if parsed.path == f"/api/wave-programs/{scanner.PROGRAM_ID}/waves":
            return waves()
        if parsed.path == "/api/issues":
            number = int(parse_qs(parsed.query)["page"][0])
            rows = {1: [row], 2: [row2]}[number]
            return page(rows, page_number=number, has_next=True, total=3, total_pages=3)
        if parsed.path.startswith("/api/issues/"):
            return {row["id"]: row, row2["id"]: row2}[parsed.path.rsplit("/", 1)[1]]
        raise AssertionError(url)

    payload = scanner.scan_market(fetch, now=NOW, max_pages=2, top_candidates=1)
    assert payload["scan"]["pages_collected"] == 2
    assert payload["scan"]["global_market_complete"] is False
    assert payload["scan"]["scan_window_complete"] is True


def test_duplicate_issue_overlap_retries_once_then_fails_closed():
    row = issue()
    calls = []

    def fetch(url: str):
        calls.append(url)
        return page([row, row], total=2, total_pages=1)

    with pytest.raises(scanner.ScannerError) as error:
        scanner.fetch_issue_window(fetch, max_pages=1)
    assert error.value.code == "duplicate_issue_overlap"
    assert len(calls) == scanner.MAX_WINDOW_COLLECTION_ATTEMPTS


def test_pagination_total_drift_recollects_the_whole_window_once(monkeypatch):
    monkeypatch.setattr(scanner, "PAGE_LIMIT", 1)
    row1 = issue()
    row2 = issue(
        issue_id="44444444-4444-4444-8444-444444444444",
        number=43,
    )
    collection_attempt = 0

    def fetch(url: str):
        nonlocal collection_attempt
        number = int(parse_qs(urlparse(url).query)["page"][0])
        if number == 1:
            collection_attempt += 1
            return page([row1], page_number=1, has_next=True, total=2, total_pages=2)
        total = 3 if collection_attempt == 1 else 2
        return page([row2], page_number=2, has_next=False, total=total, total_pages=2)

    rows, metadata = scanner.fetch_issue_window(fetch, max_pages=2)
    assert len(rows) == 2
    assert metadata["window_collection_attempts"] == 2
    assert metadata["drift_retry_used"] is True


def test_all_detail_revalidations_unavailable_abort_scan():
    base = fake_fetcher([issue()])

    def fetch(url: str):
        if urlparse(url).path.startswith("/api/issues/"):
            raise scanner.ScannerError("official_api_unavailable", "offline")
        return base(url)

    with pytest.raises(scanner.ScannerError) as error:
        scanner.scan_market(fetch, now=NOW, max_pages=1, top_candidates=1)
    assert error.value.code == "detail_revalidation_unavailable"


def test_source_hash_ignores_run_identity_but_covers_market_state():
    row = issue()
    first = scanner.scan_market(
        fake_fetcher([row]), now=NOW, max_pages=1, top_candidates=1, run_id="a"
    )
    second = scanner.scan_market(
        fake_fetcher([row]),
        now=NOW.replace(minute=5),
        max_pages=1,
        top_candidates=1,
        run_id="b",
    )
    assert first["source_hash"] == second["source_hash"]
    changed = issue(points=150)
    third = scanner.scan_market(
        fake_fetcher([changed]), now=NOW, max_pages=1, top_candidates=1, run_id="c"
    )
    assert third["source_hash"] != first["source_hash"]


class FakeResponse:
    status = 200

    def __init__(self, payload: dict, *, final_url: str | None = None):
        self.payload = json.dumps(payload).encode()
        self.final_url = final_url or f"{scanner.API_ROOT}/api/test"
        self.headers = {"Content-Type": "application/json; charset=utf-8"}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def getcode(self):
        return self.status

    def geturl(self):
        return self.final_url

    def read(self, _limit: int):
        return self.payload


def test_http_retry_is_bounded(monkeypatch):
    calls = []

    def flaky(_request, timeout):
        calls.append(timeout)
        if len(calls) < scanner.MAX_HTTP_ATTEMPTS:
            raise URLError("temporary")
        return FakeResponse({"ok": True})

    monkeypatch.setattr(scanner, "urlopen", flaky)
    monkeypatch.setattr(scanner.time, "sleep", lambda _seconds: None)
    result = scanner.http_get_json(f"{scanner.API_ROOT}/api/test")
    assert result == {"ok": True}
    assert len(calls) == scanner.MAX_HTTP_ATTEMPTS


def test_http_429_respects_capped_retry_after(monkeypatch):
    calls = []
    sleeps = []

    def throttled(request, timeout):
        calls.append((request, timeout))
        if len(calls) == 1:
            headers = email.message.Message()
            headers["Retry-After"] = "99"
            raise HTTPError(request.full_url, 429, "slow down", headers, None)
        return FakeResponse({"ok": True})

    monkeypatch.setattr(scanner, "urlopen", throttled)
    monkeypatch.setattr(scanner.time, "sleep", sleeps.append)
    assert scanner.http_get_json(f"{scanner.API_ROOT}/api/test") == {"ok": True}
    assert sleeps == [scanner.MAX_RETRY_AFTER_SECONDS]


def test_http_rejects_redirect_to_untrusted_host(monkeypatch):
    monkeypatch.setattr(
        scanner,
        "urlopen",
        lambda _request, timeout: FakeResponse(
            {"ok": True}, final_url="https://evil.example/api/test"
        ),
    )
    with pytest.raises(scanner.ScannerError) as error:
        scanner.http_get_json(f"{scanner.API_ROOT}/api/test")
    assert error.value.code == "untrusted_redirect"


def test_http_nonretryable_status_fails_once(monkeypatch):
    calls = []

    def rejected(request, timeout):
        calls.append((request, timeout))
        raise HTTPError(request.full_url, 404, "not found", None, None)

    monkeypatch.setattr(scanner, "urlopen", rejected)
    with pytest.raises(scanner.ScannerError) as error:
        scanner.http_get_json(f"{scanner.API_ROOT}/api/missing")
    assert error.value.code == "http_404"
    assert len(calls) == 1


def test_http_refuses_nonofficial_host():
    with pytest.raises(scanner.ScannerError) as error:
        scanner.http_get_json("https://example.com/api/issues")
    assert error.value.code == "untrusted_api_host"


def test_atomic_write_is_private_and_complete(tmp_path: Path):
    destination = tmp_path / "state.json"
    scanner.atomic_json_write(destination, {"status": "complete"})
    assert json.loads(destination.read_text()) == {"status": "complete"}
    assert os.stat(destination).st_mode & 0o777 == 0o600


def test_main_writes_matching_output_and_manifest(monkeypatch, tmp_path: Path):
    output = tmp_path / "candidates.json"
    manifest = tmp_path / "manifest.json"
    payload = scanner.scan_market(
        fake_fetcher([issue()]), now=NOW, max_pages=1, top_candidates=1, run_id="old"
    )

    def scan_market(**kwargs):
        result = dict(payload)
        result["run_id"] = kwargs["run_id"]
        return result

    monkeypatch.setattr(
        scanner,
        "parse_args",
        lambda: SimpleNamespace(pages=1, top=1, output=str(output), manifest=str(manifest)),
    )
    monkeypatch.setattr(scanner, "scan_market", scan_market)
    assert scanner.main() == 0
    saved_output = json.loads(output.read_text())
    saved_manifest = json.loads(manifest.read_text())
    assert saved_manifest["status"] == "complete"
    assert saved_manifest["run_id"] == saved_output["run_id"]
    assert saved_manifest["source_hash"] == saved_output["source_hash"]
    assert saved_manifest["realized_revenue_usd"] == 0.0
    assert saved_manifest["drips_detail_evidence_complete"] is True
    assert saved_manifest["candidate_evidence_complete"] is False
    assert saved_manifest["valid_until"] == saved_output["valid_until"]


def test_failure_invalidates_an_old_success_manifest(monkeypatch, tmp_path: Path):
    output = tmp_path / "candidates.json"
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"status": "complete", "run_id": "stale"}))
    monkeypatch.setattr(
        scanner,
        "parse_args",
        lambda: SimpleNamespace(pages=1, top=1, output=str(output), manifest=str(manifest)),
    )

    def fail(**_kwargs):
        raise scanner.ScannerError("official_api_unavailable", "offline")

    monkeypatch.setattr(scanner, "scan_market", fail)
    assert scanner.main() == 2
    saved = json.loads(manifest.read_text())
    assert saved["status"] == "failed"
    assert saved["run_id"] != "stale"
    assert saved["error_code"] == "official_api_unavailable"
    assert not output.exists()


def test_scanner_source_contains_no_write_method_or_submission_code():
    source = Path(scanner.__file__).read_text(encoding="utf-8")
    assert 'method="POST"' not in source
    assert "submit_application" in source  # present only in the forbidden-state contract
    assert "authorization" not in source.casefold()

"""Offline fixtures and opt-in live smoke for the large-bounty scout."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, "/Agentic/scripts")
import agentic_superteam_large_bounty_scout as scout

NOW = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


def listing(
    slug: str,
    amount: Any,
    deadline: str,
    *,
    listing_type: str = "bounty",
    status: str = "OPEN",
    token: str = "USDC",
    agent_access: str = "AGENT_ALLOWED",
) -> dict[str, Any]:
    return {
        "id": f"id-{slug}",
        "slug": slug,
        "title": f"Fixture {slug}",
        "rewardAmount": amount,
        "deadline": deadline,
        "type": listing_type,
        "status": status,
        "token": token,
        "agentAccess": agent_access,
        "sponsor": {
            "name": "Fixture Sponsor",
            "slug": "fixture-sponsor",
            "isVerified": True,
        },
    }


def detail_from_listing(item: dict[str, Any], *, description: str = "") -> dict[str, Any]:
    return {
        **item,
        "compensationType": "fixed",
        "rewards": {"1": item["rewardAmount"]},
        "description": description,
        "requirements": None,
        "eligibility": [],
    }


@pytest.fixture
def offline_list_payload() -> list[dict[str, Any]]:
    return [
        listing("largest-usdg", 10000, "2026-09-25T00:00:00Z", token="USDG"),
        listing("largest", 3000, "2026-09-20T00:00:00Z"),
        listing("same-amount-later", 1500, "2026-09-12T00:00:00Z"),
        listing("same-amount-a", 1500, "2026-09-10T00:00:00Z"),
        listing("same-amount-b", 1500, "2026-09-10T00:00:00Z"),
        listing("wrong-token-suffix", 9000, "2026-09-20T00:00:00Z", token="USDC.e"),
        listing("wrong-token-space", 9000, "2026-09-20T00:00:00Z", token="USDC "),
        listing("wrong-case-status", 9000, "2026-09-20T00:00:00Z", status="open"),
        listing("wrong-type", 9000, "2026-09-20T00:00:00Z", listing_type="project"),
        listing("past", 9000, "2026-08-31T23:59:59Z"),
        listing("string-amount", "9000", "2026-09-20T00:00:00Z"),
        listing("boolean-amount", True, "2026-09-20T00:00:00Z"),
        listing("zero-amount", 0, "2026-09-20T00:00:00Z"),
    ]


def fixture_loader(payload: list[dict[str, Any]], descriptions: dict[str, str] | None = None):
    by_slug = {item["slug"]: item for item in payload}

    def load(slug: str):
        detail = detail_from_listing(
            by_slug[slug], description=(descriptions or {}).get(slug, "")
        )
        raw = json.dumps(detail, sort_keys=True).encode()
        return detail, raw

    return load


def test_offline_fixture_strict_filters_and_top_ordering(offline_list_payload):
    selected, rejection_counts = scout.select_list_candidates(
        offline_list_payload, now=NOW
    )

    assert [item["slug"] for item in selected] == [
        "largest-usdg",
        "largest",
        "same-amount-a",
        "same-amount-b",
        "same-amount-later",
    ]
    assert rejection_counts["LIST_TOKEN_NOT_EXPLICIT"] == 2
    assert rejection_counts["LIST_STATUS_NOT_OPEN"] == 1
    assert rejection_counts["LIST_TYPE_NOT_BOUNTY"] == 1
    assert rejection_counts["LIST_DEADLINE_NOT_FUTURE"] == 1
    assert rejection_counts["LIST_AMOUNT_NOT_NUMERIC_POSITIVE"] == 3


def test_verified_is_separate_from_autonomy_and_never_auto_qualifies(
    offline_list_payload,
):
    raw = json.dumps(offline_list_payload, sort_keys=True).encode()
    state = scout.build_state(
        offline_list_payload,
        raw,
        fixture_loader(offline_list_payload),
        now=NOW,
    )

    assert state["status"] == "ok"
    assert state["summary"]["verified_listing_count"] == 5
    assert state["summary"]["autonomy_qualified_count"] == 0
    assert all(item["verified_listing"] is True for item in state["candidates"])
    assert all(item["autonomy_qualified"] is False for item in state["candidates"])
    assert all(
        "MANUAL_REVIEW_REQUIRED" in item["autonomy_reason_codes"]
        for item in state["candidates"]
    )
    assert all(
        item["reward"]["classification"]
        == "UNREALIZED_UNAUDITED_MAXIMUM_INDIVIDUAL_FACE_VALUE"
        for item in state["candidates"]
    )


def test_pool_total_never_outranks_larger_individual_reward():
    pool = listing("large-pool", 10000, "2026-09-25T00:00:00Z", token="USDG")
    individual = listing("larger-individual", 3000, "2026-09-20T00:00:00Z")
    payload = [pool, individual]
    raw = json.dumps(payload, sort_keys=True).encode()

    def load(slug: str):
        item = pool if slug == "large-pool" else individual
        detail = detail_from_listing(item)
        detail["rewards"] = {"1": 500, "2": 500} if slug == "large-pool" else {"1": 2000, "2": 1000}
        return detail, json.dumps(detail, sort_keys=True).encode()

    state = scout.build_state(payload, raw, load, now=NOW)

    assert [item["slug"] for item in state["candidates"]] == ["larger-individual", "large-pool"]
    assert state["candidates"][0]["reward"]["amount"] == 2000
    assert state["candidates"][0]["reward"]["total_pool_amount"] == 3000
    assert state["candidates"][1]["reward"]["amount"] == 500
    assert state["candidates"][1]["reward"]["total_pool_amount"] == 10000


def test_offline_gate_fixture_classifies_all_requested_gates():
    item = listing("all-gates", 2000, "2026-09-30T00:00:00Z")
    description = """
        Participants must use their own funds and execute a real trade in the casino.
        Publish an X thread and tag @Fixture. Create a video demonstration.
        Submit through the official Typeform. Provide your email address and wallet address.
        Complete KYC verification. Share your own real product experience.
    """
    gates, evidence = scout.classify_gates(
        detail_from_listing(item, description=description)
    )

    assert gates == {name: True for name in scout.GATE_NAMES}
    assert all(evidence[name] for name in scout.GATE_NAMES)


def test_offline_gate_fixture_does_not_infer_kyc_from_explicit_no_kyc():
    item = listing("no-kyc", 100, "2026-09-30T00:00:00Z")
    gates, evidence = scout.classify_gates(
        detail_from_listing(
            item,
            description="This public product has no KYC and does not require KYC verification.",
        )
    )

    assert gates["kyc"] is False
    assert evidence["kyc"] == []


def test_detail_mismatch_fails_closed_without_hiding_candidate():
    item = listing("mismatch", 500, "2026-09-30T00:00:00Z")
    raw = json.dumps([item], sort_keys=True).encode()

    def load(_slug: str):
        detail = detail_from_listing(item)
        detail["token"] = "USD"
        return detail, json.dumps(detail, sort_keys=True).encode()

    state = scout.build_state([item], raw, load, now=NOW)
    candidate = state["candidates"][0]

    assert candidate["verified_listing"] is False
    assert candidate["autonomy_qualified"] is False
    assert "DETAIL_TOKEN_MISMATCH" in candidate["verification_reason_codes"]
    assert "LISTING_NOT_VERIFIED" in candidate["autonomy_reason_codes"]


def test_detail_fetch_failure_marks_whole_run_failed_closed():
    item = listing("network-failure", 500, "2026-09-30T00:00:00Z")
    raw = json.dumps([item], sort_keys=True).encode()

    def load(_slug: str):
        raise scout.ScoutError("SOURCE_FETCH_FAILED")

    state = scout.build_state([item], raw, load, now=NOW)
    candidate = state["candidates"][0]

    assert state["status"] == "failed_closed"
    assert state["summary"]["detail_operational_error_count"] == 1
    assert candidate["verified_listing"] is False
    assert all(value is None for value in candidate["gates"].values())
    assert "GATE_KYC_UNKNOWN" in candidate["autonomy_reason_codes"]


def test_hashes_are_reproducible_for_identical_offline_evidence():
    item = listing("stable", 500, "2026-09-30T00:00:00Z")
    raw = json.dumps([item], sort_keys=True).encode()
    first = scout.build_state([item], raw, fixture_loader([item]), now=NOW)
    second = scout.build_state([item], raw, fixture_loader([item]), now=NOW)

    assert first == second
    assert first["result_sha256"] == second["result_sha256"]
    assert len(first["result_sha256"]) == 64
    assert first["sources"]["list"]["sha256"] == hashlib.sha256(raw).hexdigest()


def test_atomic_output_is_mode_0600(tmp_path: Path):
    output = tmp_path / "state.json"
    scout.atomic_write_json(output, {"ok": True})

    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert json.loads(output.read_text()) == {"ok": True}
    assert not list(tmp_path.glob(".state.json.*.tmp"))


def test_source_url_allowlist_rejects_other_hosts_and_unsafe_slugs():
    scout._validate_public_url(scout.LIST_URL)
    scout._validate_public_url(
        scout.DETAIL_URL_TEMPLATE.format(slug="valid-safe-slug")
    )
    with pytest.raises(scout.ScoutError, match="UNTRUSTED_SOURCE_URL"):
        scout._validate_public_url("https://example.com/api/listings/details/slug")
    with pytest.raises(scout.ScoutError, match="UNTRUSTED_SOURCE_URL"):
        scout._validate_public_url(
            "https://superteam.fun/api/listings/details/../unsafe"
        )


def test_canonical_and_service_mirror_are_identical_when_installed():
    canonical = Path("/Agentic/scripts/agentic_superteam_large_bounty_scout.py")
    mirror = Path("/usr/local/lib/agentic/agentic_superteam_large_bounty_scout.py")
    if not canonical.exists() or not mirror.exists():
        pytest.skip("deployment mirror is not installed")
    assert canonical.read_bytes() == mirror.read_bytes()


@pytest.mark.skipif(
    os.environ.get("SUPERTEAM_LIVE_SMOKE") != "1",
    reason="set SUPERTEAM_LIVE_SMOKE=1 for the public-network smoke",
)
def test_live_public_large_bounty_list_and_top_ordering_without_credentials():
    payload, raw = scout.fetch_public_json(scout.LIST_URL)
    selected, _rejections = scout.select_list_candidates(
        payload, now=datetime.now(UTC)
    )

    assert raw
    assert selected, "the current official list must contain explicit-token open bounties"
    assert all(item["amount_reward"] > 0 for item in selected)
    assert [item["slug"] for item in selected] == [
        item["slug"]
        for item in sorted(
            selected,
            key=lambda item: (
                -item["_amount_decimal"],
                item["_deadline_datetime"],
                item["slug"],
            ),
        )
    ]
    top = selected[0]
    detail, detail_raw = scout.fetch_public_json(
        scout.DETAIL_URL_TEMPLATE.format(slug=top["slug"])
    )
    reasons, _mapping = scout._verify_detail(top, detail, now=datetime.now(UTC))
    assert reasons == []
    assert len(scout.sha256_bytes(raw)) == 64
    assert len(scout.sha256_bytes(detail_raw)) == 64

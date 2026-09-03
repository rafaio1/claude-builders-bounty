#!/usr/bin/env python3
"""Deterministic, fail-closed priority queues for autonomous bounty work.

The module aggregates read-only state produced by the Superteam large-bounty
scout, Algora and Opire scouts, and the payout-route planner.  It does not make
network requests, submit work, claim a bounty, or move funds.  A published
reward remains an unrealized opportunity even when its listing is verified.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


SCHEMA_VERSION = "1.0"
UTC = timezone.utc
DEFAULT_SUPERTEAM_LARGE = Path("/Agentic/state/superteam_large_bounty_scout.json")
DEFAULT_PAYOUT_ROUTE_MAP = Path("/Agentic/state/payout_route_map.json")
DEFAULT_ALGORA = Path("/Agentic/state/algora_bounty_qualifications.json")
DEFAULT_OPIRE = Path("/Agentic/state/opire_bounty_qualifications.json")
DEFAULT_RUSTCHAIN = Path("/Agentic/data/aro/rustchain_bounty_scout.json")
DEFAULT_OUTPUT = Path("/Agentic/state/bounty_priority_queue.json")
DEFAULT_MAX_SOURCE_AGE_SECONDS = 2 * 60 * 60
MAX_FUTURE_CLOCK_SKEW_SECONDS = 5 * 60
MAX_INPUT_BYTES = 16 * 1024 * 1024
MAX_CANDIDATES_PER_SOURCE = 2_000
MAX_ROUTES = 2_000
MAX_FINANCIAL_AMOUNT = Decimal("1e30")

SOURCE_ORDER = ("superteam_large", "rustchain", "algora", "opire")
ALL_INPUT_ORDER = ("superteam_large", "payout_route_map", "rustchain", "algora", "opire")
READY_STATUSES = {"ok", "success", "healthy"}
OPEN_STATUSES = {"open", "active", "accepting_submissions", "available"}
CLOSED_STATUSES = {"closed", "expired", "cancelled", "canceled", "paid", "archived", "inactive"}
HUMAN_ONLY_ACCESS = {"HUMAN_ONLY", "HUMAN_REQUIRED", "MANUAL_ONLY"}
COMPLETE_ROUTE_STATUSES = {"complete_verified", "route_complete_verified", "ready_verified", "executable_verified"}
PENDING_ROUTE_STATUSES = {"route_pending", "pending", "conversion_pending", "wallet_resolution_pending"}

ASSET_RE = re.compile(r"^[A-Z][A-Z0-9._-]{1,31}$")
NETWORK_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,63}$")
UNKNOWN_VALUES = {
    "",
    "any",
    "n/a",
    "none",
    "pending",
    "tbd",
    "unknown",
    "unknown_until_provider_contract",
    "unspecified",
}

CANONICAL_HUMAN_GATES: dict[str, tuple[str, ...]] = {
    "kyc": ("kyc", "kyc_required"),
    "identity": ("identity", "account_or_identity", "identity_required", "account_required"),
    "social": (
        "social",
        "social_account_or_publication",
        "social_required",
        "publication_required",
    ),
    "video": ("video", "video_required"),
    "real_funds": ("real_funds", "real_funds_required", "own_funds_required"),
    "trading": ("trading", "trading_or_gambling", "trading_required"),
    "manual": (
        "manual",
        "manual_action",
        "manual_required",
        "manual_review_required",
        "human_action_required",
    ),
}
MANUAL_COMPONENT_GATES = ("typeform_or_external_form", "personal_experience")


class QueueError(RuntimeError):
    """An input or output violated the deterministic queue contract."""


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise QueueError("NOW_MUST_BE_TIMEZONE_AWARE")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _reject_duplicate_keys(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise QueueError(f"DUPLICATE_JSON_KEY:{key}")
        result[key] = value
    return result


def decode_json(raw: bytes) -> Any:
    try:
        return json.loads(raw.decode("utf-8-sig"), object_pairs_hook=_reject_duplicate_keys)
    except QueueError:
        raise
    except Exception as error:
        raise QueueError(f"INVALID_JSON:{type(error).__name__}") from error


def parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC)


def _timestamp_from(mapping: Mapping[str, Any]) -> tuple[datetime | None, str | None]:
    for key in ("generated_at", "observed_at", "fetched_at", "updated_at", "timestamp", "scouted_at"):
        if key in mapping:
            return parse_timestamp(mapping.get(key)), key
    return None, None


def parse_decimal(value: Any, *, minimum: Decimal | None = None, maximum: Decimal | None = None) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    if not number.is_finite():
        return None
    if minimum is not None and number < minimum:
        return None
    if maximum is not None and number > maximum:
        return None
    return number


def json_number(value: Decimal | None) -> int | float | None:
    if value is None:
        return None
    integral = value.to_integral_value()
    if value == integral:
        return int(integral)
    return float(value)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _first_value(mappings: Iterable[Mapping[str, Any]], keys: Iterable[str]) -> Any:
    for mapping in mappings:
        for key in keys:
            if key in mapping and mapping.get(key) is not None:
                return mapping.get(key)
    return None


def _first_text(mappings: Iterable[Mapping[str, Any]], keys: Iterable[str]) -> str | None:
    key_list = tuple(keys)
    for mapping in mappings:
        for key in key_list:
            value = mapping.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _qualifier_candidate(row: Mapping[str, Any], payload: Mapping[str, Any]) -> Mapping[str, Any]:
    """Adapt a fail-closed qualifier receipt to the common candidate shape.

    Algora and Opire deliberately publish qualification receipts instead of an
    executable claim contract. The adapter preserves official reward evidence
    for deterministic monitoring, while provider-side user and payout gates
    keep the record out of autonomous execution.
    """
    adapted = dict(row)
    gates = _mapping(row.get("gates"))
    financial_truth = _mapping(row.get("financial_truth"))
    source = _mapping(payload.get("source"))
    platform = str(source.get("platform") or "").strip().lower()
    official_reward = (
        gates.get("official_algora_active_bounty") is True
        and gates.get("canonical_algora_open_board") is True
        if platform == "algora"
        else gates.get("official_opire_usd_reward") is True
    )
    payment_authority = gates.get("payment_authority_proven") is True
    workflow = _mapping(payload.get("workflow_contract"))
    requires_application = workflow.get("requires_before_application")
    provider_user_gate = (
        workflow.get("application_allowed") is not True
        or workflow.get("implementation_allowed") is not True
        or (isinstance(requires_application, list) and bool(requires_application))
    )

    adapted.setdefault("id", row.get("candidate_key"))
    adapted.setdefault("status", "open" if gates.get("issue_open_unassigned") is True else "inactive")
    adapted["verified_listing"] = bool(official_reward and payment_authority)
    adapted["provider_verified"] = payment_authority
    adapted.setdefault("agent_access", "HUMAN_REQUIRED" if provider_user_gate else "UNKNOWN")
    adapted["human_gates"] = {
        "kyc": False,
        "identity": False,
        "social": False,
        "video": bool(
            platform == "algora"
            and _mapping(row.get("quality")).get("demo_video_required_by_algora") is True
        ),
        "real_funds": False,
        "trading": False,
        "manual": provider_user_gate,
    }
    amount = parse_decimal(
        financial_truth.get("face_value_usd"),
        minimum=Decimal("0.000000000001"),
        maximum=MAX_FINANCIAL_AMOUNT,
    )
    if amount is not None and official_reward and payment_authority:
        adapted["reward"] = {"amount": json_number(amount), "token": "USD"}
    adapted["qualification_decision"] = str(row.get("decision") or "unknown").strip().lower()
    adapted["workflow_contract_blocked"] = provider_user_gate
    adapted["qualifier_rejection_reasons"] = (
        row.get("rejection_reasons") if isinstance(row.get("rejection_reasons"), list) else []
    )
    return adapted


def _candidate_rows(payload: Any, source: str | None = None) -> list[Mapping[str, Any]]:
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, Mapping):
        rows = []
        keys = ("qualifications", "qualified_candidates") if source in {"algora", "opire"} else ()
        for key in keys + ("candidates", "items", "bounties"):
            if isinstance(payload.get(key), list):
                rows = payload[key]
                break
    else:
        rows = []
    if len(rows) > MAX_CANDIDATES_PER_SOURCE:
        raise QueueError("TOO_MANY_CANDIDATES")
    filtered = [row for row in rows if isinstance(row, Mapping)]
    if (
        source in {"algora", "opire"}
        and isinstance(payload, Mapping)
        and isinstance(payload.get("qualifications"), list)
    ):
        return [_qualifier_candidate(row, payload) for row in filtered]
    return filtered


def _route_rows(payload: Any) -> list[Mapping[str, Any]]:
    if not isinstance(payload, Mapping):
        return []
    rows: Any = payload.get("routes")
    if not isinstance(rows, list):
        nested = payload.get("payout_routes")
        rows = nested.get("routes") if isinstance(nested, Mapping) else []
    if not isinstance(rows, list):
        rows = []
    if len(rows) > MAX_ROUTES:
        raise QueueError("TOO_MANY_ROUTES")
    return [row for row in rows if isinstance(row, Mapping)]


def _priority_candidate_rows(payload: Any) -> list[Mapping[str, Any]]:
    if not isinstance(payload, Mapping):
        return []
    rows = payload.get("priority_candidates")
    if not isinstance(rows, list):
        return []
    if len(rows) > MAX_CANDIDATES_PER_SOURCE:
        raise QueueError("TOO_MANY_ROUTE_CANDIDATES")
    return [row for row in rows if isinstance(row, Mapping)]


def _source_health(
    name: str,
    payload: Any,
    *,
    now: datetime,
    max_age_seconds: int,
    input_hash: str | None,
    input_error: str | None,
) -> dict[str, Any]:
    reasons: list[str] = []
    if input_error:
        reasons.append(input_error)
    if not isinstance(input_hash, str) or re.fullmatch(r"[0-9a-f]{64}", input_hash) is None:
        reasons.append("input_hash_missing_or_invalid")
    if not isinstance(payload, Mapping):
        reasons.append("source_not_object")
        status = None
        observed = None
        timestamp_key = None
    else:
        status = str(payload.get("status") or "").strip().lower() or None
        if status not in READY_STATUSES:
            qualifier_rows = payload.get("qualifications")
            qualified_rows = payload.get("qualified_candidates")
            source_metadata = _mapping(payload.get("source"))
            structurally_valid_qualifier = (
                name in {"algora", "opire"}
                and source_metadata.get("platform") == name
                and isinstance(qualifier_rows, list)
                and isinstance(qualified_rows, list)
                and payload.get("qualification_count") == len(qualifier_rows)
                and payload.get("qualified_count") == len(qualified_rows)
            )
            if structurally_valid_qualifier:
                status = "ok"
            elif name == "rustchain" and isinstance(payload.get("candidates"), list) and len(payload["candidates"]) > 0:
                status = "ok"
            else:
                reasons.append("source_status_not_ready")
        observed, timestamp_key = _timestamp_from(payload)
        if observed is None:
            reasons.append("source_timestamp_missing_or_invalid")

    age_seconds: int | None = None
    if observed is not None:
        age = (now - observed).total_seconds()
        age_seconds = math.floor(age)
        if age < -MAX_FUTURE_CLOCK_SKEW_SECONDS:
            reasons.append("source_timestamp_in_future")
        elif age > max_age_seconds:
            reasons.append("source_stale")

    fresh = not reasons
    return {
        "source": name,
        "status": status,
        "observed_at": iso_timestamp(observed) if observed is not None else None,
        "timestamp_field": timestamp_key,
        "age_seconds": age_seconds,
        "max_age_seconds": max_age_seconds,
        "fresh": fresh,
        "reason_codes": sorted(set(reasons)),
        "input_sha256": input_hash,
    }


def _normalized_asset(raw: Mapping[str, Any], overlay: Mapping[str, Any]) -> str | None:
    payout = _mapping(raw.get("payout"))
    reward = _mapping(raw.get("reward"))
    overlay_payout = _mapping(overlay.get("payout"))
    value = _first_text(
        (raw, payout, reward, overlay, overlay_payout),
        ("asset", "token", "reward_asset", "reward_token", "currency", "reward_currency"),
    )
    if value is None:
        return None
    normalized = value.upper()
    if normalized.lower() in UNKNOWN_VALUES or ASSET_RE.fullmatch(normalized) is None:
        return None
    return normalized


def _normalized_network(raw: Mapping[str, Any], overlay: Mapping[str, Any]) -> str | None:
    payout = _mapping(raw.get("payout"))
    reward = _mapping(raw.get("reward"))
    overlay_payout = _mapping(overlay.get("payout"))
    value = _first_text((raw, payout, reward, overlay, overlay_payout), ("network", "chain"))
    if value is None:
        provider = str(raw.get("provider") or "").strip().lower()
        source = str(raw.get("source") or "").strip().lower()
        if provider == "rustchain" and source == "rustchain":
            return "rustchain-native"
        return None
    normalized = value.lower()
    if normalized in UNKNOWN_VALUES or NETWORK_RE.fullmatch(normalized) is None:
        return None
    return normalized


def _candidate_id(source: str, raw: Mapping[str, Any]) -> tuple[str, bool]:
    value = _first_value((raw,), ("candidate_id", "id", "candidate_key", "bounty_id", "slug", "key"))
    if isinstance(value, (str, int)) and not isinstance(value, bool) and str(value).strip():
        return str(value).strip()[:200], True
    fallback = sha256_bytes(canonical_json_bytes(raw))[:20]
    return f"missing-{source}-{fallback}", False


def _listing_verified(raw: Mapping[str, Any]) -> bool:
    if any(
        raw.get(key) is True
        for key in ("verified_listing", "listing_verified", "source_verified", "listing_source_verified")
    ):
        return True
    provider = str(raw.get("provider") or "").strip().lower()
    source = str(raw.get("source") or "").strip().lower()
    action_contract = raw.get("action_contract")
    execution_contract = raw.get("execution_contract")
    has_explicit_contracts = (
        isinstance(action_contract, Mapping)
        and action_contract.get("verified") is True
        and isinstance(execution_contract, Mapping)
        and execution_contract.get("explicit") is True
        and execution_contract.get("autonomous") is True
    )
    if provider == "rustchain" and source == "rustchain" and has_explicit_contracts:
        return True
    return False


def _provider_verified(raw: Mapping[str, Any], source_payload: Mapping[str, Any]) -> bool:
    sponsor = _mapping(raw.get("sponsor"))
    provider = _mapping(raw.get("provider"))
    if any(
        value is True
        for value in (
            raw.get("provider_verified"),
            raw.get("sponsor_verified"),
            sponsor.get("verified"),
            sponsor.get("isVerified"),
            provider.get("verified"),
            source_payload.get("provider_verified"),
        )
    ):
        return True
    raw_provider_str = str(raw.get("provider") or "").strip().lower()
    raw_source_str = str(raw.get("source") or "").strip().lower()
    action_contract = raw.get("action_contract")
    if (
        raw_provider_str == "rustchain"
        and raw_source_str == "rustchain"
        and isinstance(action_contract, Mapping)
        and action_contract.get("verified") is True
    ):
        return True
    return False


def _human_gates(raw: Mapping[str, Any], overlay: Mapping[str, Any]) -> tuple[dict[str, bool | None], bool]:
    containers: list[Mapping[str, Any]] = []
    for owner in (raw, overlay):
        for key in ("human_gates", "gates"):
            value = owner.get(key)
            if isinstance(value, Mapping):
                containers.append(value)
        containers.append(owner)

    result: dict[str, bool | None] = {}
    for canonical, aliases in CANONICAL_HUMAN_GATES.items():
        found: bool | None = None
        for container in containers:
            for alias in aliases:
                value = container.get(alias)
                if isinstance(value, bool):
                    found = value
                    break
            if found is not None:
                break
        result[canonical] = found

    if result["manual"] is None:
        components: list[bool] = []
        for component in MANUAL_COMPONENT_GATES:
            value: bool | None = None
            for container in containers:
                candidate = container.get(component)
                if isinstance(candidate, bool):
                    value = candidate
                    break
            if value is not None:
                components.append(value)
        if len(components) == len(MANUAL_COMPONENT_GATES):
            result["manual"] = any(components)

    return result, all(isinstance(result[name], bool) for name in CANONICAL_HUMAN_GATES)


def _execution_contract(raw: Mapping[str, Any], overlay: Mapping[str, Any]) -> tuple[bool, bool]:
    """Return (explicit autonomous contract, explicit human action required)."""
    for owner in (raw, overlay):
        contract = owner.get("execution_contract")
        if isinstance(contract, Mapping):
            human_required = (
                contract.get("human_action_required") is True
                or contract.get("manual_action_required") is True
                or str(contract.get("human_action") or "").lower() not in {"", "none", "false"}
            )
            explicit = contract.get("explicit") is True or contract.get("verified") is True
            autonomous = (
                contract.get("autonomous") is True
                or contract.get("automation_allowed") is True
                or contract.get("execution_allowed") is True
                or str(contract.get("mode") or "").lower() in {"autonomous", "automatic"}
            )
            return bool(explicit and autonomous and not human_required), human_required

    explicit_flag = raw.get("execution_contract_explicit") is True or overlay.get("execution_contract_explicit") is True
    allowed_flag = raw.get("autonomous_execution_allowed") is True or overlay.get("autonomous_execution_allowed") is True
    human_required = raw.get("human_action_required") is True or overlay.get("human_action_required") is True
    return bool(explicit_flag and allowed_flag and not human_required), human_required


def _action_contract(raw: Mapping[str, Any], overlay: Mapping[str, Any]) -> dict[str, Any] | None:
    """Return only the non-secret fields required by a downstream executor.

    This is preservation, not authorization.  The queue's action gates and the
    executor's live provider revalidation both remain mandatory.
    """
    value: Mapping[str, Any] | None = None
    for owner in (raw, overlay):
        candidate = owner.get("action_contract")
        if isinstance(candidate, Mapping):
            value = candidate
            break
    if value is None:
        return None
    allowed = (
        "platform",
        "kind",
        "provider",
        "target_url",
        "claim_command",
        "verified",
        "autonomous",
        "provider_instruction_sha256",
    )
    return {key: value.get(key) for key in allowed if key in value}


def _gross_verified(raw: Mapping[str, Any], listing_verified: bool) -> Decimal | None:
    reward = _mapping(raw.get("reward"))
    payout = _mapping(raw.get("payout"))
    explicit = _first_value(
        (raw, reward, payout),
        ("gross_claimable_verified", "gross_verified", "verified_amount"),
    )
    explicit_number = parse_decimal(
        explicit,
        minimum=Decimal("0.000000000001"),
        maximum=MAX_FINANCIAL_AMOUNT,
    )
    if explicit_number is not None:
        return explicit_number
    if not listing_verified:
        return None
    published = _first_value(
        (raw, reward, payout),
        ("amount", "gross_listed_amount", "reward_amount", "amount_reward", "value"),
    )
    return parse_decimal(
        published,
        minimum=Decimal("0.000000000001"),
        maximum=MAX_FINANCIAL_AMOUNT,
    )


def _verified_metric(
    owners: Iterable[Mapping[str, Any]],
    *,
    explicit_keys: tuple[str, ...],
    plain_keys: tuple[str, ...],
    verification_keys: tuple[str, ...],
    minimum: Decimal,
) -> Decimal | None:
    for owner in owners:
        economics = _mapping(owner.get("economics"))
        for container in (owner, economics):
            for key in explicit_keys:
                number = parse_decimal(container.get(key), minimum=minimum, maximum=MAX_FINANCIAL_AMOUNT)
                if number is not None:
                    return number
            verified = (
                any(container.get(flag) is True for flag in verification_keys)
                or container.get("economics_verified") is True
                or owner.get("route_complete_verified") is True
            )
            if verified:
                for key in plain_keys:
                    number = parse_decimal(container.get(key), minimum=minimum, maximum=MAX_FINANCIAL_AMOUNT)
                    if number is not None:
                        return number
    return None


def _confidence_lcb_ppm(owners: Iterable[Mapping[str, Any]]) -> int | None:
    for owner in owners:
        economics = _mapping(owner.get("economics"))
        for container in (owner, economics):
            ppm = parse_decimal(
                _first_value((container,), ("payment_confidence_lcb_ppm", "payment_probability_lcb_ppm", "confidence_lcb_ppm")),
                minimum=Decimal(0),
                maximum=Decimal(1_000_000),
            )
            if ppm is not None:
                return int(ppm.to_integral_value())
            fraction = parse_decimal(
                _first_value((container,), ("payment_confidence_lcb", "payment_probability_lcb", "confidence_lcb")),
                minimum=Decimal(0),
                maximum=Decimal(1),
            )
            if fraction is not None:
                return int((fraction * Decimal(1_000_000)).to_integral_value())
    return None


def _time_to_wise_p90_seconds(owners: Iterable[Mapping[str, Any]]) -> int | None:
    for owner in owners:
        economics = _mapping(owner.get("economics"))
        for container in (owner, economics):
            seconds = parse_decimal(container.get("time_to_wise_p90_seconds"), minimum=Decimal(0))
            if seconds is not None:
                return int(seconds.to_integral_value())
            hours = parse_decimal(container.get("time_to_wise_p90_hours"), minimum=Decimal(0))
            if hours is not None:
                return int((hours * Decimal(3600)).to_integral_value())
    return None


def _route_id(route: Mapping[str, Any]) -> str:
    return str(route.get("route_id") or route.get("id") or "")[:200]


def _route_asset(route: Mapping[str, Any]) -> str | None:
    value = _first_text((route, _mapping(route.get("rail"))), ("asset", "token"))
    if value is None:
        return None
    normalized = value.upper()
    return normalized if normalized.lower() not in UNKNOWN_VALUES and ASSET_RE.fullmatch(normalized) else None


def _route_network(route: Mapping[str, Any]) -> str | None:
    value = _first_text((route, _mapping(route.get("rail"))), ("network", "chain"))
    if value is None:
        return None
    normalized = value.lower()
    return normalized if normalized not in UNKNOWN_VALUES and NETWORK_RE.fullmatch(normalized) else None


def _route_complete(route: Mapping[str, Any]) -> bool:
    status = str(route.get("status") or route.get("route_status") or "").lower()
    return (
        route.get("route_complete_verified") is True
        and route.get("execution_enabled") is True
        and (status in COMPLETE_ROUTE_STATUSES or status in {"ok", "ready"})
    )


def _self_custody_ready(route: Mapping[str, Any]) -> bool:
    rail = _mapping(route.get("rail"))
    role = _first_text((route, rail), ("role",))
    ready = _first_value((route, rail), ("receive_ready", "self_custody_ready"))
    return role == "client_receive_self_custody" and ready is True


def _route_human_gate(route: Mapping[str, Any], overlay: Mapping[str, Any]) -> bool:
    for owner in (route, overlay):
        if any(
            owner.get(key) is True
            for key in (
                "human_action_required",
                "manual_action_required",
                "operator_required",
                "kyc_required",
                "identity_required",
                "social_required",
                "video_required",
                "real_funds_required",
                "trading_required",
            )
        ):
            return True
        gates = owner.get("human_gates")
        if isinstance(gates, Mapping) and any(value is True for value in gates.values()):
            return True
        reason_codes = owner.get("reason_codes")
        if isinstance(reason_codes, list):
            for reason in reason_codes:
                code = str(reason).lower()
                if (
                    code.endswith("_kyc_required")
                    or code.endswith("_identity_required")
                    or code.endswith("_social_required")
                    or code.endswith("_video_required")
                    or code.endswith("_real_funds_required")
                    or code.endswith("_trading_required")
                    or code.endswith("_manual_required")
                    or code.endswith("_operator_required")
                    or code.endswith("_human_action_required")
                ):
                    return True
    return False


def _overlay_index(route_map: Any) -> dict[tuple[str, str], Mapping[str, Any]]:
    index: dict[tuple[str, str], Mapping[str, Any]] = {}
    for row in sorted(_priority_candidate_rows(route_map), key=lambda item: canonical_json_bytes(item)):
        source = str(row.get("source") or "").lower()
        candidate_id = str(row.get("candidate_id") or row.get("id") or row.get("slug") or "")
        if not candidate_id:
            continue
        keys = [(source, candidate_id)] if source else []
        keys.append(("*", candidate_id))
        for key in keys:
            index.setdefault(key, row)
    return index


def _candidate_overlay(index: Mapping[tuple[str, str], Mapping[str, Any]], source: str, candidate_id: str) -> Mapping[str, Any]:
    provider_alias = "superteam" if source == "superteam_large" else source
    return index.get((source, candidate_id)) or index.get((provider_alias, candidate_id)) or index.get(("*", candidate_id)) or {}


def _select_route(
    routes: Sequence[Mapping[str, Any]],
    raw: Mapping[str, Any],
    overlay: Mapping[str, Any],
    asset: str | None,
    network: str | None,
) -> Mapping[str, Any]:
    requested_id = _first_text((raw, overlay), ("route_id", "payout_route_id"))
    matches: list[Mapping[str, Any]] = []
    for route in routes:
        if requested_id and _route_id(route) == requested_id:
            if asset is None or network is None or (_route_asset(route) == asset and _route_network(route) == network):
                matches.append(route)
            continue
        if asset is not None and network is not None and _route_asset(route) == asset and _route_network(route) == network:
            matches.append(route)
    matches.sort(
        key=lambda route: (
            not _route_complete(route),
            not _self_custody_ready(route),
            _route_id(route),
            sha256_bytes(canonical_json_bytes(route)),
        )
    )
    return matches[0] if matches else {}


def _active_listing(raw: Mapping[str, Any]) -> bool:
    status = str(raw.get("status") or raw.get("listing_status") or "").strip().lower()
    if status in CLOSED_STATUSES:
        return False
    if status and status not in OPEN_STATUSES:
        return False
    active = raw.get("active")
    return active is not False


def _candidate_fresh(raw: Mapping[str, Any], source_fresh: bool, now: datetime, max_age_seconds: int) -> bool:
    if not source_fresh:
        return False
    observed, key = _timestamp_from(raw)
    if key is None:
        return True
    if observed is None:
        return False
    age = (now - observed).total_seconds()
    return -MAX_FUTURE_CLOCK_SKEW_SECONDS <= age <= max_age_seconds


def _normalized_candidate(
    *,
    source: str,
    raw: Mapping[str, Any],
    source_payload: Mapping[str, Any],
    source_health: Mapping[str, Any],
    routes: Sequence[Mapping[str, Any]],
    route_map_fresh: bool,
    overlays: Mapping[tuple[str, str], Mapping[str, Any]],
    now: datetime,
    max_age_seconds: int,
) -> tuple[str, dict[str, Any]]:
    candidate_id, id_present = _candidate_id(source, raw)
    overlay = _candidate_overlay(overlays, source, candidate_id)
    listing_verified = _listing_verified(raw)
    provider_verified = _provider_verified(raw, source_payload)
    agent_access = str(_first_value((raw, overlay), ("agent_access", "agentAccess")) or "UNKNOWN").upper()
    if agent_access == "UNKNOWN":
        provider_str = str(raw.get("provider") or "").strip().lower()
        source_str = str(raw.get("source") or "").strip().lower()
        exec_contract = raw.get("execution_contract")
        act_contract = raw.get("action_contract")
        if (
            provider_str == "rustchain"
            and source_str == "rustchain"
            and isinstance(exec_contract, Mapping)
            and exec_contract.get("autonomous") is True
            and exec_contract.get("human_action_required") is False
            and isinstance(act_contract, Mapping)
            and act_contract.get("verified") is True
        ):
            agent_access = "AGENT_ALLOWED"
    gates, gates_complete = _human_gates(raw, overlay)
    execution_contract_explicit, contract_human_required = _execution_contract(raw, overlay)
    asset = _normalized_asset(raw, overlay)
    network = _normalized_network(raw, overlay)
    route = _select_route(routes, raw, overlay, asset, network)
    exact_asset_network = bool(
        route and asset is not None and network is not None and _route_asset(route) == asset and _route_network(route) == network
    )
    route_complete = bool(route_map_fresh and route and _route_complete(route))
    self_custody_ready = bool(route_map_fresh and route and _self_custody_ready(route))
    route_human_gate = _route_human_gate(route, overlay)

    source_fresh = _candidate_fresh(raw, bool(source_health.get("fresh")), now, max_age_seconds)
    deadline_raw = _first_value((raw, overlay), ("deadline", "expires_at", "due_at"))
    deadline = parse_timestamp(deadline_raw)
    deadline_future = deadline is not None and deadline > now
    listing_active = _active_listing(raw)
    gross_verified = _gross_verified(raw, listing_verified)

    metric_owners = (raw, overlay, route)
    expected_wise_net = _verified_metric(
        metric_owners,
        explicit_keys=("expected_wise_net_verified",),
        plain_keys=("expected_wise_net",),
        verification_keys=("expected_wise_net_verified", "expected_wise_net_is_verified", "wise_net_verified"),
        minimum=Decimal("0.000000000001"),
    )
    net_if_paid = _verified_metric(
        metric_owners,
        explicit_keys=("net_if_paid_verified",),
        plain_keys=("net_if_paid",),
        verification_keys=("net_if_paid_verified", "net_if_paid_is_verified"),
        minimum=Decimal("0.000000000001"),
    )
    payment_confidence_lcb_ppm = _confidence_lcb_ppm(metric_owners)
    time_to_wise_p90_seconds = _time_to_wise_p90_seconds(metric_owners)

    route_status = str(
        _first_value((route, overlay), ("status", "route_status"))
        or ("route_missing" if not route else "route_pending")
    ).lower()
    if route_complete:
        route_status = "complete_verified"
    elif route_status not in PENDING_ROUTE_STATUSES:
        route_status = "route_pending"

    reasons: list[str] = []
    if not id_present:
        reasons.append("candidate_id_missing")
    if not source_fresh:
        reasons.append("listing_or_source_stale")
    if not listing_verified:
        reasons.append("listing_not_verified")
    if not listing_active:
        reasons.append("listing_not_active")
    if deadline is None:
        reasons.append("deadline_missing_or_invalid")
    elif not deadline_future:
        reasons.append("deadline_not_future")
    if not provider_verified:
        reasons.append("provider_not_verified")
    if agent_access != "AGENT_ALLOWED":
        reasons.append("agent_access_not_allowed")
    if not gates_complete:
        reasons.append("human_gates_incomplete")
    for gate_name, value in gates.items():
        if value is True:
            reasons.append(f"human_gate_{gate_name}")
    if contract_human_required:
        reasons.append("human_gate_manual")
    if route_human_gate:
        reasons.append("route_human_gate")
    if asset is None:
        reasons.append("exact_asset_missing")
    if network is None:
        reasons.append("exact_network_missing")
    if not exact_asset_network:
        reasons.append("exact_asset_network_route_missing")
    if not self_custody_ready:
        reasons.append("self_custody_rail_not_verified")
    if not route_complete:
        reasons.append("route_pending")
    if not execution_contract_explicit:
        reasons.append("explicit_execution_contract_missing")
    qualification_decision = str(raw.get("qualification_decision") or "").lower()
    if qualification_decision == "rejected":
        reasons.append("qualification_rejected")
    if raw.get("workflow_contract_blocked") is True:
        reasons.append("provider_workflow_human_gate")
    for reason in raw.get("qualifier_rejection_reasons") or []:
        if isinstance(reason, str) and reason.strip():
            reasons.append(f"qualifier:{reason.strip()[:120]}")
    if gross_verified is None:
        reasons.append("gross_not_verified")
    if expected_wise_net is None:
        reasons.append("expected_wise_net_not_verified")
    if payment_confidence_lcb_ppm is None or payment_confidence_lcb_ppm <= 0:
        reasons.append("payment_confidence_lcb_missing")
    if net_if_paid is None:
        reasons.append("net_if_paid_not_verified")
    if time_to_wise_p90_seconds is None:
        reasons.append("time_to_wise_p90_missing")

    human_gate_present = (
        any(value is True for value in gates.values())
        or contract_human_required
        or route_human_gate
        or raw.get("workflow_contract_blocked") is True
        or qualification_decision == "rejected"
    )
    # Research queue promotion: allow high-gross candidates with agent access to enter research
    # even when human gates are present, as long as listing is active and deadline is future.
    # This unblocks candidates like Rustchain $781K/$43K that fail only on route_human_gate.
    # Filter out claims by other users that pollute the research queue.
    # Titles like "Claim: X — username" indicate a submission, not an open bounty.
    _title_text = str(raw.get("title") or "").strip()
    _is_foreign_claim = bool(re.match(r"^Claim:\s*.+?\s*[—\-]\s*\w+$", _title_text))
    research_promotable = (
        (not _is_foreign_claim)
        and gross_verified is not None
        and gross_verified >= 1000
        and agent_access not in HUMAN_ONLY_ACCESS
        and listing_active
        and (deadline is None or deadline_future)
    )
    terminal_monitor = (human_gate_present or agent_access in HUMAN_ONLY_ACCESS or not listing_active or (deadline is not None and not deadline_future)) and not research_promotable

    action_ready = all(
        (
            id_present,
            source_fresh,
            listing_verified,
            listing_active,
            deadline_future,
            provider_verified,
            agent_access == "AGENT_ALLOWED",
            gates_complete,
            not any(value is not False for value in gates.values()),
            not contract_human_required,
            not route_human_gate,
            exact_asset_network,
            self_custody_ready,
            route_complete,
            execution_contract_explicit,
            gross_verified is not None,
            expected_wise_net is not None,
            payment_confidence_lcb_ppm is not None and payment_confidence_lcb_ppm > 0,
            net_if_paid is not None,
            time_to_wise_p90_seconds is not None,
        )
    )
    queue_name = "action_queue" if action_ready else ("monitor_only" if terminal_monitor else "research_queue")

    provider_name = _first_text((raw, _mapping(raw.get("provider"))), ("provider", "name"))
    if provider_name is None:
        provider_name = "superteam" if source == "superteam_large" else source
    title = _first_text((raw,), ("title", "name", "summary")) or ""
    url = _first_text((raw, overlay), ("url", "issue_url", "html_url"))
    platform = _first_text((raw, overlay), ("platform", "action_platform"))
    action = _first_text((raw, overlay), ("action", "execution_action"))
    claim_command = _first_text((raw, overlay), ("claim_command",))
    action_contract = _action_contract(raw, overlay)

    result = {
        "source": source,
        "candidate_id": candidate_id,
        "stable_id": f"{source}:{candidate_id}",
        "title": title[:300],
        "provider": provider_name[:100],
        "platform": platform.lower()[:40] if platform else None,
        "url": url[:500] if url else None,
        "action": action.lower()[:40] if action else None,
        "claim_command": claim_command[:100] if claim_command else None,
        "action_contract": action_contract,
        "listing_verified": listing_verified,
        "source_fresh": source_fresh,
        "provider_verified": provider_verified,
        "agent_access": agent_access,
        "human_gates": gates,
        "human_gates_complete": gates_complete,
        "asset": asset,
        "network": network,
        "asset_network_exact": exact_asset_network,
        "deadline": iso_timestamp(deadline) if deadline is not None else None,
        "gross_verified": json_number(gross_verified),
        "gross_classification": "verified_unrealized_opportunity_not_revenue" if gross_verified is not None else "unverified_not_revenue",
        "route_id": _route_id(route) or None,
        "route_status": route_status,
        "self_custody_rail_verified": self_custody_ready,
        "explicit_execution_contract": execution_contract_explicit,
        "qualification_decision": qualification_decision or None,
        "expected_wise_net_verified": json_number(expected_wise_net),
        "payment_confidence_lcb_ppm": payment_confidence_lcb_ppm,
        "net_if_paid_verified": json_number(net_if_paid),
        "time_to_wise_p90_seconds": time_to_wise_p90_seconds,
        "financial_classification": "unrealized_opportunity_not_revenue",
        "funds_moved": False,
        "realized": 0,
        "reason_codes": sorted(set(reasons)),
    }
    return queue_name, result


def _action_sort_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        -Decimal(str(row["expected_wise_net_verified"])),
        -int(row["payment_confidence_lcb_ppm"]),
        -Decimal(str(row["net_if_paid_verified"])),
        int(row["time_to_wise_p90_seconds"]),
        str(row["deadline"]),
        str(row["candidate_id"]),
        str(row["source"]),
    )


def _opportunity_sort_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
    gross = parse_decimal(row.get("gross_verified"))
    return (
        gross is None,
        -(gross or Decimal(0)),
        str(row.get("candidate_id") or ""),
        str(row.get("source") or ""),
    )


def build_priority_queue(
    superteam_large: Any,
    payout_route_map: Any,
    rustchain: Any,
    algora: Any,
    opire: Any,
    *,
    now: datetime | None = None,
    max_source_age_seconds: int = DEFAULT_MAX_SOURCE_AGE_SECONDS,
    input_hashes: Mapping[str, str | None] | None = None,
    input_errors: Mapping[str, str | None] | None = None,
) -> dict[str, Any]:
    """Build an auditable queue snapshot without performing external actions."""
    current = (now or utc_now()).astimezone(UTC)
    if max_source_age_seconds <= 0:
        raise QueueError("MAX_SOURCE_AGE_MUST_BE_POSITIVE")

    payloads = {
        "superteam_large": superteam_large,
        "payout_route_map": payout_route_map,
        "rustchain": rustchain,
        "algora": algora,
        "opire": opire,
    }
    if input_hashes is None:
        hashes = {name: sha256_bytes(canonical_json_bytes(payloads[name])) for name in ALL_INPUT_ORDER}
    else:
        hashes = {name: input_hashes.get(name) for name in ALL_INPUT_ORDER}
    errors = {name: (input_errors or {}).get(name) for name in ALL_INPUT_ORDER}
    health = {
        name: _source_health(
            name,
            payloads[name],
            now=current,
            max_age_seconds=max_source_age_seconds,
            input_hash=hashes[name],
            input_error=errors[name],
        )
        for name in ALL_INPUT_ORDER
    }

    routes = _route_rows(payout_route_map)
    overlays = _overlay_index(payout_route_map)
    queues: dict[str, list[dict[str, Any]]] = {
        "action_queue": [],
        "research_queue": [],
        "monitor_only": [],
    }
    source_payloads = {
        "superteam_large": superteam_large,
        "rustchain": rustchain,
        "algora": algora,
        "opire": opire,
    }
    seen: set[tuple[str, str]] = set()
    duplicate_count = 0
    for source in SOURCE_ORDER:
        payload = source_payloads[source]
        payload_mapping = _mapping(payload)
        rows = sorted(_candidate_rows(payload, source), key=canonical_json_bytes)
        for raw in rows:
            candidate_id, _ = _candidate_id(source, raw)
            identity = (source, candidate_id)
            if identity in seen:
                duplicate_count += 1
                continue
            seen.add(identity)
            queue_name, normalized = _normalized_candidate(
                source=source,
                raw=raw,
                source_payload=payload_mapping,
                source_health=health[source],
                routes=routes,
                route_map_fresh=bool(health["payout_route_map"]["fresh"]),
                overlays=overlays,
                now=current,
                max_age_seconds=max_source_age_seconds,
            )
            queues[queue_name].append(normalized)

    queues["action_queue"].sort(key=_action_sort_key)
    queues["research_queue"].sort(key=_opportunity_sort_key)
    queues["monitor_only"].sort(key=_opportunity_sort_key)

    all_rows = queues["action_queue"] + queues["research_queue"] + queues["monitor_only"]
    status = "ok" if all(health[name]["fresh"] for name in ALL_INPUT_ORDER) else "degraded_fail_closed"
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "aggregator": "bounty_priority_queue",
        "generated_at": iso_timestamp(current),
        "status": status,
        "policy": {
            "action_contract": [
                "fresh_verified_listing_source",
                "verified_provider",
                "AGENT_ALLOWED",
                "all_human_gates_explicit_false",
                "exact_asset_and_network",
                "verified_receive_ready_client_self_custody_rail",
                "complete_verified_route",
                "explicit_autonomous_execution_contract",
                "verified_ranking_metrics",
            ],
            "human_gate_disposition": "monitor_only",
            "route_pending_without_human_gate_disposition": "research_queue",
            "action_sort": [
                "expected_wise_net_verified:desc",
                "payment_confidence_lcb_ppm:desc",
                "net_if_paid_verified:desc",
                "time_to_wise_p90_seconds:asc",
                "deadline:asc",
                "candidate_id:asc",
            ],
            "research_sort": ["gross_verified_unrealized_opportunity:desc", "candidate_id:asc"],
            "gross_is_revenue": False,
            "settlement_evidence_consumed": False,
            "execution_performed": False,
        },
        "input_hashes": {name: hashes[name] for name in ALL_INPUT_ORDER},
        "source_health": {name: health[name] for name in ALL_INPUT_ORDER},
        "action_queue": queues["action_queue"],
        "research_queue": queues["research_queue"],
        "monitor_only": queues["monitor_only"],
        "summary": {
            "candidate_count": len(all_rows),
            "action_count": len(queues["action_queue"]),
            "research_count": len(queues["research_queue"]),
            "monitor_only_count": len(queues["monitor_only"]),
            "verified_gross_opportunity_count": sum(row["gross_verified"] is not None for row in all_rows),
            "human_gate_monitor_count": sum(
                any(value is True for value in row["human_gates"].values()) or "route_human_gate" in row["reason_codes"]
                for row in queues["monitor_only"]
            ),
            "route_pending_research_count": sum("route_pending" in row["reason_codes"] for row in queues["research_queue"]),
            "source_fresh_count": sum(health[name]["fresh"] for name in ALL_INPUT_ORDER),
            "source_count": len(ALL_INPUT_ORDER),
            "duplicate_source_candidate_count": duplicate_count,
            "funds_moved": False,
            "realized": 0,
        },
        "funds_moved": False,
        "realized": 0,
    }
    payload["result_sha256"] = sha256_bytes(canonical_json_bytes(payload))
    return payload


def read_input(path: Path) -> tuple[Any, bytes | None, str | None]:
    try:
        size = path.stat().st_size
        if size > MAX_INPUT_BYTES:
            return None, None, "input_too_large"
        raw = path.read_bytes()
    except OSError as error:
        return None, None, f"input_unreadable:{type(error).__name__}"
    try:
        return decode_json(raw), raw, None
    except QueueError as error:
        return None, raw, str(error).lower()


def atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = canonical_json_bytes(value) + b"\n"
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    temporary_path = Path(temporary_name)
    try:
        os.chmod(temporary_path, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        os.chmod(path, 0o600)
    except Exception:
        try:
            os.close(descriptor)
        except OSError:
            pass
        try:
            temporary_path.unlink()
        except OSError:
            pass
        raise


def run_from_paths(
    *,
    superteam_large_path: Path,
    payout_route_map_path: Path,
    rustchain_path: Path,
    algora_path: Path,
    opire_path: Path,
    output_path: Path,
    now: datetime | None = None,
    max_source_age_seconds: int = DEFAULT_MAX_SOURCE_AGE_SECONDS,
) -> dict[str, Any]:
    paths = {
        "superteam_large": superteam_large_path,
        "payout_route_map": payout_route_map_path,
        "rustchain": rustchain_path,
        "algora": algora_path,
        "opire": opire_path,
    }
    values: dict[str, Any] = {}
    hashes: dict[str, str | None] = {}
    errors: dict[str, str | None] = {}
    for name in ALL_INPUT_ORDER:
        value, raw, error = read_input(paths[name])
        values[name] = value
        hashes[name] = sha256_bytes(raw) if raw is not None else None
        errors[name] = error
    snapshot = build_priority_queue(
        values["superteam_large"],
        values["payout_route_map"],
        values["rustchain"],
        values["algora"],
        values["opire"],
        now=now,
        max_source_age_seconds=max_source_age_seconds,
        input_hashes=hashes,
        input_errors=errors,
    )
    atomic_write_json(output_path, snapshot)
    return snapshot


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--superteam-large", default=str(DEFAULT_SUPERTEAM_LARGE))
    parser.add_argument("--payout-route-map", default=str(DEFAULT_PAYOUT_ROUTE_MAP))
    parser.add_argument("--algora", default=str(DEFAULT_ALGORA))
    parser.add_argument("--opire", default=str(DEFAULT_OPIRE))
    parser.add_argument("--rustchain", default=str(DEFAULT_RUSTCHAIN))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--max-source-age-seconds", type=int, default=DEFAULT_MAX_SOURCE_AGE_SECONDS)
    parser.add_argument("--now", help="Optional timezone-aware ISO-8601 time for deterministic replay/tests")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    now = parse_timestamp(args.now) if args.now else None
    if args.now and now is None:
        print(json.dumps({"status": "failed_closed", "reason_code": "invalid_now"}, sort_keys=True), file=sys.stderr)
        return 2
    try:
        snapshot = run_from_paths(
            superteam_large_path=Path(args.superteam_large),
            payout_route_map_path=Path(args.payout_route_map),
            rustchain_path=Path(args.rustchain),
            algora_path=Path(args.algora),
            opire_path=Path(args.opire),
            output_path=Path(args.output),
            now=now,
            max_source_age_seconds=args.max_source_age_seconds,
        )
    except Exception as error:
        print(
            json.dumps(
                {"status": "failed_closed", "reason_code": type(error).__name__},
                ensure_ascii=True,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    print(
        json.dumps(
            {
                "status": snapshot["status"],
                "output": str(args.output),
                "summary": snapshot["summary"],
                "funds_moved": False,
                "realized": 0,
            },
            ensure_ascii=True,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Read-only, fail-closed scout for any explicit-token bounty on Superteam.

This program only reads Superteam's public API and atomically writes a local
observation state.  It never logs in, claims, submits, publishes, messages, or
performs a transaction.  A verified listing is deliberately never promoted to
autonomous eligibility.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import os
import re
import sys
import tempfile
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

SCHEMA_VERSION = "1.0"
LIST_URL = (
    "https://superteam.fun/api/listings?context=all&tab=bounties&category=All"
    "&status=open&sortBy=Prize&order=desc&region=&sponsor="
)
DETAIL_URL_TEMPLATE = "https://superteam.fun/api/listings/details/{slug}"
DEFAULT_OUTPUT_PATH = Path("/Agentic/state/superteam_large_bounty_scout.json")
USER_AGENT = "Agentic-ReadOnly-Superteam-Large-Bounty-Scout/1.0"
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
MAX_LISTINGS = 1_000
MAX_DETAILS = 200
REQUEST_TIMEOUT_SECONDS = 30
SLUG_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,198}[a-z0-9])?$")
TOKEN_PATTERN = re.compile(r"^[A-Z][A-Z0-9]{1,15}$")

GATE_NAMES = (
    "real_funds",
    "trading_or_gambling",
    "social_account_or_publication",
    "video",
    "typeform_or_external_form",
    "account_or_identity",
    "kyc",
    "personal_experience",
)

# The expressions intentionally classify explicit requirements conservatively.
# Matches produce stable evidence codes, never copied excerpts from a listing.
GATE_PATTERNS: dict[str, tuple[tuple[str, re.Pattern[str]], ...]] = {
    "real_funds": (
        ("REAL_FUNDS_EXPLICIT", re.compile(r"\breal funds?\b")),
        (
            "OWN_FUNDS_EXPLICIT",
            re.compile(r"\b(?:your|their|participants?[' ]s) own (?:accounts? and )?funds?\b"),
        ),
        (
            "REQUIRED_REAL_TRADE",
            re.compile(
                r"\b(?:must|required to|need to|have to|show at least one)"
                r"[^.!?\n]{0,100}\breal trade\b"
            ),
        ),
        (
            "REQUIRED_DEPOSIT_OR_PURCHASE",
            re.compile(
                r"\b(?:must|required to|need to|have to)"
                r"[^.!?\n]{0,100}\b(?:deposit|purchase|buy)\b"
            ),
        ),
        (
            "MINIMUM_FINANCIAL_VOLUME",
            re.compile(
                r"\b(?:minimum|at least)\s+(?:[$€£]\s*)?[0-9][0-9,.]*"
                r"[^.!?\n]{0,40}\b(?:trading|transaction|sales?) volume\b"
            ),
        ),
    ),
    "trading_or_gambling": (
        (
            "TRADING_ACTIVITY",
            re.compile(r"\b(?:trade|trades|trader|traders|trading|perpetuals?|pnl|roi)\b"),
        ),
        (
            "GAMBLING_ACTIVITY",
            re.compile(r"\b(?:casino|gambling|gameplay|bet|bets|betting|wager|wagering)\b"),
        ),
    ),
    "social_account_or_publication": (
        (
            "SOCIAL_ACCOUNT_OR_HANDLE",
            re.compile(
                r"\b(?:x|twitter)\s+(?:account|username|handle|profile|presence)\b"
            ),
        ),
        (
            "SOCIAL_POST_OR_THREAD",
            re.compile(
                r"\b(?:x|twitter)\s+(?:post|posts|thread|threads)\b|"
                r"\b(?:post|publish|share)[^.!?\n]{0,90}\b(?:on|to)\s+(?:x|twitter)\b"
            ),
        ),
        ("SOCIAL_TAG_REQUIRED", re.compile(r"\btag\s+@[a-z0-9_]+\b")),
        (
            "PUBLIC_ARTIFACT_REQUIRED",
            re.compile(
                r"\bpublic\s+(?:github\s+)?(?:pull request|repository|post|thread|article)\b"
            ),
        ),
        (
            "PUBLICATION_ARTIFACT_REQUIRED",
            re.compile(
                r"\b(?:create|submit|publish|write)[^.!?\n]{0,70}"
                r"\b(?:writeup|article|post|thread)\b"
            ),
        ),
    ),
    "video": (
        (
            "VIDEO_EXPLICITLY_REQUIRED",
            re.compile(
                r"\b(?:must|required to|need to|have to)[^.!?\n]{0,100}\bvideo\b|"
                r"\bvideo\b[^.!?\n]{0,50}\b(?:must|required|mandatory)\b"
            ),
        ),
        (
            "VIDEO_DEMONSTRATION_REQUIRED",
            re.compile(
                r"\b(?:create|record|produce|submit|provide|post|upload)"
                r"[^.!?\n]{0,80}\b(?:video demonstration|demo(?:nstration)? video)\b"
            ),
        ),
        (
            "VIDEO_LINK_REQUIRED",
            re.compile(r"\b(?:link|url)\s+to\s+(?:your\s+)?(?:demo(?:nstration)?\s+)?video\b"),
        ),
    ),
    "typeform_or_external_form": (
        ("TYPEFORM_REQUIRED", re.compile(r"\btypeform\b")),
        ("GOOGLE_FORM_REQUIRED", re.compile(r"\bgoogle forms?\b")),
        ("EXTERNAL_FORM_REQUIRED", re.compile(r"\bexternal forms?\b")),
        (
            "FORM_SUBMISSION_REQUIRED",
            re.compile(
                r"\bsubmit[^.!?\n]{0,100}\b(?:through|using|via)\b"
                r"[^.!?\n]{0,50}\bforms?\b"
            ),
        ),
    ),
    "account_or_identity": (
        (
            "ACCOUNT_REQUIRED",
            re.compile(
                r"\b(?:create|open|register|sign up for|log in to|connect|use)"
                r"[^.!?\n]{0,80}\baccount\b"
            ),
        ),
        (
            "ACCOUNT_IDENTIFIER_REQUIRED",
            re.compile(
                r"\b(?:your|same|what)\s+(?:email address|wallet address|username|"
                r"account|[a-z0-9]+ id)\b"
            ),
        ),
        (
            "VERIFIED_ACCOUNT_REQUIRED",
            re.compile(r"\b(?:public,?\s+)?(?:blue-)?verified[^.!?\n]{0,50}\baccount\b"),
        ),
        (
            "GITHUB_ACCOUNT_ACTION_REQUIRED",
            re.compile(r"\b(?:github\s+)?pull request\b"),
        ),
        (
            "WALLET_IDENTITY_REQUIRED",
            re.compile(r"\b(?:wallet|deposit|contract|mint) address\b"),
        ),
        (
            "WALLET_CONNECTION_REQUIRED",
            re.compile(r"\bconnect(?:ing)?\s+(?:a|your)\s+[^.!?\n]{0,30}\bwallet\b"),
        ),
    ),
    "kyc": (
        (
            "KYC_COMPLETION_REQUIRED",
            re.compile(
                r"\b(?:complete|pass|undergo|provide|submit)[^.!?\n]{0,60}\bkyc\b"
            ),
        ),
        (
            "KYC_EXPLICITLY_REQUIRED",
            re.compile(r"\bkyc(?: verification)?\s+(?:is\s+)?(?:required|mandatory)\b"),
        ),
        ("KNOW_YOUR_CUSTOMER_REQUIRED", re.compile(r"\bknow your customer\b")),
    ),
    "personal_experience": (
        (
            "OWN_EXPERIENCE_REQUIRED",
            re.compile(
                r"\b(?:your|their|participants?[' ]s)\s+(?:own|personal|actual|real)"
                r"[^.!?\n]{0,70}\b(?:experience|trades?|usage|results?|perspective|opinion)\b"
            ),
        ),
        (
            "BASED_ON_EXPERIENCE_REQUIRED",
            re.compile(r"\bbased on your (?:own )?(?:product )?experience\b"),
        ),
        (
            "SHARE_PERSONAL_VIEW_REQUIRED",
            re.compile(r"\bshare your (?:own )?(?:experience|perspective|opinion|feedback)\b"),
        ),
        (
            "DOCUMENT_PERSONAL_EXPERIENCE_REQUIRED",
            re.compile(
                r"\b(?:document|describe|explain)[^.!?\n]{0,60}\byour (?:own )?"
                r"(?:experience|journey)\b"
            ),
        ),
        ("REAL_PRODUCT_USAGE_REQUIRED", re.compile(r"\breal product usage\b")),
    ),
}


class ScoutError(RuntimeError):
    """A bounded, public-data operation could not be verified."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


JsonDetailLoader = Callable[[str], tuple[Any, bytes]]


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data)

    def text(self) -> str:
        return " ".join(self.parts)


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def canonical_json_bytes(value: Any) -> bytes:
    try:
        rendered = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as error:
        raise ScoutError("NON_CANONICAL_STATE") from error
    return rendered.encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _reject_duplicate_keys(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ScoutError("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def decode_json(raw: bytes) -> Any:
    try:
        text = raw.decode("utf-8")
        return json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=lambda _value: (_ for _ in ()).throw(
                ScoutError("NON_FINITE_JSON_NUMBER")
            ),
        )
    except ScoutError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ScoutError("INVALID_JSON_RESPONSE") from error


def _validate_public_url(url: str) -> None:
    if url == LIST_URL:
        return
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "superteam.fun"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in {None, 443}
        or parsed.query
        or parsed.fragment
        or not parsed.path.startswith("/api/listings/details/")
    ):
        raise ScoutError("UNTRUSTED_SOURCE_URL")
    slug = parsed.path.removeprefix("/api/listings/details/")
    if not SLUG_PATTERN.fullmatch(slug):
        raise ScoutError("UNTRUSTED_SOURCE_URL")


def fetch_public_json(url: str) -> tuple[Any, bytes]:
    """Fetch one bounded public JSON document without cookies or credentials."""
    _validate_public_url(url)
    request = Request(
        url,
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
        method="GET",
    )
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            status = getattr(response, "status", 200)
            final_url = response.geturl()
            content_type = str(response.headers.get("Content-Type") or "")
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as error:
        raise ScoutError(f"SOURCE_HTTP_{error.code}") from error
    except (URLError, TimeoutError, OSError) as error:
        raise ScoutError("SOURCE_FETCH_FAILED") from error
    _validate_public_url(final_url)
    if final_url != url:
        raise ScoutError("SOURCE_REDIRECTED")
    if status != 200:
        raise ScoutError(f"SOURCE_HTTP_{status}")
    if "application/json" not in content_type.casefold():
        raise ScoutError("SOURCE_CONTENT_TYPE_NOT_JSON")
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ScoutError("SOURCE_RESPONSE_TOO_LARGE")
    return decode_json(raw), raw


def parse_deadline(value: Any) -> tuple[datetime, str] | None:
    if not isinstance(value, str) or not value or value != value.strip():
        return None
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    parsed = parsed.astimezone(UTC)
    return parsed, iso_timestamp(parsed)


def parse_positive_number(value: Any) -> Decimal | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    try:
        parsed = Decimal(str(value))
    except InvalidOperation:
        return None
    if not parsed.is_finite() or parsed <= 0:
        return None
    return parsed


def decimal_to_json_number(value: Decimal) -> int | float:
    if value == value.to_integral_value():
        return int(value)
    rendered = float(value)
    if not math.isfinite(rendered):
        raise ScoutError("AMOUNT_OUT_OF_JSON_RANGE")
    return rendered


def _list_rejection_codes(row: Any, now: datetime) -> list[str]:
    if not isinstance(row, Mapping):
        return ["LIST_ROW_NOT_OBJECT"]
    reasons: list[str] = []
    if row.get("type") != "bounty":
        reasons.append("LIST_TYPE_NOT_BOUNTY")
    if row.get("status") != "OPEN":
        reasons.append("LIST_STATUS_NOT_OPEN")
    if not isinstance(row.get("token"), str) or not TOKEN_PATTERN.fullmatch(row["token"]):
        reasons.append("LIST_TOKEN_NOT_EXPLICIT")
    if parse_positive_number(row.get("rewardAmount")) is None:
        reasons.append("LIST_AMOUNT_NOT_NUMERIC_POSITIVE")
    parsed_deadline = parse_deadline(row.get("deadline"))
    if parsed_deadline is None or parsed_deadline[0] <= now:
        reasons.append("LIST_DEADLINE_NOT_FUTURE")
    slug = row.get("slug")
    if not isinstance(slug, str) or not SLUG_PATTERN.fullmatch(slug):
        reasons.append("LIST_SLUG_INVALID")
    listing_id = row.get("id")
    if not isinstance(listing_id, str) or not listing_id.strip():
        reasons.append("LIST_ID_INVALID")
    return reasons


def select_list_candidates(
    payload: Any, *, now: datetime
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    if not isinstance(payload, list):
        raise ScoutError("LIST_RESPONSE_NOT_ARRAY")
    if len(payload) > MAX_LISTINGS:
        raise ScoutError("LIST_RESPONSE_TOO_MANY_ROWS")
    rejection_counts: Counter[str] = Counter()
    selected: list[dict[str, Any]] = []
    for row in payload:
        reasons = _list_rejection_codes(row, now)
        if reasons:
            rejection_counts.update(reasons)
            continue
        assert isinstance(row, Mapping)
        parsed_deadline = parse_deadline(row["deadline"])
        amount = parse_positive_number(row["rewardAmount"])
        assert parsed_deadline is not None and amount is not None
        sponsor = row.get("sponsor")
        sponsor_result: dict[str, Any] = {
            "name": None,
            "slug": None,
            "verified": False,
        }
        if isinstance(sponsor, Mapping):
            sponsor_result = {
                "name": sponsor.get("name") if isinstance(sponsor.get("name"), str) else None,
                "slug": sponsor.get("slug") if isinstance(sponsor.get("slug"), str) else None,
                "verified": sponsor.get("isVerified") is True,
            }
        selected.append(
            {
                "_amount_decimal": amount,
                "_deadline_datetime": parsed_deadline[0],
                "id": row["id"],
                "slug": row["slug"],
                "title": row.get("title") if isinstance(row.get("title"), str) else "",
                "amount_reward": decimal_to_json_number(amount),
                "reward_token": row["token"],
                "deadline": parsed_deadline[1],
                "agent_access": (
                    row.get("agentAccess")
                    if isinstance(row.get("agentAccess"), str)
                    else None
                ),
                "sponsor": sponsor_result,
            }
        )
    if len(selected) > MAX_DETAILS:
        raise ScoutError("TOO_MANY_DETAIL_REQUESTS")
    selected.sort(
        key=lambda item: (
            -item["_amount_decimal"],
            item["_deadline_datetime"],
            item["slug"],
        )
    )
    return selected, dict(sorted(rejection_counts.items()))


def _flatten_text(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        result: list[str] = []
        for key in sorted(value):
            result.extend(_flatten_text(value[key]))
        return result
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        result = []
        for item in value:
            result.extend(_flatten_text(item))
        return result
    return []


def _visible_normalized_text(detail: Mapping[str, Any]) -> str:
    raw_parts: list[str] = []
    for field in ("title", "description", "requirements", "eligibility"):
        raw_parts.extend(_flatten_text(detail.get(field)))
    parser = _VisibleTextParser()
    try:
        parser.feed(" ".join(raw_parts))
        parser.close()
    except Exception as error:
        raise ScoutError("DETAIL_HTML_PARSE_FAILED") from error
    text = html.unescape(parser.text()).casefold()
    text = text.replace("’", "'").replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", text).strip()


def classify_gates(detail: Mapping[str, Any]) -> tuple[dict[str, bool], dict[str, list[str]]]:
    text = _visible_normalized_text(detail)
    # Explicit negations are removed only for KYC classification.  The other
    # gates remain conservative because their mere required activity can block
    # unattended participation even when the prose discusses risks or limits.
    kyc_text = re.sub(
        r"\b(?:no|without|does not require|doesn't require|not requiring|kyc-free)"
        r"[^.!?\n]{0,12}\bkyc\b|\bno kyc\b",
        " ",
        text,
    )
    gates: dict[str, bool] = {}
    evidence: dict[str, list[str]] = {}
    for gate_name in GATE_NAMES:
        subject = kyc_text if gate_name == "kyc" else text
        codes = [
            code
            for code, pattern in GATE_PATTERNS[gate_name]
            if pattern.search(subject) is not None
        ]
        gates[gate_name] = bool(codes)
        evidence[gate_name] = codes
    return gates, evidence


def _verify_detail(
    summary: Mapping[str, Any], detail: Any, *, now: datetime
) -> tuple[list[str], Mapping[str, Any] | None]:
    if not isinstance(detail, Mapping):
        return ["DETAIL_RESPONSE_NOT_OBJECT"], None
    reasons: list[str] = []
    if detail.get("id") != summary["id"]:
        reasons.append("DETAIL_ID_MISMATCH")
    if detail.get("slug") != summary["slug"]:
        reasons.append("DETAIL_SLUG_MISMATCH")
    if detail.get("type") != "bounty":
        reasons.append("DETAIL_TYPE_NOT_BOUNTY")
    if detail.get("status") != "OPEN":
        reasons.append("DETAIL_STATUS_NOT_OPEN")
    if detail.get("token") != summary["reward_token"]:
        reasons.append("DETAIL_TOKEN_MISMATCH")
    detail_amount = parse_positive_number(detail.get("rewardAmount"))
    summary_amount = parse_positive_number(summary.get("amount_reward"))
    if detail_amount is None:
        reasons.append("DETAIL_AMOUNT_NOT_NUMERIC_POSITIVE")
    elif summary_amount is None or detail_amount != summary_amount:
        reasons.append("DETAIL_AMOUNT_MISMATCH")
    if maximum_individual_reward(detail) is None:
        reasons.append("DETAIL_INDIVIDUAL_REWARD_NOT_VERIFIED")
    detail_deadline = parse_deadline(detail.get("deadline"))
    if detail_deadline is None or detail_deadline[0] <= now:
        reasons.append("DETAIL_DEADLINE_NOT_FUTURE")
    elif detail_deadline[1] != summary["deadline"]:
        reasons.append("DETAIL_DEADLINE_MISMATCH")
    return reasons, detail


def maximum_individual_reward(detail: Mapping[str, Any]) -> Decimal | None:
    """Return the largest explicitly listed per-winner reward.

    `rewardAmount` is a pool total on Superteam and must not be used as the
    amount one submission can win. Only the official fixed reward map is
    accepted; variable/range compensation remains unknown.
    """
    if detail.get("compensationType") not in (None, "fixed"):
        return None
    rewards = detail.get("rewards")
    if not isinstance(rewards, Mapping) or not rewards:
        return None
    parsed: list[Decimal] = []
    for value in rewards.values():
        amount = parse_positive_number(value)
        if amount is None:
            return None
        parsed.append(amount)
    return max(parsed) if parsed else None


def _candidate_from_detail(
    *,
    rank: int,
    summary: Mapping[str, Any],
    list_sha256: str,
    detail_url: str,
    detail_raw: bytes | None,
    detail: Any,
    operational_error: str | None,
    now: datetime,
) -> dict[str, Any]:
    maximum_reward: Decimal | None = None
    if operational_error is not None:
        verification_reasons = [operational_error]
        verified = False
        gates: dict[str, bool | None] = {name: None for name in GATE_NAMES}
        gate_evidence = {name: [] for name in GATE_NAMES}
        agent_access = summary.get("agent_access")
    else:
        verification_reasons, detail_mapping = _verify_detail(summary, detail, now=now)
        verified = not verification_reasons
        if detail_mapping is None:
            gates = {name: None for name in GATE_NAMES}
            gate_evidence = {name: [] for name in GATE_NAMES}
            agent_access = summary.get("agent_access")
        else:
            gates, gate_evidence = classify_gates(detail_mapping)
            maximum_reward = maximum_individual_reward(detail_mapping)
            agent_access = (
                detail_mapping.get("agentAccess")
                if isinstance(detail_mapping.get("agentAccess"), str)
                else summary.get("agent_access")
            )
        if verified:
            verification_reasons = ["LIST_AND_DETAIL_MATCH_VERIFIED"]

    autonomy_reasons = ["AUTONOMY_DEFAULT_DENY", "MANUAL_REVIEW_REQUIRED"]
    if not verified:
        autonomy_reasons.append("LISTING_NOT_VERIFIED")
    if agent_access != "AGENT_ALLOWED":
        autonomy_reasons.append("AGENT_ACCESS_NOT_ALLOWED")
    for gate_name in GATE_NAMES:
        if gates[gate_name] is True:
            autonomy_reasons.append(f"GATE_{gate_name.upper()}")
        elif gates[gate_name] is None:
            autonomy_reasons.append(f"GATE_{gate_name.upper()}_UNKNOWN")

    candidate: dict[str, Any] = {
        "rank": rank,
        "id": summary["id"],
        "slug": summary["slug"],
        "title": summary["title"],
        "network": "solana-mainnet",
        "reward": {
            "amount": decimal_to_json_number(maximum_reward) if maximum_reward is not None else None,
            "amount_basis": "MAXIMUM_INDIVIDUAL_REWARD",
            "total_pool_amount": summary["amount_reward"],
            "token": summary["reward_token"],
            "classification": "UNREALIZED_UNAUDITED_MAXIMUM_INDIVIDUAL_FACE_VALUE",
            "total_pool_classification": "UNREALIZED_UNAUDITED_POOL_FACE_VALUE",
        },
        "deadline": summary["deadline"],
        "sponsor": summary["sponsor"],
        "agent_access": agent_access,
        "verified_listing": verified,
        "autonomy_qualified": False,
        "verification_reason_codes": verification_reasons,
        "autonomy_reason_codes": autonomy_reasons,
        "gates": gates,
        "gate_evidence_codes": gate_evidence,
        "source_urls": {"list": LIST_URL, "detail": detail_url},
        "source_hashes": {
            "list_sha256": list_sha256,
            "detail_sha256": sha256_bytes(detail_raw) if detail_raw is not None else None,
        },
    }
    candidate["candidate_sha256"] = sha256_bytes(canonical_json_bytes(candidate))
    return candidate


def build_state(
    list_payload: Any,
    list_raw: bytes,
    detail_loader: JsonDetailLoader,
    *,
    now: datetime,
) -> dict[str, Any]:
    if now.tzinfo is None:
        raise ScoutError("NOW_MUST_BE_TIMEZONE_AWARE")
    now = now.astimezone(UTC)
    selected, rejection_counts = select_list_candidates(list_payload, now=now)
    list_hash = sha256_bytes(list_raw)
    candidates: list[dict[str, Any]] = []
    operational_errors: list[dict[str, str]] = []
    for index, summary in enumerate(selected, start=1):
        slug = summary["slug"]
        detail_url = DETAIL_URL_TEMPLATE.format(slug=slug)
        try:
            detail, detail_raw = detail_loader(slug)
            operational_error = None
        except ScoutError as error:
            detail = None
            detail_raw = None
            operational_error = error.code
            operational_errors.append({"slug": slug, "reason_code": error.code})
        candidates.append(
            _candidate_from_detail(
                rank=index,
                summary=summary,
                list_sha256=list_hash,
                detail_url=detail_url,
                detail_raw=detail_raw,
                detail=detail,
                operational_error=operational_error,
                now=now,
            )
        )

    def candidate_order(item: Mapping[str, Any]) -> tuple[Any, ...]:
        reward = item.get("reward") if isinstance(item.get("reward"), Mapping) else {}
        amount = parse_positive_number(reward.get("amount"))
        return (
            amount is None,
            -amount if amount is not None else Decimal(0),
            str(item.get("deadline") or ""),
            str(item.get("slug") or ""),
        )

    candidates.sort(key=candidate_order)
    for index, candidate in enumerate(candidates, start=1):
        candidate["rank"] = index
        candidate.pop("candidate_sha256", None)
        candidate["candidate_sha256"] = sha256_bytes(canonical_json_bytes(candidate))

    verified_count = sum(item["verified_listing"] is True for item in candidates)
    individual_reward_count = sum(
        parse_positive_number((item.get("reward") or {}).get("amount")) is not None
        for item in candidates
    )
    policy = {
        "read_only": True,
        "public_data_only": True,
        "network_methods": ["GET"],
        "forbidden_actions": [
            "claim",
            "login",
            "message",
            "submission",
            "transaction",
        ],
        "required_filters": {
            "type": "bounty",
            "status": "OPEN",
            "token": "explicit_symbol_from_listing",
            "token_match": "exact_case_sensitive_list_detail_match",
            "deadline": "future_utc",
            "reward_amount": "numeric_gt_zero",
            "individual_reward": "official_fixed_reward_map_numeric_positive",
        },
        "sort": ["reward.maximum_individual_amount:desc", "deadline:asc", "slug:asc"],
        "autonomy": "default_deny_manual_review_required",
        "ordinary_candidates": "silent_state_only",
    }
    hash_basis = {
        "schema_version": SCHEMA_VERSION,
        "status": "failed_closed" if operational_errors else "ok",
        "policy": policy,
        "list_sha256": list_hash,
        "list_rejection_reason_counts": rejection_counts,
        "candidates": candidates,
        "operational_errors": operational_errors,
    }
    result_hash = sha256_bytes(canonical_json_bytes(hash_basis))
    return {
        "schema_version": SCHEMA_VERSION,
        "scout": "superteam_large_bounty",
        "generated_at": iso_timestamp(now),
        "status": "failed_closed" if operational_errors else "ok",
        "policy": policy,
        "sources": {
            "list": {"url": LIST_URL, "sha256": list_hash},
            "detail_url_template": DETAIL_URL_TEMPLATE,
            "detail_requests": len(selected),
        },
        "summary": {
            "api_listing_count": len(list_payload),
            "list_filter_candidate_count": len(selected),
            "verified_listing_count": verified_count,
            "maximum_individual_reward_verified_count": individual_reward_count,
            "autonomy_qualified_count": 0,
            "detail_operational_error_count": len(operational_errors),
            "list_rejection_reason_counts": rejection_counts,
        },
        "candidates": candidates,
        "operational_errors": operational_errors,
        "result_sha256": result_hash,
    }


def build_failure_state(reason_code: str, *, now: datetime) -> dict[str, Any]:
    basis = {
        "schema_version": SCHEMA_VERSION,
        "status": "failed_closed",
        "reason_code": reason_code,
        "candidates": [],
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "scout": "superteam_large_bounty",
        "generated_at": iso_timestamp(now),
        "status": "failed_closed",
        "policy": {
            "read_only": True,
            "public_data_only": True,
            "autonomy": "default_deny_manual_review_required",
        },
        "sources": {"list": {"url": LIST_URL, "sha256": None}},
        "summary": {
            "api_listing_count": 0,
            "list_filter_candidate_count": 0,
            "verified_listing_count": 0,
            "autonomy_qualified_count": 0,
            "detail_operational_error_count": 0,
            "list_rejection_reason_counts": {},
        },
        "candidates": [],
        "operational_errors": [{"reason_code": reason_code}],
        "result_sha256": sha256_bytes(canonical_json_bytes(basis)),
    }


def discover_live(*, now: datetime | None = None) -> dict[str, Any]:
    observed_at = (now or utc_now()).astimezone(UTC)
    list_payload, list_raw = fetch_public_json(LIST_URL)

    def load_detail(slug: str) -> tuple[Any, bytes]:
        return fetch_public_json(DETAIL_URL_TEMPLATE.format(slug=slug))

    return build_state(list_payload, list_raw, load_detail, now=observed_at)


def atomic_write_json(path: Path, value: Any) -> None:
    parent = path.parent
    if not parent.is_dir():
        raise ScoutError("OUTPUT_PARENT_NOT_DIRECTORY")
    encoded = json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=True,
        indent=2,
        sort_keys=True,
    ).encode("utf-8") + b"\n"
    old_umask = os.umask(0o077)
    temporary_name: str | None = None
    try:
        file_descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=parent
        )
        try:
            os.fchmod(file_descriptor, 0o600)
            with os.fdopen(file_descriptor, "wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, path)
            temporary_name = None
            os.chmod(path, 0o600)
            directory_descriptor = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_descriptor)
            finally:
                os.close(directory_descriptor)
        finally:
            if temporary_name is not None:
                try:
                    os.unlink(temporary_name)
                except FileNotFoundError:
                    pass
    except OSError as error:
        raise ScoutError("ATOMIC_STATE_WRITE_FAILED") from error
    finally:
        os.umask(old_umask)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only deterministic Superteam large-bounty scout"
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    observed_at = utc_now()
    try:
        state = discover_live(now=observed_at)
    except ScoutError as error:
        state = build_failure_state(error.code, now=observed_at)
        try:
            atomic_write_json(args.output, state)
        except ScoutError as write_error:
            print(f"SUPERTEAM_LARGE_BOUNTY_SCOUT_FAILED:{write_error.code}", file=sys.stderr)
            return 1
        print(f"SUPERTEAM_LARGE_BOUNTY_SCOUT_FAILED:{error.code}", file=sys.stderr)
        return 1
    try:
        atomic_write_json(args.output, state)
    except ScoutError as error:
        print(f"SUPERTEAM_LARGE_BOUNTY_SCOUT_FAILED:{error.code}", file=sys.stderr)
        return 1
    if state["status"] != "ok":
        print("SUPERTEAM_LARGE_BOUNTY_SCOUT_FAILED:DETAIL_DISCOVERY_INCOMPLETE", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

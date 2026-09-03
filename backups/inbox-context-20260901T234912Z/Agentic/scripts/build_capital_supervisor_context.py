#!/usr/bin/env python3
"""Reduce the canonical capital context to one bounded, decision-only snapshot."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


DEFAULT_SOURCE = Path("/var/lib/agentic/capital_cycle_context.json")
DEFAULT_OUTPUT = Path("/var/lib/agentic/capital_supervisor_context.json")


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _unit_health(context: dict[str, Any]) -> tuple[dict[str, str], list[str]]:
    health = _dict(context.get("health"))
    states: dict[str, str] = {}
    problems: list[str] = []
    for group_name in ("services", "timers"):
        for name, raw in sorted(_dict(health.get(group_name)).items()):
            row = _dict(raw)
            active = str(row.get("active") or "unknown")
            sub = str(row.get("sub") or "unknown")
            result = str(row.get("result") or "unknown")
            states[str(name)] = f"{active}/{sub}/{result}"
            expected = active == "active" and result in {"success", "unknown"}
            if not expected:
                problems.append(f"{name}:{active}/{sub}/{result}")
    validator = _dict(health.get("financial_validator"))
    if str(validator.get("status") or "") != "valid":
        problems.append("financial_validator_not_valid")
    return states, problems


def _email_summary(context: dict[str, Any]) -> dict[str, Any]:
    email = _dict(context.get("email_collection_candidates"))
    guard = _dict(context.get("proposal_guard"))
    existing = {str(value).lower() for value in _list(guard.get("existing_bounty_keys"))}
    items: list[dict[str, Any]] = []
    new_targets = 0
    for raw in _list(email.get("items"))[:8]:
        row = _dict(raw)
        repo = str(row.get("repo") or "")
        target_number = row.get("target_number")
        target_type = str(row.get("target_type") or "")
        provider = str(row.get("provider") or "github")
        prefixes = [f"github|{repo}|{target_number}".lower(), f"{provider}|{repo}|{target_number}".lower()]
        already_mapped = any(any(key.startswith(prefix) for key in existing) for prefix in prefixes)
        if not already_mapped:
            new_targets += 1
        items.append(
            {
                "target_url": row.get("target_url"),
                "strict_state": row.get("strict_state"),
                "verified": bool(row.get("verified")),
                "already_in_ledger": already_mapped,
                "target_type": target_type,
            }
        )
    return {
        "count": int(email.get("count") or 0),
        "new_unmapped_target_count": new_targets,
        "items": items,
    }


def _payout_route_summary(context: dict[str, Any]) -> dict[str, Any]:
    payout = _dict(context.get("payout_routes"))
    summary = _dict(payout.get("summary"))
    routes: list[dict[str, Any]] = []
    for raw in _list(payout.get("routes"))[:8]:
        row = _dict(raw)
        route = {
                "route_id": row.get("route_id"),
                "asset": row.get("asset"),
                "network": row.get("network"),
                "status": row.get("status"),
                "route_complete_verified": row.get("route_complete_verified") is True,
                "execution_enabled": row.get("execution_enabled") is True,
                "expected_wise_net_verified": row.get("expected_wise_net_verified"),
                "mapped_wallet_received_amount": row.get("mapped_wallet_received_amount"),
                "reason_codes": _list(row.get("reason_codes"))[:6],
                "is_revenue": False,
                "is_settlement": False,
            }
        if route["asset"] == "RTC":
            quote = _dict(row.get("market_quote"))
            quote_ok = (
                quote.get("quote_ok") is True
                and quote.get("read_only") is True
                and quote.get("expiring") is True
                and quote.get("post_bridge_only") is True
            )
            route["market_quote"] = {
                "observed_at": quote.get("observed_at"),
                "venue": quote.get("venue"),
                "input_amount": quote.get("input_amount"),
                "intermediate_output": quote.get("intermediate_output"),
                "estimated_output": quote.get("estimated_output"),
                "first_leg_price_impact_pct": quote.get("first_leg_price_impact_pct"),
                "quote_ok": quote_ok,
                "expiring": True,
                "post_bridge_only": True,
                "native_rtc_to_wrtc_verified": quote.get("native_rtc_to_wrtc_verified") is True,
                "authorizes_execution": False,
            }
            bridge = _dict(row.get("bridge_request"))
            try:
                trusted_comments_seen = max(0, int(bridge.get("trusted_comments_seen") or 0))
            except (TypeError, ValueError):
                trusted_comments_seen = 0
            route["bridge_request"] = {
                "status": bridge.get("status") or "watcher_state_missing_pending",
                "issue_url": bridge.get("issue_url"),
                "trusted_comments_seen": trusted_comments_seen,
                "operator_gate_satisfied": False,
                "execution_authorized": False,
                "funds_moved": False,
            }
        routes.append(route)
    return {
        "status": payout.get("status"),
        "ranking_primary": "verified_expected_wise_net",
        "human_action_required": False,
        "route_pending_is_revenue": False,
        "route_pending_is_settlement": False,
        "route_count": int(summary.get("route_count") or 0),
        "complete_verified_count": int(summary.get("complete_verified") or 0),
        "route_pending_count": int(summary.get("route_pending") or 0),
        "candidates_with_verified_wise_net": int(
            summary.get("candidates_with_verified_wise_net") or 0
        ),
        "funds_moved": summary.get("funds_moved") is True,
        "routes": routes,
    }


def _large_bounty_summary(context: dict[str, Any]) -> dict[str, Any]:
    source = _dict(context.get("large_bounty_candidates"))
    items: list[dict[str, Any]] = []
    for raw in _list(source.get("items"))[:2]:
        row = _dict(raw)
        items.append(
            {
                "candidate_id": row.get("candidate_id"),
                "title": row.get("title"),
                "asset": row.get("asset"),
                "asset_exact_no_fiat_equivalence": True,
                "listed_face_value_unrealized": row.get("listed_face_value_unrealized"),
                "expected_wise_net_verified": row.get("expected_wise_net_verified"),
                "route_status": row.get("route_status"),
                "autonomy_qualified": row.get("autonomy_qualified") is True,
                "reason_codes": _list(row.get("reason_codes"))[:8],
                "source_urls": _list(row.get("source_urls"))[:1],
                "is_revenue": False,
                "is_settlement": False,
            }
        )
    return {
        "status": source.get("status"),
        "ranking_primary": "verified_expected_wise_net",
        "human_action_required": False,
        "asset_symbols_are_not_fiat_equivalence": True,
        "listed_face_value_is_revenue": False,
        "listed_face_value_is_settlement": False,
        "sources": _list(source.get("sources"))[:4],
        "raw_candidate_count": int(source.get("raw_candidate_count") or 0),
        "candidate_count": int(source.get("candidate_count") or 0),
        "overlap_duplicate_count": int(source.get("overlap_duplicate_count") or 0),
        "autonomy_qualified_count": int(source.get("autonomy_qualified_count") or 0),
        "verified_expected_wise_net_count": int(
            source.get("verified_expected_wise_net_count") or 0
        ),
        "items": items,
    }


def _bounty_priority_summary(context: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    raw_source = context.get("bounty_priority_queue")
    authoritative = isinstance(raw_source, dict)
    source = _dict(raw_source)
    current = source.get("status") == "ok" and source.get("fresh") is True

    def candidates(queue_name: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for raw in _list(source.get(queue_name))[:1]:
            row = _dict(raw)
            actionable = (
                current
                and queue_name == "action_queue"
                and row.get("actionable") is True
                and row.get("explicit_execution_contract") is True
                and row.get("is_revenue") is False
                and row.get("is_settlement") is False
                and row.get("funds_moved") is False
            )
            items.append(
                {
                    "queue": queue_name,
                    "stable_id": row.get("stable_id"),
                    "candidate_id": row.get("candidate_id"),
                    "source": row.get("source"),
                    "provider": row.get("provider"),
                    "title": row.get("title"),
                    "asset": row.get("asset"),
                    "network": row.get("network"),
                    "deadline": row.get("deadline"),
                    "listed_face_value_unrealized": row.get("listed_face_value_unrealized"),
                    "expected_wise_net_verified": row.get("expected_wise_net_verified"),
                    "payment_confidence_lcb_ppm": row.get("payment_confidence_lcb_ppm"),
                    "net_if_paid_verified": row.get("net_if_paid_verified"),
                    "time_to_wise_p90_seconds": row.get("time_to_wise_p90_seconds"),
                    "route_status": row.get("route_status"),
                    "reason_codes": _list(row.get("reason_codes"))[:8],
                    "actionable": actionable,
                    "is_revenue": False,
                    "is_settlement": False,
                    "funds_moved": False,
                }
            )
        return items

    action = candidates("action_queue")
    research = candidates("research_queue")
    monitor = candidates("monitor_only")
    selected_queue: str | None = None
    selected_candidate_id: str | None = None
    if action and action[0]["actionable"]:
        selected_queue = "action_queue"
        selected_candidate_id = action[0].get("stable_id") or action[0].get("candidate_id")
    elif current and research:
        selected_queue = "research_queue"
        selected_candidate_id = research[0].get("stable_id") or research[0].get("candidate_id")

    summary = _dict(source.get("summary"))
    return (
        {
            "status": source.get("status") or "unavailable",
            "fresh": current,
            "observed_at": source.get("observed_at"),
            "reason_codes": _list(source.get("reason_codes"))[:8],
            "precedence": ["action_queue", "research_queue", "monitor_only"],
            "monitor_only_is_actionable": False,
            "listed_face_value_is_revenue": False,
            "expected_wise_net_is_revenue": False,
            "counts": {
                "candidate": int(summary.get("candidate_count") or 0),
                "raw_action": int(summary.get("raw_action_count") or 0),
                "effective_action": int(summary.get("effective_action_count") or 0),
                "research": int(summary.get("research_count") or 0),
                "monitor_only": int(summary.get("monitor_only_count") or 0),
                "suppressed_action": int(summary.get("suppressed_action_count") or 0),
            },
            "top_action": action,
            "top_research": research,
            "top_monitor_only": monitor,
            "selected_queue": selected_queue,
            "selected_candidate_id": selected_candidate_id,
        },
        authoritative,
    )


def build(source: Path) -> dict[str, Any]:
    context = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(context, dict):
        raise ValueError("capital context must be an object")

    ledger = _dict(context.get("ledger"))
    realized = _dict(context.get("realized_revenue"))
    rustchain = _dict(context.get("rustchain"))
    telegram = _dict(context.get("telegram_unprocessed"))
    routing = _dict(context.get("routing"))
    units, health_problems = _unit_health(context)
    email = _email_summary(context)
    payout_routes = _payout_route_summary(context)
    large_bounties = _large_bounty_summary(context)
    bounty_priority, bounty_priority_authoritative = _bounty_priority_summary(context)
    if bounty_priority_authoritative:
        large_bounties = {
            "status": large_bounties.get("status"),
            "candidate_count": large_bounties.get("candidate_count"),
            "raw_candidate_count": large_bounties.get("raw_candidate_count"),
            "overlap_duplicate_count": large_bounties.get("overlap_duplicate_count"),
            "listed_face_value_is_revenue": False,
            "listed_face_value_is_settlement": False,
            "details_superseded_by": "bounty_priority_queue",
            "items": [],
        }

    provider_rows = []
    for raw in _list(ledger.get("provider_confirmed"))[:8]:
        row = _dict(raw)
        provider_rows.append(
            {
                "key": row.get("key"),
                "amount": row.get("amount"),
                "asset": row.get("asset"),
                "status": row.get("status"),
                "txid_present": bool(str(row.get("txid") or "").strip() or _list(row.get("txids"))),
                "blockers": _list(row.get("blockers"))[:8],
            }
        )

    wallet_received_rows = []
    for raw in _list(ledger.get("wallet_received"))[:8]:
        row = _dict(raw)
        wallet_received_rows.append(
            {
                "key": row.get("key"),
                "amount": row.get("amount"),
                "asset": row.get("asset"),
                "status": row.get("status"),
                "txid_present": bool(str(row.get("txid") or "").strip() or _list(row.get("txids"))),
                "blockers": _list(row.get("blockers"))[:8],
            }
        )

    realized_usd = float(realized.get("total_usd") or 0)
    telegram_count = int(telegram.get("count") or 0)
    actionable_reasons: list[str] = []
    if realized_usd > 0:
        actionable_reasons.append("reconciled_revenue_present")
    if wallet_received_rows:
        actionable_reasons.append("wallet_receipt_present")
    if email["new_unmapped_target_count"]:
        actionable_reasons.append("new_unmapped_email_target")
    if telegram_count:
        actionable_reasons.append("authorized_telegram_command_pending")
    if health_problems:
        actionable_reasons.append("runtime_health_problem")
    if any(
        row["route_complete_verified"] and row["execution_enabled"]
        for row in payout_routes["routes"]
    ):
        actionable_reasons.append("verified_executable_payout_route")
    if bounty_priority["selected_queue"] == "action_queue":
        actionable_reasons.append("highest_value_autonomous_bounty_ready")
    elif bounty_priority["selected_queue"] == "research_queue":
        actionable_reasons.append("highest_value_bounty_research_ready")
    elif not bounty_priority_authoritative and any(
        row["autonomy_qualified"] and row["expected_wise_net_verified"] is not None
        for row in large_bounties["items"]
    ):
        actionable_reasons.append("autonomous_large_bounty_with_verified_wise_net")

    output = {
        "schema_version": 1,
        "context_id": context.get("context_id"),
        "material_state_id": context.get("material_state_id"),
        "generated_at": context.get("generated_at"),
        "routing": {
            "model_alias": routing.get("model_alias"),
            "loopback_only": str(routing.get("base_url") or "").startswith("http://127.0.0.1:"),
        },
        "financial_truth": {
            "goal_usd_wise_settled": 20_000_000,
            "realized_usd": realized_usd,
            "realized_record_count": int(realized.get("record_count") or 0),
            "ledger_entry_count": int(ledger.get("entry_count") or 0),
            "ledger_status_counts": _dict(ledger.get("status_counts")),
            "provider_confirmed": provider_rows,
            "wallet_received": wallet_received_rows,
        },
        "rustchain": {
            "wallet_amount_rtc": _dict(rustchain.get("wallet")).get("amount_rtc"),
            "provider_confirmed": rustchain.get("provider_confirmed_total"),
            "wallet_received": rustchain.get("wallet_received_total"),
            "settled": rustchain.get("settled_total"),
            "unmapped_balance_rtc": rustchain.get("unmapped_balance_rtc"),
            "bybit_route": rustchain.get("bybit_route"),
            "wise_route": rustchain.get("wise_route"),
            "direct_transfer_performed": bool(rustchain.get("direct_transfer_performed")),
        },
        "payout_routes": payout_routes,
        "bounty_priority_queue": bounty_priority,
        "large_bounties": large_bounties,
        "email_signals": email,
        "telegram": {"authorized_unprocessed_count": telegram_count},
        "runtime": {"units": units, "problems": health_problems},
        "supervision": {
            "actionable_new_evidence": bool(actionable_reasons),
            "actionable_reasons": actionable_reasons,
            "human_action_required": False,
            "execution_owner": "deterministic_server_controllers",
            "communication_mode": "informational_only",
        },
    }
    return output


def atomic_write(path: Path, payload: dict[str, Any], max_bytes: int) -> None:
    encoded = (json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n").encode()
    if len(encoded) > max_bytes:
        raise ValueError(f"supervisor context exceeds {max_bytes} bytes: {len(encoded)}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    temporary.write_bytes(encoded)
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--max-bytes", type=int, default=8192)
    args = parser.parse_args()
    payload = build(args.source)
    atomic_write(args.output, payload, args.max_bytes)
    print(
        "CAPITAL_SUPERVISOR_CONTEXT_READY "
        f"path={args.output} bytes={args.output.stat().st_size} "
        f"id={payload.get('context_id')} "
        f"actionable={str(payload['supervision']['actionable_new_evidence']).lower()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

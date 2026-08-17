"""Wise-funded P2P via Bybit marketplace. Wise pays; Bybit only matches orders."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

import requests

from agentic.aro.config import AroConfig
from agentic.aro.finance import BASE_LIMIT, record_collect, snapshot
from agentic.aro.wallets import wise_funding_brl
from agentic.aro.store import append_jsonl, read_jsonl, utcnow
from agentic.env import bybit_credentials, mask_secrets

P2P_API = "https://api.bybit.com"
STATE_FILE = "p2p-state.json"
RECV_WINDOW = "5000"
FINISHED_STATUS = 50


def _strip(value: str | None) -> str:
    return (value or "").strip().strip('"').strip("'")


def _api_base() -> str:
    mode = _strip(os.getenv("BYBIT_MODE")).lower()
    if mode in {"test", "testnet"}:
        return "https://api-testnet.bybit.com"
    return P2P_API


def configured() -> bool:
    try:
        bybit_credentials()
        return True
    except RuntimeError:
        return False


def authorized(config: AroConfig) -> bool:
    flag = _strip(os.getenv("ARO_P2P_AUTHORIZED")).lower()
    return flag in {"1", "true", "yes", "on"} and config.commercial_outbound


def live_enabled() -> bool:
    return _strip(os.getenv("ARO_P2P_LIVE")).lower() in {"1", "true", "yes", "on"}


def _token() -> str:
    return _strip(os.getenv("ARO_P2P_TOKEN")) or "USDT"


def _currency() -> str:
    return _strip(os.getenv("ARO_P2P_CURRENCY")) or "BRL"


def _sign(secret: str, payload: str, timestamp: str, api_key: str) -> str:
    raw = f"{timestamp}{api_key}{RECV_WINDOW}{payload}"
    return hmac.new(secret.encode(), raw.encode(), hashlib.sha256).hexdigest()


def _request(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    api_key, secret = bybit_credentials()
    timestamp = str(int(time.time() * 1000))
    session = requests.Session()
    session.trust_env = False
    url = f"{_api_base()}{path}"
    try:
        if method.upper() == "POST":
            payload = json.dumps(body or {}, separators=(",", ":"), ensure_ascii=False)
            sign_payload = payload
            headers = {
                "X-BAPI-API-KEY": api_key,
                "X-BAPI-TIMESTAMP": timestamp,
                "X-BAPI-RECV-WINDOW": RECV_WINDOW,
                "X-BAPI-SIGN": _sign(secret, sign_payload, timestamp, api_key),
                "Content-Type": "application/json",
                "User-Agent": "Agentic-ARO/0.1",
            }
            response = session.post(url, data=payload, headers=headers, timeout=25)
        else:
            sign_payload = ""
            if "?" in path:
                sign_payload = path.split("?", 1)[1]
            headers = {
                "X-BAPI-API-KEY": api_key,
                "X-BAPI-TIMESTAMP": timestamp,
                "X-BAPI-RECV-WINDOW": RECV_WINDOW,
                "X-BAPI-SIGN": _sign(secret, sign_payload, timestamp, api_key),
                "Content-Type": "application/json",
                "User-Agent": "Agentic-ARO/0.1",
            }
            response = session.get(url, headers=headers, timeout=25)
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        return {"ok": False, "reason": type(exc).__name__, "detail": mask_secrets(str(exc))[:200]}
    ret_code = data.get("ret_code", data.get("retCode"))
    ok = ret_code in {0, "0", None} and response.status_code < 400
    if ret_code not in {0, "0", None}:
        ok = False
    return {
        "ok": ok,
        "ret_code": ret_code,
        "ret_msg": data.get("ret_msg") or data.get("retMsg") or "",
        "result": data.get("result") if isinstance(data.get("result"), (dict, list)) else {},
        "http": response.status_code,
    }


def status() -> dict[str, Any]:
    if not configured():
        return {"ok": False, "configured": False, "reason": "bybit_credentials_missing"}
    account = _request("POST", "/v5/p2p/user/personal/info", {})
    payments = _request("POST", "/v5/p2p/user/payment/list", {})
    balance = _request(
        "GET",
        "/v5/asset/transfer/query-account-coins-balance?accountType=FUND&coin=USDT",
    )
    return {
        "ok": bool(account.get("ok")),
        "configured": True,
        "authorized_env": _strip(os.getenv("ARO_P2P_AUTHORIZED")).lower() in {"1", "true", "yes", "on"},
        "live": live_enabled(),
        "token": _token(),
        "currency": _currency(),
        "account": account.get("result") or {},
        "payments_count": len((payments.get("result") or {}).get("list") or []),
        "balance": balance.get("result") or {},
        "ret_msg": account.get("ret_msg") or "",
    }


def scan_online(*, side: str, token: str | None = None, currency: str | None = None, size: int = 10) -> dict[str, Any]:
    """side: 0=buy ads (makers buy token), 1=sell ads (makers sell token)."""
    body = {
        "tokenId": token or _token(),
        "currencyId": currency or _currency(),
        "side": side,
        "page": "1",
        "size": str(min(max(size, 1), 50)),
    }
    payload = _request("POST", "/v5/p2p/item/online", body)
    items = (payload.get("result") or {}).get("items") or []
    ranked = sorted(
        [item for item in items if isinstance(item, dict)],
        key=lambda row: float(row.get("price") or 0),
        reverse=side == "1",
    )
    return {
        "ok": payload.get("ok"),
        "side": side,
        "count": len(ranked),
        "top": ranked[:5],
        "ret_msg": payload.get("ret_msg") or "",
    }


def list_my_ads(*, side: str | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"page": "1", "size": "20"}
    if side is not None:
        body["side"] = side
    payload = _request("POST", "/v5/p2p/item/personal/list", body)
    items = (payload.get("result") or {}).get("items") or []
    return {"ok": payload.get("ok"), "items": items, "ret_msg": payload.get("ret_msg") or ""}


def list_pending_orders() -> dict[str, Any]:
    payload = _request("POST", "/v5/p2p/order/pending/simplifyList", {"page": 1, "size": 30})
    items = (payload.get("result") or {}).get("items") or []
    return {"ok": payload.get("ok"), "items": items, "ret_msg": payload.get("ret_msg") or ""}


def list_orders(*, page: int = 1, size: int = 30) -> dict[str, Any]:
    payload = _request(
        "POST",
        "/v5/p2p/order/simplifyList",
        {"page": page, "size": min(size, 30)},
    )
    items = (payload.get("result") or {}).get("items") or []
    return {"ok": payload.get("ok"), "items": items, "ret_msg": payload.get("ret_msg") or ""}


def _load_state(root: Path) -> dict[str, Any]:
    path = Path(root) / "data" / "aro" / STATE_FILE
    if not path.is_file():
        return {"synced_orders": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"synced_orders": []}
    return data if isinstance(data, dict) else {"synced_orders": []}


def _save_state(root: Path, state: dict[str, Any]) -> None:
    path = Path(root) / "data" / "aro" / STATE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = utcnow()
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _dec(value: Any) -> Decimal:
    try:
        return Decimal(str(value or "0").replace(",", ".")).quantize(Decimal("0.01"))
    except Exception:
        return Decimal("0.00")


def sync_ledger(root: Path, config: AroConfig) -> dict[str, Any]:
    """Record finished P2P orders into the ARO ledger (idempotent)."""
    if not authorized(config):
        return {"ok": False, "action": "blocked", "reason": "p2p_not_authorized"}
    orders = list_orders(page=1, size=30)
    if not orders.get("ok"):
        return {"ok": False, "action": "sync_failed", "reason": orders.get("ret_msg") or "orders_unavailable"}
    state = _load_state(root)
    synced = set(str(x) for x in state.get("synced_orders") or [])
    recorded: list[dict[str, Any]] = []
    for row in orders.get("items") or []:
        if not isinstance(row, dict):
            continue
        if int(row.get("status") or 0) != FINISHED_STATUS:
            continue
        order_id = str(row.get("id") or "")
        if not order_id or order_id in synced:
            continue
        amount_brl = _dec(row.get("amount") or "0")
        side = int(row.get("side") or 0)
        if amount_brl <= 0:
            continue
        if side == 1:
            entry = record_collect(
                root,
                amount_brl,
                contract_id="",
                reference=f"p2p_order:{order_id}",
                source="bybit_p2p_sell",
            )
            recorded.append({"order_id": order_id, "kind": "sell", "amount_brl": f"{amount_brl:.2f}"})
        else:
            from agentic.aro.finance import record_expense

            entry = record_expense(
                root,
                amount_brl,
                reference=f"p2p_order:{order_id}",
                source="bybit_p2p_buy",
            )
            recorded.append({"order_id": order_id, "kind": "buy", "amount_brl": f"{amount_brl:.2f}"})
        synced.add(order_id)
        append_jsonl(
            root,
            "journal.jsonl",
            {"kind": "p2p_sync", "order_id": order_id, "side": side, "hash": entry.get("hash")},
        )
    state["synced_orders"] = sorted(synced)[-500:]
    _save_state(root, state)
    return {"ok": True, "action": "sync_ledger", "recorded": recorded, "synced_total": len(synced)}


def post_ad(
    root: Path,
    config: AroConfig,
    *,
    side: str,
    price: str,
    quantity: str,
    min_amount: str,
    max_amount: str,
    payment_ids: list[str],
    remark: str = "ARO P2P",
) -> dict[str, Any]:
    """Post a P2P ad. side 0=buy token, 1=sell token."""
    if not authorized(config):
        return {"ok": False, "reason": "p2p_not_authorized"}
    if not live_enabled():
        return {
            "ok": True,
            "action": "dry_run",
            "would_post": {
                "side": side,
                "tokenId": _token(),
                "currencyId": _currency(),
                "price": price,
                "quantity": quantity,
                "minAmount": min_amount,
                "maxAmount": max_amount,
                "paymentIds": payment_ids,
            },
            "note": "ARO_P2P_LIVE=0 — defina 1 para publicar anúncio real",
        }
    try:
        base = Decimal(str(config.base_limit_brl or "50"))
    except Exception:
        base = BASE_LIMIT
    fin = snapshot(root, payout_dest_ok=config.money_rail_ready, base=base, channel=config.payout_channel)
    limits = fin.get("limits") or {}
    max_brl = _dec(max_amount)
    if side == "0":
        funding = wise_funding_brl(config)
        available = _dec(funding.get("available_brl") or "0")
        if max_brl > available:
            return {
                "ok": False,
                "reason": "above_wise_p2p_funding",
                "wise_available_brl": funding.get("available_brl"),
                "requested_max_brl": str(max_brl),
            }
        if max_brl > _dec(limits.get("max_single_expense") or "0"):
            return {
                "ok": False,
                "reason": "above_max_single_expense",
                "limit": limits.get("max_single_expense"),
            }
    body = {
        "tokenId": _token(),
        "currencyId": _currency(),
        "side": side,
        "priceType": "0",
        "premium": "",
        "price": price,
        "minAmount": min_amount,
        "maxAmount": max_amount,
        "paymentIds": payment_ids[:5],
        "remark": remark[:900],
        "tradingPreferenceSet": {"isKyc": "1"},
        "quantity": quantity,
        "paymentPeriod": "15",
        "itemType": "ORIGIN",
    }
    payload = _request("POST", "/v5/p2p/item/create", body)
    if payload.get("ok"):
        append_jsonl(
            root,
            "journal.jsonl",
            {
                "kind": "p2p_ad",
                "side": side,
                "item_id": (payload.get("result") or {}).get("itemId"),
            },
        )
    return {
        "ok": payload.get("ok"),
        "action": "post_ad",
        "side": side,
        "result": payload.get("result") or {},
        "ret_msg": payload.get("ret_msg") or "",
    }


def run_p2p(root: Path, config: AroConfig) -> dict[str, Any]:
    """Scan market, sync ledger, surface pending orders. No spot trading."""
    if config.stop_all:
        return {"ok": False, "action": "paused", "reason": "STOP_ALL_OPERATIONS"}
    if not authorized(config):
        return {"ok": False, "action": "blocked", "reason": "ARO_P2P_AUTHORIZED=0"}
    if not configured():
        return {"ok": False, "action": "blocked", "reason": "bybit_credentials_missing"}
    rail = status()
    funding = wise_funding_brl(config)
    buy_market = scan_online(side="1")
    sell_market = scan_online(side="0")
    my_ads = list_my_ads()
    pending = list_pending_orders()
    sync = sync_ledger(root, config)
    return {
        "ok": True,
        "action": "p2p",
        "live": live_enabled(),
        "token": _token(),
        "currency": _currency(),
        "role": "bybit_marketplace_only",
        "wise_funding": funding,
        "rail": {
            "ok": rail.get("ok"),
            "payments_count": rail.get("payments_count"),
            "ret_msg": rail.get("ret_msg") or "",
        },
        "market": {
            "sellers": buy_market.get("top") or [],
            "buyers": sell_market.get("top") or [],
        },
        "my_ads": len(my_ads.get("items") or []),
        "pending_orders": len(pending.get("items") or []),
        "pending": pending.get("items") or [],
        "sync": sync,
        "next": _next_p2p(pending.get("items") or [], sync, funding, live_enabled()),
    }


def _next_p2p(
    pending: list[dict[str, Any]],
    sync: dict[str, Any],
    funding: dict[str, Any],
    live: bool,
) -> str:
    if pending:
        return f"{len(pending)} ordem(ns) P2P pendente(s) — pagar via Wise PIX se comprador"
    if sync.get("recorded"):
        return f"sync: {len(sync['recorded'])} ordem(ns) no ledger"
    avail = funding.get("available_brl") or "0"
    if not live:
        return f"Wise disponível R$ {avail} para P2P; ARO_P2P_LIVE=0 (dry-run)"
    return f"usar até R$ {avail} da Wise em compra P2P; reinvestir capital"

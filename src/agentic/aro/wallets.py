"""Receive wallets and Wise-funded P2P. Bybit is marketplace only — not client receive."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from agentic.aro.config import AroConfig
from agentic.aro.store import append_jsonl, list_named, upsert_named

WALLET_ENV = Path("/root/.automaton/aro-wallet.env")
WALLETS_FILE = "receive-wallets.json"


def _strip(value: str | None) -> str:
    return (value or "").strip().strip('"').strip("'")


def _load_wallet_env() -> dict[str, str]:
    data: dict[str, str] = {}
    if not WALLET_ENV.is_file():
        return data
    for raw in WALLET_ENV.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        data[key.strip()] = val.strip()
    return data


def _save_wallet_env(values: dict[str, str]) -> None:
    existing = _load_wallet_env()
    existing.update({k: v for k, v in values.items() if v})
    lines = ["# ARO receive wallet — mode 0600. Never commit."]
    for key in sorted(existing):
        lines.append(f"{key}={existing[key]}")
    WALLET_ENV.write_text("\n".join(lines) + "\n", encoding="utf-8")
    WALLET_ENV.chmod(0o600)


def _may_create(config: AroConfig) -> bool:
    flag = _strip(os.getenv("ARO_MAY_CREATE_RECEIVE_WALLET")).lower()
    return flag in {"1", "true", "yes", "on"} or config.may_open_receive_accounts


def ensure_crypto_wallet(*, chain: str = "polygon", currency: str = "USDT") -> dict[str, Any]:
    """Create or load EVM receive wallet. Private key stays in aro-wallet.env."""
    env = _load_wallet_env()
    address = _strip(env.get("ARO_RECEIVE_ADDRESS"))
    if address:
        return {
            "ok": True,
            "created": False,
            "address": address,
            "chain": _strip(env.get("ARO_RECEIVE_CHAIN")) or chain,
            "currency": _strip(env.get("ARO_RECEIVE_CURRENCY")) or currency,
        }
    try:
        from eth_account import Account

        acct = Account.create()
        address = acct.address
        priv = acct.key.hex()
    except ImportError:
        return {"ok": False, "reason": "eth_account_missing"}
    _save_wallet_env(
        {
            "ARO_RECEIVE_ADDRESS": address,
            "ARO_RECEIVE_PRIVATE_KEY": priv if priv.startswith("0x") else f"0x{priv}",
            "ARO_RECEIVE_CHAIN": chain,
            "ARO_RECEIVE_CURRENCY": currency,
        }
    )
    return {"ok": True, "created": True, "address": address, "chain": chain, "currency": currency}


def ensure_receive_rails(root, config: AroConfig) -> dict[str, Any]:
    """Wise = fiat receive + P2P funding. Crypto wallet for client USDT. Not Bybit."""
    from agentic.aro import wise as wise_mod

    rails: list[dict[str, Any]] = []
    wise = wise_mod.status() if config.wise_configured else {"ok": False}
    if wise.get("ok"):
        rails.append(
            {
                "rail_id": "wise_brl",
                "kind": "wise",
                "label": "Wise BRL (PIX/TED)",
                "address": "",
                "chain": "",
                "currency": "BRL",
                "primary": True,
                "brl_balance": wise.get("brl_balance"),
                "receive_ready": wise.get("receive_ready"),
                "role": "client_receive_and_p2p_funding",
            }
        )
    crypto: dict[str, Any] = {"ok": False}
    if _may_create(config):
        crypto = ensure_crypto_wallet(
            chain=_strip(os.getenv("ARO_RECEIVE_CHAIN")) or "polygon",
            currency=_strip(os.getenv("ARO_RECEIVE_CURRENCY")) or "USDT",
        )
        if crypto.get("ok"):
            rails.append(
                {
                    "rail_id": "crypto_usdt",
                    "kind": "crypto_wallet",
                    "label": f"USDT ({crypto.get('chain')})",
                    "address": crypto.get("address"),
                    "chain": crypto.get("chain"),
                    "currency": crypto.get("currency"),
                    "primary": False,
                    "role": "client_receive_crypto",
                    "note": "Endereço público; chave privada só em aro-wallet.env",
                }
            )
    for row in rails:
        upsert_named(root, WALLETS_FILE, row, key="rail_id")
    append_jsonl(
        root,
        "journal.jsonl",
        {
            "kind": "receive_rails",
            "rails": [r.get("rail_id") for r in rails],
            "crypto_created": crypto.get("created"),
        },
    )
    return {"ok": True, "rails": rails, "wise_brl": wise.get("brl_balance"), "crypto": crypto}


def public_receive_catalog(root) -> list[dict[str, Any]]:
    """Safe payment options for catalog (no private keys, truncated crypto address)."""
    from agentic.aro import wise as wise_mod

    out: list[dict[str, Any]] = []
    for item in wise_mod.receive_catalog():
        out.append({**item, "rail": "wise", "primary": True})
    for row in list_named(root, WALLETS_FILE):
        if str(row.get("kind")) != "crypto_wallet":
            continue
        addr = str(row.get("address") or "")
        if not addr:
            continue
        out.append(
            {
                "rail": "crypto_wallet",
                "currency": row.get("currency") or "USDT",
                "chain": row.get("chain") or "polygon",
                "title": row.get("label") or "USDT wallet",
                "address_hint": addr[:6] + "…" + addr[-4:] if len(addr) > 12 else addr,
                "methods": ["on_chain"],
                "note": "Confirme rede e endereço completo por e-mail após contrato.",
                "primary": False,
            }
        )
    return out


def wise_funding_brl(config: AroConfig) -> dict[str, Any]:
    """BRL on Wise available for P2P buys (operating float)."""
    from decimal import Decimal

    from agentic.aro import wise as wise_mod

    if not config.wise_configured:
        return {"ok": False, "reason": "wise_not_configured", "available_brl": "0.00"}
    wise = wise_mod.status()
    if not wise.get("ok"):
        return {"ok": False, "reason": wise.get("reason") or "wise_unavailable", "available_brl": "0.00"}
    reserve = _strip(os.getenv("ARO_WISE_P2P_RESERVE_BRL")) or "10"
    balance = Decimal(str(wise.get("brl_balance") or "0"))
    floor = Decimal(reserve)
    available = max(balance - floor, Decimal("0"))
    return {
        "ok": True,
        "wise_brl": f"{balance.quantize(Decimal('0.01')):.2f}",
        "reserve_brl": f"{floor.quantize(Decimal('0.01')):.2f}",
        "available_brl": f"{available.quantize(Decimal('0.01')):.2f}",
        "note": "Compras P2P pagam PIX/TED da Wise; Bybit só executa a ordem.",
    }

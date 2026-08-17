"""Owner-authorized operating policy — licit revenue in Brasil only."""

from __future__ import annotations

import os
from typing import Any

from agentic.aro.config import AroConfig
from agentic.aro.constitution import JURISDICTION


def _strip(value: str | None) -> str:
    return (value or "").strip().strip('"').strip("'")


def full_autonomy_authorized() -> bool:
    return _strip(os.getenv("ARO_FULL_AUTONOMY")).lower() in {"1", "true", "yes", "on"}


def operating_policy(config: AroConfig) -> dict[str, Any]:
    """Hard limits stay in ARO.md; this reflects owner authorization scope."""
    return {
        "jurisdiction": JURISDICTION,
        "licit_revenue_only": True,
        "full_autonomy": full_autonomy_authorized(),
        "commercial_outbound": config.commercial_outbound,
        "may_open_receive_accounts": config.may_open_receive_accounts,
        "p2p_authorized": config.p2p_authorized,
        "forbidden": [
            "ilegal ou evasão fiscal",
            "impersonar pessoa física quando proibido",
            "spam ou contacto comercial não autorizado",
            "contornar CAPTCHA/antibot",
            "spot trading especulativo (AGENTIC_LIVE_TRADE)",
            "inventar clientes ou receita",
        ],
        "required": [
            "divulgar automação quando lei/plataforma exigir",
            "receita licita declarável no Brasil",
            "OWNER_SHARE_RATE 20% imutável + milestone R$ 1000",
            "reinvestir ~80% para crescer capital",
        ],
        "owner_mission": "20% lucro semanal; reinvestir resto; aos R$ 1000 metade ao owner",
    }

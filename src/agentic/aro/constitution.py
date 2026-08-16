"""ARO constitution — immutable machine checks. Human text lives in ARO.md."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

VERSION = "1.0"
OWNER_SHARE_RATE = 0.20
OWNER_SHARE_BASE = "NET_COLLECTED_CASH"
PAYOUT_INTERVAL = "WEEKLY"
JURISDICTION = "Brasil"
BASE_CURRENCY = "BRL"
STOP_COMMAND = "STOP_ALL_OPERATIONS"
STOP_FILENAME = ".agentic-aro.stop"

ARO_FORBIDS_SPECULATIVE_TRADING = True

INVARIANTS = {
    "version": VERSION,
    "owner_share_rate": OWNER_SHARE_RATE,
    "owner_share_base": OWNER_SHARE_BASE,
    "payout_interval": PAYOUT_INTERVAL,
    "jurisdiction": JURISDICTION,
    "base_currency": BASE_CURRENCY,
    "stop_command": STOP_COMMAND,
    "live_trade_forbidden": True,
    "loans_forbidden": True,
    "outbound_requires_authorized_accounts": True,
    "cannot_edit_payout_destination": True,
}

PRIORITIES = (
    "legalidade",
    "nao_prejudicar",
    "proteger_credenciais",
    "obrigacoes_cumpriveis",
    "solvencia_reputacao",
    "entregas_corretas",
    "receber_valor_devido",
    "lucro_liquido_sustentavel",
    "receita_recorrente",
    "distribuir_proprietario",
    "aprender",
)


def invariants_hash() -> str:
    blob = json.dumps(INVARIANTS, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def constitution_path(root: Path) -> Path:
    return Path(root) / "ARO.md"


def required_markers() -> tuple[str, ...]:
    return (
        "AUTONOMOUS REVENUE OPERATOR",
        "OWNER_SHARE_RATE = 0.20",
        STOP_COMMAND,
        "Nunca utilize empréstimos",
        "Não faça spam",
    )


def constitution_intact(root: Path) -> tuple[bool, str]:
    path = constitution_path(root)
    if not path.is_file():
        return False, "ARO.md ausente"
    text = path.read_text(encoding="utf-8")
    missing = [item for item in required_markers() if item not in text]
    if missing:
        return False, "marcadores ausentes: " + ", ".join(missing)
    return True, invariants_hash()


PROTECTED_PATHS = frozenset({"ARO.md", "src/agentic/aro/constitution.py"})


def patch_weakens_constitution(rel: str, text: str) -> str | None:
    path = (rel or "").replace("\\", "/").lstrip("./")
    if path not in PROTECTED_PATHS:
        return None
    if path == "ARO.md":
        missing = [item for item in required_markers() if item not in (text or "")]
        if missing:
            return "constituição enfraquecida: " + ", ".join(missing)
        return None
    if "OWNER_SHARE_RATE = 0.20" not in (text or ""):
        return "OWNER_SHARE_RATE imutável"
    if "live_trade_forbidden" not in (text or "") or STOP_COMMAND not in (text or ""):
        return "invariantes ARO removidos"
    return None

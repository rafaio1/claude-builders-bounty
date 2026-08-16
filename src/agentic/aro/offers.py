"""Three initial low-risk productized offers. No invented clients or testimonials."""

from __future__ import annotations

from typing import Any

from agentic.aro.config import AroConfig
from agentic.aro.store import list_named, upsert_named

OFFERS: tuple[dict[str, Any], ...] = (
    {
        "id": "offer-bugfix-api",
        "title": "Corrijo um bug reproduzível em API Python/Node",
        "scope": "Reproduzir o defeito, patch pequeno, testes e instrução de rollback.",
        "out_of_scope": ["exploração ofensiva", "acesso a produção sem autorização", "reescritas amplas"],
        "acceptance": ["teste que falhava passa", "diff revisado", "sem secrets no commit"],
        "delivery_days": 3,
        "theme": "bugfix",
    },
    {
        "id": "offer-docker-deploy",
        "title": "Dockerizo e implanto sua aplicação em Linux",
        "scope": "Dockerfile, compose ou unit systemd, healthcheck e notas de operação.",
        "out_of_scope": ["migrar dados de produção sem backup", "expor painéis sem autenticação"],
        "acceptance": ["container sobe localmente ou no servidor autorizado", "instruções testadas"],
        "delivery_days": 4,
        "theme": "deploy",
    },
    {
        "id": "offer-ghostcli-agent",
        "title": "Configuro um agente de IA (GhostCLI) no seu servidor",
        "scope": "CLI apontada à GhostCLI, Playwright headless e kill switches documentados.",
        "out_of_scope": ["usar a chave do contratante em outro cliente", "ligar trade ou pagamentos"],
        "acceptance": ["comando de status responde", "segredos fora do git"],
        "delivery_days": 2,
        "theme": "agents",
    },
)


def seed_offers(root, config: AroConfig) -> list[dict[str, Any]]:
    existing = {str(item.get("id")) for item in list_named(root, "offers.json")}
    seeded: list[dict[str, Any]] = []
    for raw in OFFERS:
        item = dict(raw)
        item["currency"] = config.base_currency
        item["price_floor"] = config.price_floor_brl
        item["status"] = "draft"
        item["authorized_to_publish"] = False
        if item["id"] not in existing:
            upsert_named(root, "offers.json", item)
            seeded.append(item)
        else:
            seeded.append(item)
    return list_named(root, "offers.json")

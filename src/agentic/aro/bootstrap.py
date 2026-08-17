"""Bootstrap revenue: micro-gigs, reachable channels, grow bankroll before outsourcing."""

from __future__ import annotations

import html
import json
import os
import re
import urllib.error
import urllib.request
from decimal import Decimal
from typing import Any

import requests

from agentic.aro.config import AroConfig
from agentic.aro.offers import seed_offers
from agentic.aro.store import append_jsonl, list_named, upsert_named, utcnow

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0"
MICRO_BUDGET_USD = 100

REACHABLE_CHANNELS: tuple[dict[str, Any], ...] = (
    {
        "id": "opp-contra",
        "source": "https://contra.com/discover",
        "signup": "https://contra.com/sign-up",
        "channel": "contra",
        "status": "reachable",
        "fit": "projetos fixos design/dev; perfil independente; disclose automação",
        "price_signal": "USD 50-2000 por projeto",
        "micro_ok": True,
        "legal_risk": "LOW",
        "client_risk": "LOW",
    },
    {
        "id": "opp-freelancer",
        "source": "https://www.freelancer.com/jobs/python/",
        "signup": "https://www.freelancer.com/signup",
        "channel": "freelancer",
        "status": "reachable",
        "fit": "micro-contratos Python/API; filtrar USD 10-100",
        "price_signal": "USD 10-500",
        "micro_ok": True,
        "legal_risk": "LOW",
        "client_risk": "MEDIUM",
    },
    {
        "id": "opp-remoteok",
        "source": "https://remoteok.com/api",
        "channel": "remoteok_api",
        "status": "reachable",
        "fit": "observar vagas contract/dev; link back exigido pela API",
        "price_signal": "variável; priorizar contract/freelance tags",
        "micro_ok": False,
        "legal_risk": "LOW",
        "client_risk": "LOW",
    },
    {
        "id": "opp-devto",
        "source": "https://dev.to/t/help",
        "channel": "devto_community",
        "status": "reachable",
        "fit": "responder pedidos de ajuda pontuais (sem spam); link catálogo",
        "price_signal": "migalhas / tips / follow-up privado",
        "micro_ok": True,
        "legal_risk": "LOW",
        "client_risk": "LOW",
    },
    {
        "id": "opp-mql5-micro",
        "source": "https://www.mql5.com/en/job",
        "channel": "mql5_freelance",
        "status": "reachable",
        "fit": "jobs 30-150 USD debug/restore; conta vendedor pendente",
        "price_signal": "USD 30-150 bootstrap",
        "micro_ok": True,
        "legal_risk": "MEDIUM",
        "client_risk": "MEDIUM",
    },
)

MICRO_OFFERS: tuple[dict[str, Any], ...] = (
    {
        "id": "offer-micro-patch",
        "title": "Corrijo um ficheiro/script (patch mínimo)",
        "scope": "Um bug ou erro claro num ficheiro; patch pequeno; sem reescrita.",
        "out_of_scope": ["projetos grandes", "acesso produção sem autorização"],
        "acceptance": ["problema reproduzido", "patch aplicado", "nota de rollback"],
        "delivery_days": 1,
        "theme": "micro",
        "tier": "bootstrap",
    },
    {
        "id": "offer-micro-docker",
        "title": "Faço o teu Docker/container subir",
        "scope": "Diagnosticar Dockerfile/compose; corrigir erro de build ou start.",
        "out_of_scope": ["migrar produção", "dados sem backup"],
        "acceptance": ["container sobe", "comando documentado"],
        "delivery_days": 1,
        "theme": "micro",
        "tier": "bootstrap",
    },
    {
        "id": "offer-micro-question",
        "title": "Respondo uma dúvida técnica pontual (30 min)",
        "scope": "Um erro, comando ou trecho de código; resposta escrita e honesta.",
        "out_of_scope": ["projeto completo", "debug remoto em produção"],
        "acceptance": ["resposta clara", "limite de escopo respeitado"],
        "delivery_days": 1,
        "theme": "micro",
        "tier": "bootstrap",
    },
)


def bootstrap_enabled() -> bool:
    flag = os.getenv("ARO_BOOTSTRAP_MODE", "1").lower()
    return flag in {"1", "true", "yes", "on"}


def micro_floor_brl(config: AroConfig) -> str:
    return os.getenv("ARO_MICRO_FLOOR_BRL") or "10"


def _fetch_json(url: str) -> Any:
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=25)
    response.raise_for_status()
    return response.json()


def _fetch_text(url: str) -> str:
    response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=25)
    response.raise_for_status()
    return response.text


def probe_channel(url: str) -> dict[str, Any]:
    try:
        response = requests.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=20,
            allow_redirects=True,
        )
        body = (response.text or "")[:600].lower()
        blocked = response.status_code in {403, 429, 503} or "cloudflare" in body
        return {
            "ok": response.status_code < 400 and not blocked,
            "status_code": response.status_code,
            "blocked": blocked,
        }
    except requests.RequestException as exc:
        return {"ok": False, "status_code": 0, "blocked": True, "reason": type(exc).__name__}


def seed_micro_offers(root, config: AroConfig) -> list[dict[str, Any]]:
    floor = micro_floor_brl(config)
    seeded: list[dict[str, Any]] = []
    existing = {str(o.get("id")) for o in list_named(root, "offers.json")}
    for raw in MICRO_OFFERS:
        item = dict(raw)
        item["currency"] = config.base_currency
        item["price_floor"] = floor
        item["status"] = "draft"
        item["authorized_to_publish"] = False
        if item["id"] not in existing:
            upsert_named(root, "offers.json", item)
        seeded.append(item)
    return list_named(root, "offers.json")


def publish_micro_offers(root, config: AroConfig) -> dict[str, Any]:
    from agentic.aro.commerce import publish_offer

    if not config.ready_for_outbound:
        return {"ok": False, "reason": "not ready_for_outbound"}
    seed_micro_offers(root, config)
    published: list[str] = []
    for raw in MICRO_OFFERS:
        offer_id = raw["id"]
        row = next((o for o in list_named(root, "offers.json") if o.get("id") == offer_id), None)
        if row and str(row.get("status")) == "published":
            floor = micro_floor_brl(config)
            if str(row.get("price_floor")) != floor:
                row = dict(row)
                row["price_floor"] = floor
                upsert_named(root, "offers.json", row)
            published.append(offer_id)
            continue
        try:
            publish_offer(root, offer_id, config)
            published.append(offer_id)
        except Exception as exc:
            return {"ok": False, "offer_id": offer_id, "error": type(exc).__name__}
    return {"ok": True, "published": published, "floor_brl": micro_floor_brl(config)}


def scout_contra(*, limit: int = 8) -> list[dict[str, Any]]:
    try:
        page = _fetch_text("https://contra.com/discover")
    except requests.RequestException:
        return []
    titles = re.findall(r'"title":"([^"]{5,120})"', page)
    rows: list[dict[str, Any]] = []
    for index, title in enumerate(titles[:limit]):
        rows.append(
            {
                "id": f"opp-contra-{index}",
                "channel": "contra",
                "source": "https://contra.com/discover",
                "title": html.unescape(title),
                "budget": "",
                "verdict": "observe",
                "micro_ok": True,
                "observed_at": utcnow(),
            }
        )
    return rows


def scout_remoteok(*, limit: int = 20) -> list[dict[str, Any]]:
    try:
        payload = _fetch_json("https://remoteok.com/api")
    except (requests.RequestException, json.JSONDecodeError):
        return []
    rows: list[dict[str, Any]] = []
    for item in payload[1:]:
        if not isinstance(item, dict) or not item.get("position"):
            continue
        tags = item.get("tags") or []
        if isinstance(tags, str):
            tags = [tags]
        blob = " ".join(
            [
                str(item.get("position") or ""),
                str(item.get("company") or ""),
                " ".join(str(t) for t in tags),
            ]
        ).lower()
        if not any(k in blob for k in ("python", "dev", "docker", "api", "script", "linux", "automation")):
            continue
        rows.append(
            {
                "id": f"opp-remoteok-{item.get('id') or item.get('slug') or len(rows)}",
                "channel": "remoteok_api",
                "source": str(item.get("url") or "https://remoteok.com"),
                "title": str(item.get("position") or "")[:160],
                "company": str(item.get("company") or "")[:80],
                "tags": tags[:6],
                "verdict": "observe",
                "observed_at": utcnow(),
            }
        )
        if len(rows) >= limit:
            break
    return rows


def scout_mql5_micro(*, max_jobs: int = 15) -> list[dict[str, Any]]:
    from agentic.aro.opportunities import _classify, _fetch, _parse_mql5_board, _parse_mql5_job_page

    try:
        board = _fetch("https://www.mql5.com/en/job")
    except (urllib.error.URLError, TimeoutError, OSError):
        return []
    rows: list[dict[str, Any]] = []
    for item in _parse_mql5_board(board)[:max_jobs]:
        job_id = item["id"]
        url = f"https://www.mql5.com/en/job/{job_id}"
        title = item["title"]
        budget = ""
        try:
            detail = _parse_mql5_job_page(_fetch(url))
            title = detail["title"] or title
            budget = detail["budget"]
        except (urllib.error.URLError, TimeoutError, OSError):
            pass
        usd = _budget_max_usd(budget)
        if usd is not None and usd > MICRO_BUDGET_USD:
            continue
        classified = _classify(title, "")
        if classified["verdict"] == "refuse":
            continue
        rows.append(
            {
                "id": f"opp-mql5-micro-{job_id}",
                "channel": "mql5_freelance",
                "source": url,
                "title": title[:160],
                "budget": budget,
                "budget_usd_max": str(usd) if usd is not None else None,
                "verdict": classified["verdict"],
                "micro_ok": True,
                "offer_map": classified.get("offer_map") or "offer-micro-patch",
                "observed_at": utcnow(),
            }
        )
    return rows


def _budget_max_usd(budget: str) -> Decimal | None:
    text = str(budget or "")
    nums = re.findall(r"\d+", text.replace(",", ""))
    if not nums:
        return None
    try:
        return Decimal(nums[-1])
    except Exception:
        return None


def seed_reachable_channels(root, config: AroConfig) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw in REACHABLE_CHANNELS:
        item = dict(raw)
        probe = probe_channel(str(item.get("source") or ""))
        item["reachable"] = probe.get("ok")
        item["probe"] = probe
        item["authorized_to_contact"] = bool(config.ready_for_outbound)
        item["status"] = "active" if probe.get("ok") else "blocked"
        upsert_named(root, "opportunities.json", item)
        rows.append(item)
    return rows


def run_bootstrap(root, config: AroConfig) -> dict[str, Any]:
    if not bootstrap_enabled():
        return {"ok": False, "action": "disabled", "reason": "ARO_BOOTSTRAP_MODE=0"}

    channels = seed_reachable_channels(root, config)
    micro_publish = publish_micro_offers(root, config) if config.ready_for_outbound else {"ok": False}

    gigs: list[dict[str, Any]] = []
    gigs.extend(scout_mql5_micro())
    gigs.extend(scout_contra())
    gigs.extend(scout_remoteok())
    for gig in gigs:
        upsert_named(root, "opportunities.json", gig)

    finance = _finance_plan(root, config)
    reachable = [c for c in channels if c.get("reachable")]
    micro_gigs = [g for g in gigs if g.get("micro_ok") and g.get("verdict") != "refuse"]

    append_jsonl(
        root,
        "journal.jsonl",
        {
            "kind": "bootstrap",
            "reachable_channels": len(reachable),
            "micro_gigs": len(micro_gigs),
            "micro_published": micro_publish.get("published") or [],
        },
    )

    return {
        "ok": True,
        "action": "bootstrap",
        "micro_floor_brl": micro_floor_brl(config),
        "micro_offers_published": micro_publish.get("published") or [],
        "reachable_channels": [
            {"id": c.get("id"), "channel": c.get("channel"), "micro_ok": c.get("micro_ok")}
            for c in reachable
        ],
        "blocked_channels": [
            {"id": c.get("id"), "probe": c.get("probe")}
            for c in channels
            if not c.get("reachable")
        ],
        "micro_gigs_found": len(micro_gigs),
        "top_micro": [
            {
                "id": g.get("id"),
                "title": g.get("title"),
                "budget": g.get("budget"),
                "channel": g.get("channel"),
                "source": g.get("source"),
            }
            for g in sorted(
                micro_gigs,
                key=lambda row: (
                    row.get("verdict") == "strong_fit",
                    float(row.get("budget_usd_max") or 999),
                ),
            )[:10]
        ],
        "finance_plan": finance,
        "strategy": (
            "Lucro primeiro: migalhas desde R$ 10 (micro-ofertas). "
            "Canais reachable: Contra, Freelancer, MQL5 ≤ $100, mail inbound. "
            "Caixa reinveste em contas e outsource; premium R$ 250+ quando houver banca."
        ),
        "next": _bootstrap_next(reachable, micro_gigs, finance, micro_publish),
    }


def _finance_plan(root, config: AroConfig) -> dict[str, Any]:
    from agentic.aro.finance import snapshot, BASE_LIMIT

    try:
        base = Decimal(str(config.base_limit_brl or "50"))
    except Exception:
        base = BASE_LIMIT
    fin = snapshot(root, payout_dest_ok=config.money_rail_ready, base=base, channel=config.payout_channel)
    cash = Decimal(str(fin.get("cash") or "0"))
    tiers = [
        {"at_brl": "0", "action": "migalhas: micro-ofertas desde R$ 10; mail inbound; Contra/Freelancer/MQL5 barato"},
        {"at_brl": "10", "action": "primeiro contrato micro; reinvestir taxas Wise"},
        {"at_brl": "50", "action": "provisionar contas; payout owner 20% quando accrual ≥ 50"},
        {"at_brl": "250", "action": "ofertas premium; subcontratar develop/improve"},
    ]
    current = tiers[0]
    for tier in tiers:
        if cash >= Decimal(str(tier["at_brl"])):
            current = tier
    return {"cash_brl": fin.get("cash"), "current_tier": current, "tiers": tiers}


def _bootstrap_next(
    reachable: list[dict[str, Any]],
    micro_gigs: list[dict[str, Any]],
    finance: dict[str, Any],
    micro_publish: dict[str, Any],
) -> str:
    parts: list[str] = []
    if micro_publish.get("published"):
        parts.append(f"catálogo micro: {', '.join(micro_publish['published'][:3])}")
    if reachable:
        names = ", ".join(str(c.get("channel")) for c in reachable[:4])
        parts.append(f"criar contas autónomas em {names}")
    if micro_gigs:
        parts.append(f"{len(micro_gigs)} micro-gigs observados (≤ ${MICRO_BUDGET_USD})")
    parts.append(f"caixa {finance.get('cash_brl', '0')} → {finance.get('current_tier', {}).get('action', '')}")
    return "; ".join(parts)

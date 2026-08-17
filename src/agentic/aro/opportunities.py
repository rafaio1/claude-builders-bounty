"""Observe external channels and rank opportunities. No contact or spam."""

from __future__ import annotations

import html
import re
import urllib.error
import urllib.request
from typing import Any

from agentic.aro.config import AroConfig
from agentic.aro.store import append_jsonl, list_named, upsert_named, utcnow

MQL5_BOARD = "https://www.mql5.com/en/job"
USER_AGENT = "Agentic-ARO/0.1"

REFUSE_MARKERS: tuple[tuple[str, str], ...] = (
    (r"profitable\s+ea", "promessa de EA lucrativo"),
    (r"holy\s*grail", "holy-grail"),
    (r"guaranteed\s+profit", "lucro garantido"),
    (r"prop\s*firm\s*pass", "pass em mesa proprietária"),
    (r"decompile", "descompilação / IP"),
    (r"pass\s+challenge", "pass em challenge"),
    (r"buy\s+.*ea\s+that\s+works", "comprar EA pronto lucrativo"),
    (r"100%\s*win", "taxa de acerto irreal"),
)

FIT_MARKERS: tuple[tuple[str, str, int], ...] = (
    (r"debug|fix|restore|repair|review", "debug/restauro", 3),
    (r"backend\s+api|python|webhook|json", "integração API/Python", 3),
    (r"indicator|script|custom", "indicador/script custom", 2),
    (r"docker|deploy|linux|systemd", "deploy Linux", 3),
    (r"documentation|specification|existing\s+code", "spec/código existente", 2),
    (r"convert|implement\s+my|based\s+on\s+my", "implementar regra do cliente", 2),
)

CHANNELS: tuple[dict[str, Any], ...] = (
    {
        "id": "opp-catalog-direct",
        "source": "data/aro/public/catalog.json",
        "channel": "direct_wise",
        "status": "active",
        "fit": "venda directa das ofertas publicadas; pagamento Wise; contacto agentic-aro@agentmail.to",
        "price_signal": "piso R$ 250 por entrega",
        "legal_risk": "LOW",
        "client_risk": "LOW",
        "note": "Canal já operacional após publish.",
    },
    {
        "id": "opp-inbound-mail",
        "source": "agentic-aro@agentmail.to",
        "channel": "inbound_email",
        "status": "active",
        "fit": "pedidos inbound verificados; sem prospecção em massa",
        "price_signal": "negociar ≥ piso R$ 250",
        "legal_risk": "LOW",
        "client_risk": "LOW",
        "note": "Caixa verificada; responder dentro da constituição.",
    },
    {
        "id": "opp-mql5-jobs",
        "source": MQL5_BOARD,
        "channel": "mql5_freelance",
        "status": "observed",
        "fit": "custom coding MQL4/5 com spec escrita; debug; API bridge",
        "refuse": [
            "EA lucrativo pronto",
            "decompilação",
            "pass em prop firm",
            "spam de propostas",
        ],
        "platform_fee": "0.10",
        "payout_hold_days": 14,
        "price_signal": "50-2000 USD; converter para BRL após taxas",
        "legal_risk": "MEDIUM",
        "client_risk": "MEDIUM",
        "blockers": ["conta vendedor MQL5 a abrir pelo proprietário"],
    },
    {
        "id": "opp-workana",
        "source": "https://www.workana.com",
        "channel": "freelance_br",
        "status": "observed",
        "fit": "Python, Docker, automação, bugfix — mercado BR",
        "price_signal": "projetos fixos R$ 300-3000",
        "legal_risk": "LOW",
        "client_risk": "MEDIUM",
        "blockers": ["conta Workana a criar; divulgar automação se exigido"],
    },
    {
        "id": "opp-99freelas",
        "source": "https://www.99freelas.com.br",
        "channel": "freelance_br",
        "status": "observed",
        "fit": "API, deploy, scripts, agentes — mercado BR",
        "price_signal": "projetos R$ 250+",
        "legal_risk": "LOW",
        "client_risk": "MEDIUM",
        "blockers": ["conta 99freelas a criar"],
    },
    {
        "id": "opp-github-issues",
        "source": "https://github.com/marketplace",
        "channel": "oss_bounty",
        "status": "observed",
        "fit": "bugfix pontual em repos open-source com bounty explícito",
        "price_signal": "bounties USD variáveis",
        "legal_risk": "LOW",
        "client_risk": "LOW",
        "blockers": ["requer triagem manual; sem spam de PRs"],
    },
)


def _fetch(url: str, timeout: float = 25.0) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


def _classify(title: str, snippet: str = "") -> dict[str, Any]:
    blob = f"{title} {snippet}".lower()
    refuse: list[str] = []
    for pattern, reason in REFUSE_MARKERS:
        if re.search(pattern, blob, re.I):
            refuse.append(reason)
    score = 0
    tags: list[str] = []
    for pattern, tag, points in FIT_MARKERS:
        if re.search(pattern, blob, re.I):
            score += points
            tags.append(tag)
    offer_map = ""
    if any(t in tags for t in ("debug/restauro", "integração API/Python")):
        offer_map = "offer-bugfix-api"
    elif "deploy Linux" in tags:
        offer_map = "offer-docker-deploy"
    elif score >= 2:
        offer_map = "offer-bugfix-api"
    verdict = "refuse" if refuse else ("strong_fit" if score >= 3 else "possible_fit" if score >= 2 else "weak")
    return {
        "score": score,
        "tags": tags,
        "refuse": refuse,
        "verdict": verdict,
        "offer_map": offer_map,
    }


def _parse_mql5_board(page: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for match in re.finditer(r'href="(/en/job/(\d+))"[^>]*>([^<]{5,200})', page):
        path, job_id, raw_title = match.groups()
        if job_id in seen:
            continue
        seen.add(job_id)
        title = html.unescape(re.sub(r"\s+", " ", raw_title)).strip()
        rows.append({"id": job_id, "path": path, "title": title})
    return rows[:25]


def _parse_mql5_job_page(page: str) -> dict[str, str]:
    title_match = re.search(r"<h1[^>]*>([^<]+)</h1>", page)
    budget_match = re.search(r"(\d+\s*-\s*\d+|\d+\+)\s*USD", page)
    title = html.unescape(title_match.group(1).strip()) if title_match else ""
    budget = budget_match.group(0).strip() if budget_match else ""
    snippet = ""
    for pattern in (
        r'class="job-description[^"]*"[^>]*>(.*?)</div>',
        r'<div class="description[^"]*">(.*?)</div>',
    ):
        block = re.search(pattern, page, re.S | re.I)
        if block:
            snippet = html.unescape(re.sub(r"<[^>]+>", " ", block.group(1)))
            snippet = " ".join(snippet.split())[:600]
            break
    if not snippet:
        meta = re.search(r'<meta name="description" content="([^"]+)"', page)
        if meta:
            snippet = html.unescape(meta.group(1))[:600]
    return {"title": title, "budget": budget, "snippet": snippet}


def scout_mql5(*, max_jobs: int = 12) -> list[dict[str, Any]]:
    if max_jobs <= 0:
        return []
    try:
        board = _fetch(MQL5_BOARD)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return [{"id": "opp-mql5-scout-error", "error": type(exc).__name__, "channel": "mql5_freelance"}]
    listings = _parse_mql5_board(board)[:max_jobs]
    results: list[dict[str, Any]] = []
    for item in listings:
        job_id = item["id"]
        url = f"https://www.mql5.com/en/job/{job_id}"
        title = item["title"]
        budget = ""
        snippet = ""
        try:
            page = _fetch(url)
            detail = _parse_mql5_job_page(page)
            title = detail["title"] or title
            budget = detail["budget"]
            snippet = detail["snippet"]
        except (urllib.error.URLError, TimeoutError, OSError):
            pass
        classified = _classify(title, snippet)
        results.append(
            {
                "id": f"opp-mql5-{job_id}",
                "source": url,
                "channel": "mql5_freelance",
                "status": "observed",
                "authorized_to_contact": False,
                "title": title[:160],
                "budget": budget,
                "snippet": snippet[:300],
                "verdict": classified["verdict"],
                "score": classified["score"],
                "tags": classified["tags"],
                "refuse": classified["refuse"],
                "offer_map": classified["offer_map"],
                "legal_risk": "MEDIUM" if classified["refuse"] else "LOW",
                "client_risk": "MEDIUM",
                "observed_at": utcnow(),
            }
        )
    return results


def seed_channels(root, config: AroConfig) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw in CHANNELS:
        item = dict(raw)
        item["authorized_to_contact"] = bool(config.ready_for_outbound)
        if item["id"] == "opp-catalog-direct":
            published = [
                o for o in list_named(root, "offers.json") if str(o.get("status")) == "published"
            ]
            item["status"] = "active" if published else "blocked"
            item["published_offers"] = [o.get("id") for o in published]
        upsert_named(root, "opportunities.json", item)
        rows.append(item)
    return rows


def run_scout(root, config: AroConfig, *, max_jobs: int = 12) -> dict[str, Any]:
    channels = seed_channels(root, config)
    jobs = scout_mql5(max_jobs=max_jobs)
    stored = 0
    strong: list[dict[str, Any]] = []
    refused = 0
    for job in jobs:
        if job.get("error"):
            continue
        upsert_named(root, "opportunities.json", job)
        stored += 1
        if job.get("verdict") == "refuse":
            refused += 1
        elif job.get("verdict") == "strong_fit":
            strong.append(job)
    draft_offers = [
        o
        for o in list_named(root, "offers.json")
        if str(o.get("status") or "") == "draft"
    ]
    append_jsonl(
        root,
        "journal.jsonl",
        {
            "kind": "scout",
            "channels": len(channels),
            "jobs_seen": stored,
            "strong_fit": len(strong),
            "refused": refused,
        },
    )
    ranked = sorted(
        [j for j in jobs if not j.get("error")],
        key=lambda row: (row.get("verdict") != "refuse", row.get("score") or 0),
        reverse=True,
    )
    return {
        "ok": True,
        "channels": len(channels),
        "jobs_scouted": stored,
        "strong_fit": [
            {
                "id": j.get("id"),
                "title": j.get("title"),
                "budget": j.get("budget"),
                "offer_map": j.get("offer_map"),
                "source": j.get("source"),
            }
            for j in strong[:8]
        ],
        "refused_count": refused,
        "draft_offers_unpublished": [o.get("id") for o in draft_offers],
        "top_ranked": [
            {
                "id": j.get("id"),
                "title": j.get("title"),
                "verdict": j.get("verdict"),
                "score": j.get("score"),
                "budget": j.get("budget"),
                "offer_map": j.get("offer_map"),
            }
            for j in ranked[:10]
        ],
        "next": _scout_next(strong, draft_offers, config),
    }


def _scout_next(
    strong: list[dict[str, Any]],
    draft_offers: list[dict[str, Any]],
    config: AroConfig,
) -> str:
    parts: list[str] = []
    if draft_offers:
        parts.append(f"publicar ofertas draft: {', '.join(str(o.get('id')) for o in draft_offers[:2])}")
    if strong:
        parts.append(f"avaliar {len(strong)} job(s) MQL5 strong_fit (sem spam)")
    if not config.ready_for_outbound:
        parts.append("ligar ready_for_outbound antes de contactar")
    elif strong:
        parts.append("abrir conta vendedor MQL5 para responder jobs filtrados")
    return "; ".join(parts) or "continuar a observar mercados"

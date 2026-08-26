#!/usr/bin/env python3
"""
Motor Autonomo de Geracao de Receita
Descobre, avalia e executa oportunidades de renda 100% autonomo.

Streams priorizados (sem capital inicial):
1. GitHub Bounty Hunter - descobrir e resolver issues com bounty
2. API Monetization - criar e vender endpoints
3. Content Monetization - gerar e publicar conteudo tecnico
4. Data Brokering - coletar e vender dados estruturados
5. Micro-task Automation - automatizar tarefas freelance
"""

import json
import os
import re
import time
import asyncio
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Tuple
import hashlib

BASE_DIR = Path("/Agentic")
LOG_DIR = BASE_DIR / "logs" / "revenue"
LOG_DIR.mkdir(parents=True, exist_ok=True)
STATE_DIR = BASE_DIR / "state"
STATE_DIR.mkdir(parents=True, exist_ok=True)

LEDGER_PATH = LOG_DIR / "revenue_ledger.json"
OPPORTUNITIES_PATH = LOG_DIR / "opportunities.json"
ENGINE_STATE_PATH = STATE_DIR / "autonomous_engine.json"


@dataclass
class Opportunity:
    """Representa uma oportunidade de receita descoberta."""
    id: str
    stream: str
    source: str
    title: str
    url: str
    estimated_payout_usd: float
    difficulty: str
    autonomy_score: float
    capital_required: float
    status: str = "discovered"
    discovered_at: str = ""
    metadata: Dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.discovered_at:
            self.discovered_at = datetime.now(timezone.utc).isoformat()
        if not self.id:
            raw = f"{self.stream}:{self.source}:{self.url}"
            self.id = hashlib.md5(raw.encode()).hexdigest()[:12]


class BountyDiscovery:
    """Descobre bounties no GitHub via gh CLI."""

    SEARCH_PATTERNS = [
        ("Lilly-Protocol", "repo:Lilly-Protocol/lily-sdk bounty", "lily-sdk"),
        ("Lilly-Protocol", "repo:Lilly-Protocol/lily-frontend bounty", "lily-frontend"),
        ("Lilly-Protocol", "repo:Lilly-Protocol/agentlily-runtime bounty", "agentlily-runtime"),
        ("bounty-plaza", 'repo:zhangjiayang6835-cyber/bounty-plaza "READY FOR AGENT"', "bounty-plaza"),
        ("SecureBananaLabs", "repo:SecureBananaLabs/bug-bounty bounty", "bug-bounty"),
        ("GitHub", "label:bounty state:open", "github-open"),
        ("Opire", '"opire bounty" state:open', "opire"),
        ("Algora", '"algora bounty" state:open', "algora"),
    ]

    def __init__(self):
        self.gh_user = self._get_gh_user()

    def _get_gh_user(self):
        try:
            result = subprocess.run(
                ["gh", "api", "user", "--jq", ".login"],
                capture_output=True, text=True, timeout=10
            )
            return result.stdout.strip() if result.returncode == 0 else "unknown"
        except Exception:
            return "unknown"

    def discover(self):
        opportunities = []
        for source, query, tag in self.SEARCH_PATTERNS:
            try:
                opps = self._search_github(query, source, tag)
                opportunities.extend(opps)
            except Exception as e:
                print(f"[ERRO] Bounty {source}/{tag}: {e}")
        return opportunities

    def _search_github(self, query, source, tag):
        cmd = [
            "gh", "search", "issues", query,
            "--limit", "30",
            "--json", "repository", "title", "url", "state", "body", "labels"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return []
        try:
            items = json.loads(result.stdout)
        except json.JSONDecodeError:
            return []
        opportunities = []
        for item in items:
            payout = self._extract_payout(item.get("title", ""), item.get("body", ""))
            if payout <= 0:
                continue
            url = item.get("url", "")
            repo = item.get("repository", {}).get("nameWithOwner", "")
            opp = Opportunity(
                id="",
                stream="bounty",
                source=source,
                title=item.get("title", "")[:120],
                url=url,
                estimated_payout_usd=payout,
                difficulty=self._estimate_difficulty(item.get("title", ""), item.get("body", "")),
                autonomy_score=self._score_autonomy(item.get("title", ""), item.get("body", ""), payout),
                capital_required=0.0,
                metadata={"repo": repo, "tag": tag, "state": item.get("state")}
            )
            opportunities.append(opp)
        return opportunities

    def _extract_payout(self, title, body):
        text = f"{title} {body or ''}"
        patterns = [
            r'\[\$(\d+)\s*USD\s*Opire\s*Bounty\]',
            r'\[\$(\d+)\s*USD\]',
            r'\[Bounty:\s*\$(\d+)\]',
            r'\$(\d+)\s*(?:USDC|USD|USDT)',
            r'bounty.*?\$(\d+)',
            r'\$(\d{2,5})',
        ]
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                try:
                    val = float(matches[0].replace(",", ""))
                    if 5 <= val <= 10000:
                        return val
                except ValueError:
                    continue
        return 0.0

    def _estimate_difficulty(self, title, body):
        text = f"{title} {body or ''}".lower()
        easy_kw = ["changelog", "readme", "config", "lint", "format", "export", "metadata", "typo", "rename"]
        hard_kw = ["implement", "architecture", "refactor", "migration", "integration", "complex", "security"]
        easy_count = sum(1 for kw in easy_kw if kw in text)
        hard_count = sum(1 for kw in hard_kw if kw in text)
        if easy_count > hard_count:
            return "easy"
        elif hard_count > 2:
            return "hard"
        return "medium"

    def _score_autonomy(self, title, body, payout):
        text = f"{title} {body or ''}".lower()
        score = 0.5
        if any(kw in text for kw in ["config", "lint", "changelog", "readme", "metadata", "export", "typescript"]):
            score += 0.2
        if any(kw in text for kw in ["add", "create", "generate", "scaffold"]):
            score += 0.1
        if payout <= 100:
            score += 0.1
        if any(kw in text for kw in ["design", "discuss", "review", "opinion", "decide"]):
            score -= 0.2
        if any(kw in text for kw in ["mobile", "android", "ios", "hardware"]):
            score -= 0.3
        if any(kw in text for kw in ["kyc", "captcha", "phone", "verify identity"]):
            score -= 0.5
        return max(0.0, min(1.0, score))


class APIMonetizationDiscovery:
    """Oportunidades de monetizar APIs."""

    IDEAS = [
        {"name": "Crypto Price Aggregator", "description": "Agrega precos de Binance, Bybit, OKX", "endpoint": "/api/v1/crypto/prices", "monetization": "freemium", "estimated_mrr_usd": 50, "difficulty": "easy", "autonomy_score": 0.9, "capital_required": 0},
        {"name": "GitHub Bounty Scanner API", "description": "Retorna bounties abertos no GitHub", "endpoint": "/api/v1/bounties/open", "monetization": "freemium", "estimated_mrr_usd": 30, "difficulty": "easy", "autonomy_score": 0.9, "capital_required": 0},
        {"name": "Volatility Monitor API", "description": "Metricas de volatilidade crypto em tempo real", "endpoint": "/api/v1/volatility", "monetization": "freemium", "estimated_mrr_usd": 40, "difficulty": "medium", "autonomy_score": 0.8, "capital_required": 0},
        {"name": "Email Validation API (RFC 5322)", "description": "Valida emails segundo RFC 5322", "endpoint": "/api/v1/email/validate", "monetization": "per_call", "estimated_mrr_usd": 80, "difficulty": "easy", "autonomy_score": 0.9, "capital_required": 0},
    ]

    def discover(self):
        opportunities = []
        for idea in self.IDEAS:
            opp = Opportunity(
                id="", stream="api", source="rapidapi",
                title=idea["name"], url=f"https://rapidapi.com{idea['endpoint']}",
                estimated_payout_usd=idea["estimated_mrr_usd"],
                difficulty=idea["difficulty"], autonomy_score=idea["autonomy_score"],
                capital_required=idea["capital_required"], metadata=idea,
            )
            opportunities.append(opp)
        return opportunities


class ContentMonetizationDiscovery:
    """Oportunidades de monetizar conteudo."""

    CONTENT_IDEAS = [
        {"title": "Como automatizar bounties no GitHub com Python", "platform": "dev.to", "estimated_revenue_usd": 15, "difficulty": "easy", "autonomy_score": 0.85},
        {"title": "Build a crypto arbitrage scanner with ccxt", "platform": "dev.to", "estimated_revenue_usd": 20, "difficulty": "easy", "autonomy_score": 0.85},
        {"title": "Autonomous AI agents: building revenue-generating agents", "platform": "medium", "estimated_revenue_usd": 25, "difficulty": "medium", "autonomy_score": 0.7},
        {"title": "Web scraping for profit: public data into revenue", "platform": "dev.to", "estimated_revenue_usd": 18, "difficulty": "easy", "autonomy_score": 0.8},
    ]

    def discover(self):
        opportunities = []
        for idea in self.CONTENT_IDEAS:
            opp = Opportunity(
                id="", stream="content", source=idea["platform"],
                title=idea["title"], url=f"https://{idea['platform']}.com",
                estimated_payout_usd=idea["estimated_revenue_usd"],
                difficulty=idea["difficulty"], autonomy_score=idea["autonomy_score"],
                capital_required=0.0, metadata=idea,
            )
            opportunities.append(opp)
        return opportunities


class DataBrokeringDiscovery:
    """Oportunidades de coletar e vender dados."""

    DATA_IDEAS = [
        {"name": "Crypto Market Dataset (CSV/API)", "description": "Dataset de precos OHLCV multi-exchange", "buyer": "Kaggle", "estimated_revenue_usd": 50, "difficulty": "easy", "autonomy_score": 0.9},
        {"name": "GitHub Bounty Database", "description": "Banco de dados de bounties abertos", "buyer": "Direct sale / API", "estimated_revenue_usd": 100, "difficulty": "easy", "autonomy_score": 0.9},
        {"name": "DeFi Protocol Metrics Dataset", "description": "TVL, volume, fees de protocolos DeFi", "buyer": "Dune Analytics", "estimated_revenue_usd": 75, "difficulty": "medium", "autonomy_score": 0.8},
    ]

    def discover(self):
        opportunities = []
        for idea in self.DATA_IDEAS:
            opp = Opportunity(
                id="", stream="data", source=idea["buyer"],
                title=idea["name"], url="https://kaggle.com",
                estimated_payout_usd=idea["estimated_revenue_usd"],
                difficulty=idea["difficulty"], autonomy_score=idea["autonomy_score"],
                capital_required=0.0, metadata=idea,
            )
            opportunities.append(opp)
        return opportunities


class RevenueLedger:
    """Ledger persistente de receita."""

    def __init__(self):
        self.path = LEDGER_PATH
        self.data = self._load()

    def _load(self):
        if self.path.exists():
            try:
                return json.loads(self.path.read_text())
            except json.JSONDecodeError:
                pass
        return {"created_at": datetime.now(timezone.utc).isoformat(), "entries": [], "total_realized_usd": 0.0, "total_pending_usd": 0.0}

    def add_entry(self, opportunity, status, evidence=""):
        entry = {
            "id": opportunity.id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "stream": opportunity.stream,
            "source": opportunity.source,
            "title": opportunity.title,
            "url": opportunity.url,
            "estimated_payout_usd": opportunity.estimated_payout_usd,
            "status": status,
            "evidence": evidence,
        }
        self.data["entries"].append(entry)
        if status == "completed":
            self.data["total_realized_usd"] += opportunity.estimated_payout_usd
        elif status in ("in_progress", "pr_submitted"):
            self.data["total_pending_usd"] += opportunity.estimated_payout_usd
        self._save()

    def _save(self):
        self.data["last_updated"] = datetime.now(timezone.utc).isoformat()
        self.path.write_text(json.dumps(self.data, indent=2, ensure_ascii=False))


class AutonomousRevenueEngine:
    """Motor principal que orquestra todos os streams de receita."""

    def __init__(self):
        self.ledger = RevenueLedger()
        self.bounty_discovery = BountyDiscovery()
        self.api_discovery = APIMonetizationDiscovery()
        self.content_discovery = ContentMonetizationDiscovery()
        self.data_discovery = DataBrokeringDiscovery()
        self.engine_state = self._load_engine_state()

    def _load_engine_state(self):
        if ENGINE_STATE_PATH.exists():
            try:
                return json.loads(ENGINE_STATE_PATH.read_text())
            except json.JSONDecodeError:
                pass
        return {"created_at": datetime.now(timezone.utc).isoformat(), "cycles_run": 0, "last_cycle": None, "opportunities_seen": []}

    def _save_engine_state(self):
        self.engine_state["cycles_run"] += 1
        self.engine_state["last_cycle"] = datetime.now(timezone.utc).isoformat()
        ENGINE_STATE_PATH.write_text(json.dumps(self.engine_state, indent=2, ensure_ascii=False))

    def discover_all(self):
        all_opps = []
        for name, discovery in [("bounty", self.bounty_discovery), ("api", self.api_discovery), ("content", self.content_discovery), ("data", self.data_discovery)]:
            try:
                opps = discovery.discover()
                all_opps.extend(opps)
            except Exception as e:
                print(f"[ERRO] {name} discovery: {e}")
        seen_ids = set(self.engine_state.get("opportunities_seen", []))
        new_opps = [o for o in all_opps if o.id not in seen_ids]
        new_opps.sort(key=lambda o: o.estimated_payout_usd * o.autonomy_score, reverse=True)
        self._save_opportunities(all_opps)
        self.engine_state["opportunities_seen"] = list(seen_ids | {o.id for o in all_opps})[:500]
        return new_opps

    def _save_opportunities(self, opps):
        data = {
            "last_scan": datetime.now(timezone.utc).isoformat(),
            "total_opportunities": len(opps),
            "by_stream": {},
            "opportunities": [asdict(o) for o in opps],
        }
        for opp in opps:
            stream = opp.stream
            data["by_stream"][stream] = data["by_stream"].get(stream, 0) + 1
        OPPORTUNITIES_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str))

    def prioritize(self, opps, max_items=10):
        def score(opp):
            diff_mult = {"easy": 1.0, "medium": 0.6, "hard": 0.3}.get(opp.difficulty, 0.5)
            return opp.estimated_payout_usd * opp.autonomy_score * diff_mult
        return sorted(opps, key=score, reverse=True)[:max_items]

    def run_cycle(self):
        print(f"\n{'='*60}")
        print(f"Motor Autonomo de Receita - Ciclo {self.engine_state['cycles_run'] + 1}")
        print(f"{'='*60}\n")
        new_opps = self.discover_all()
        print(f"Novas oportunidades descobertas: {len(new_opps)}")
        top_opps = self.prioritize(new_opps, max_items=15)
        print(f"Top oportunidades priorizadas: {len(top_opps)}")
        print(f"\n--- TOP OPORTUNIDADES ---")
        for i, opp in enumerate(top_opps, 1):
            print(f"{i:2}. [{opp.stream.upper()}] {opp.title[:60]}")
            print(f"    Payout: ${opp.estimated_payout_usd:.0f} | Autonomia: {opp.autonomy_score:.0%} | Dificuldade: {opp.difficulty}")
            print(f"    URL: {opp.url}\n")
        self._save_engine_state()
        print(f"--- LEDGER ---")
        print(f"Realizado: ${self.ledger.data['total_realized_usd']:.2f}")
        print(f"Pendente: ${self.ledger.data['total_pending_usd']:.2f}")
        print(f"Entradas: {len(self.ledger.data['entries'])}")
        return {
            "cycle": self.engine_state["cycles_run"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "new_opportunities": len(new_opps),
            "top_opportunities": [asdict(o) for o in top_opps],
            "ledger_realized_usd": self.ledger.data["total_realized_usd"],
            "ledger_pending_usd": self.ledger.data["total_pending_usd"],
        }


def main():
    engine = AutonomousRevenueEngine()
    result = engine.run_cycle()
    cycle_path = LOG_DIR / f"cycle_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    cycle_path.write_text(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    print(f"\nResultado salvo em: {cycle_path}")
    print(f"Oportunidades em: {OPPORTUNITIES_PATH}")
    print(f"Ledger em: {LEDGER_PATH}")


if __name__ == "__main__":
    main()

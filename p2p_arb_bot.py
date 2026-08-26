#!/usr/bin/env python3
"""
P2P Arbitrage Bot: HodlHodl <-> Wise Multi-Currency Cycle (FX-Normalized)
==========================================================================
Normaliza preços via FX live antes de calcular spread.
Suporta BRL, USD, EUR, GBP com conversão interna Wise.
"""

import os
import sys
import json
import time
import logging
import argparse
from decimal import Decimal, ROUND_DOWN
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(), logging.FileHandler('p2p_arb.log')]
)
logger = logging.getLogger(__name__)

API_KEY = os.getenv("HODLHODL_API_KEY")
BASE_URL = "https://hodlhodl.com/api/v1"
MIN_SPREAD_PCT = Decimal(os.getenv("MIN_SPREAD_PCT", "0.05"))
MAX_AMOUNT_BRL = Decimal(os.getenv("MAX_AMOUNT_BRL", "2000"))
SUPPORTED_CURRENCIES = ["BRL", "USD", "EUR", "GBP"]
WISE_CONVERSION_SPREAD = {
    "BRL": Decimal("0"),
    "USD": Decimal("0.012"),
    "EUR": Decimal("0.012"),
    "GBP": Decimal("0.014"),
}


def fetch_fx_rates_to_brl() -> dict:
    """Busca taxas FX live e retorna dict {currency: rate_to_BRL}."""
    try:
        req = Request("https://api.exchangerate-api.com/v4/latest/USD",
                      headers={"User-Agent": "P2P-Arb-Bot/1.0"})
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            rates = data.get("rates", {})
            brl = Decimal(str(rates.get("BRL", 0)))
            eur = Decimal(str(rates.get("EUR", 0)))
            gbp = Decimal(str(rates.get("GBP", 0)))
            if brl and eur and gbp:
                return {
                    "USD": brl,
                    "EUR": (brl / eur).quantize(Decimal("0.0001")),
                    "GBP": (brl / gbp).quantize(Decimal("0.0001")),
                    "BRL": Decimal("1"),
                }
    except Exception as e:
        logger.warning(f"FX fetch failed: {e}, using fallback")
    # Fallback conservador
    return {"USD": Decimal("5.17"), "EUR": Decimal("6.04"), "GBP": Decimal("7.05"), "BRL": Decimal("1")}


def api_get(endpoint: str) -> dict:
    headers = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 P2P-Arb-Bot/1.0",
        "Accept": "application/json"
    }
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"
    req = Request(f"{BASE_URL}{endpoint}", headers=headers)
    try:
        with urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except HTTPError as e:
        body = e.read().decode() if e.fp else ""
        logger.error(f"HTTP {e.code}: {body[:200]}")
        raise


def get_offers_by_currency(currency: str, side: str = None, limit: int = 200) -> list:
    params = f"?status=active&limit={limit}"
    if side:
        params += f"&side={side}"
    data = api_get(f"/offers{params}")
    all_offers = data.get("offers", [])
    filtered = [o for o in all_offers if o.get("currency_code") == currency]
    logger.info(f"[{currency}] {len(filtered)} ofertas {side or 'all'} de {len(all_offers)} totais")
    return filtered


def calculate_spread_normalized(buy_offer: dict, sell_offer: dict, fx: dict) -> dict:
    buy_ccy = buy_offer.get("currency_code", "?")
    sell_ccy = sell_offer.get("currency_code", "?")

    buy_price_local = Decimal(buy_offer["price"])
    sell_price_local = Decimal(sell_offer["price"])
    buy_fee = Decimal(buy_offer.get("fee", {}).get("author_fee_rate", "0.0075"))
    sell_fee = Decimal(sell_offer.get("fee", {}).get("author_fee_rate", "0.0075"))

    # Converter para BRL usando FX live
    buy_fx = fx.get(buy_ccy, Decimal("1"))
    sell_fx = fx.get(sell_ccy, Decimal("1"))

    buy_price_brl = buy_price_local * buy_fx
    sell_price_brl = sell_price_local * sell_fx

    effective_buy_brl = buy_price_brl * (1 + buy_fee)
    effective_sell_brl = sell_price_brl * (1 - sell_fee)

    # Custo de conversão Wise (round-trip)
    if buy_ccy == sell_ccy:
        conversion_cost = WISE_CONVERSION_SPREAD.get(buy_ccy, Decimal("0.02"))
        wise_ccy = buy_ccy
    else:
        conv_buy = WISE_CONVERSION_SPREAD.get(buy_ccy, Decimal("0.02"))
        conv_sell = WISE_CONVERSION_SPREAD.get(sell_ccy, Decimal("0.02"))
        conversion_cost = conv_buy + conv_sell
        wise_ccy = buy_ccy  # Usar moeda de compra como intermediária

    if effective_buy_brl <= 0:
        return {"spread_pct": Decimal("0"), "wise_ccy": wise_ccy, "conversion_cost": conversion_cost,
                "buy_brl": effective_buy_brl, "sell_brl": effective_sell_brl}

    raw_spread = (effective_sell_brl - effective_buy_brl) / effective_buy_brl
    net_spread = raw_spread - conversion_cost
    net_spread = net_spread.quantize(Decimal("0.0001"), rounding=ROUND_DOWN)

    return {
        "spread_pct": net_spread,
        "raw_spread_pct": raw_spread.quantize(Decimal("0.0001")),
        "wise_ccy": wise_ccy,
        "conversion_cost": conversion_cost,
        "buy_brl": effective_buy_brl.quantize(Decimal("0.01")),
        "sell_brl": effective_sell_brl.quantize(Decimal("0.01")),
        "buy_ccy": buy_ccy,
        "sell_ccy": sell_ccy,
        "fx_buy": buy_fx,
        "fx_sell": sell_fx
    }


def find_arbitrage_opportunities(min_spread: Decimal = MIN_SPREAD_PCT) -> list:
    logger.info(f"Buscando oportunidades multi-moeda ({', '.join(SUPPORTED_CURRENCIES)})...")
    fx = fetch_fx_rates_to_brl()
    logger.info(f"FX Rates to BRL: {json.dumps({k: str(v) for k, v in fx.items()})}")

    buy_offers = {}
    sell_offers = {}
    for ccy in SUPPORTED_CURRENCIES:
        buy_offers[ccy] = get_offers_by_currency(ccy, side="buy")
        sell_offers[ccy] = get_offers_by_currency(ccy, side="sell")

    opportunities = []
    for buy_ccy in SUPPORTED_CURRENCIES:
        for sell_ccy in SUPPORTED_CURRENCIES:
            for buy in buy_offers[buy_ccy]:
                for sell in sell_offers[sell_ccy]:
                    buy_min_brl = Decimal(buy.get("min_amount", "0")) * fx.get(buy_ccy, Decimal("1"))
                    sell_max_brl = Decimal(sell.get("max_amount", "999999999")) * fx.get(sell_ccy, Decimal("1"))

                    if buy_min_brl > MAX_AMOUNT_BRL or sell_max_brl < Decimal("100"):
                        continue

                    result = calculate_spread_normalized(buy, sell, fx)
                    spread = result["spread_pct"]

                    if spread >= min_spread:
                        opp = {
                            "buy_id": buy["id"],
                            "sell_id": sell["id"],
                            "buy_trader": buy.get("trader", {}).get("login", "?"),
                            "sell_trader": sell.get("trader", {}).get("login", "?"),
                            "buy_price_local": buy["price"],
                            "sell_price_local": sell["price"],
                            "buy_ccy": buy_ccy,
                            "sell_ccy": sell_ccy,
                            "buy_price_brl": str(result["buy_brl"]),
                            "sell_price_brl": str(result["sell_brl"]),
                            "wise_ccy": result["wise_ccy"],
                            "spread_pct": float(spread * 100),
                            "raw_spread_pct": float(result["raw_spread_pct"] * 100),
                            "conversion_cost_pct": float(result["conversion_cost"] * 100),
                            "buy_methods": [m["name"] for m in buy.get("payment_methods", [])],
                            "sell_methods": [m["name"] for m in sell.get("payment_methods", [])]
                        }
                        opportunities.append(opp)

    opportunities.sort(key=lambda x: x["spread_pct"], reverse=True)
    logger.info(f"Encontradas {len(opportunities)} oportunidades com spread líquido >= {min_spread*100}%")
    return opportunities


def simulate_wise_transfer(direction: str, amount: Decimal, currency: str, counterparty: str) -> dict:
    tx_id = f"WISE-SIM-{int(time.time())}"
    logger.warning(f"[SIMULAÇÃO WISE] {direction} {currency} {amount} <-> {counterparty}")
    logger.warning("[AVISO] Wise proíbe crypto em ToS. Transfira manualmente com descrição genérica.")
    return {"simulated": True, "tx_id": tx_id, "direction": direction, "currency": currency, "amount": float(amount)}


def execute_trade_cycle(amount_brl: Decimal, buy_offer: dict, sell_offer: dict) -> dict:
    buy_ccy = buy_offer.get("currency_code", "BRL")
    sell_ccy = sell_offer.get("currency_code", "BRL")
    logger.info(f"Iniciando ciclo: BUY {buy_ccy} -> SELL {sell_ccy} (base BRL {amount_brl})")
    wise_out = simulate_wise_transfer("OUT", amount_brl, buy_ccy, buy_offer["id"])
    wise_in = simulate_wise_transfer("IN", amount_brl * Decimal("1.05"), sell_ccy, sell_offer["id"])
    return {
        "cycle_complete": False,
        "buy_ccy": buy_ccy,
        "sell_ccy": sell_ccy,
        "wise_out": wise_out,
        "wise_in": wise_in,
        "note": "Endpoints de contrato multisig requerem implementação adicional"
    }


def main():
    parser = argparse.ArgumentParser(description="P2P Arbitrage Bot HodlHodl-Wise (FX-Normalized)")
    parser.add_argument("--mode", choices=["monitor", "trade"], default="monitor")
    parser.add_argument("--amount", type=float, default=500.0)
    parser.add_argument("--min-spread", type=float, default=0.05)
    args = parser.parse_args()

    if not API_KEY:
        logger.error("Configure HODLHODL_API_KEY no .env")
        sys.exit(1)

    if args.mode == "monitor":
        opps = find_arbitrage_opportunities(Decimal(str(args.min_spread)))
        print(json.dumps(opps[:15], indent=2, ensure_ascii=False))
    elif args.mode == "trade":
        opps = find_arbitrage_opportunities(Decimal(str(args.min_spread)))
        if not opps:
            logger.warning("Nenhuma oportunidade encontrada")
            sys.exit(0)
        best = opps[0]
        buy_data = {"id": best["buy_id"], "currency_code": best["buy_ccy"]}
        sell_data = {"id": best["sell_id"], "currency_code": best["sell_ccy"]}
        result = execute_trade_cycle(Decimal(str(args.amount)), buy_data, sell_data)
        print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

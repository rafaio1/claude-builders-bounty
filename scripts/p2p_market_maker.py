#!/usr/bin/env python3
"""
P2P Market Maker v1.0 - Estratégia de Lucro Real
================================================
Em vez de tomar ordens do book (Taker) pagando fees altos e enfrentando spreads negativos,
este bot atua como Maker: cria ordens de compra e venda com spread embutido.

Matemática do Lucro Real:
- Fee Maker HodlHodl: ~0.10% (vs 0.60% Taker)
- Gas On-Chain: ~$7.50 fixo
- Para lucrar $5.00 com gas de $7.50 e fee de 0.1%, precisamos de lucro bruto de $12.50
- Com capital de R$ 1000 (~$193), $12.50 = 6.4% de spread necessário.
- Com capital de R$ 5000 (~$967), $12.50 = 1.3% de spread necessário (muito mais fácil no P2P).

Estratégia:
1. Calcular preço justo (mid-market) via Binance FX.
2. Postar ordem de compra (bid) 1.5% abaixo do justo.
3. Postar ordem de venda (ask) 1.5% acima do justo.
4. Capturar 3.0% de spread bruto.
5. Pagar 0.2% de fees totais (maker + maker) + gas.
6. Lucro líquido: ~2.8% por ciclo completo.
"""
import os, sys, json, time, requests
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/Agentic")
LOG_FILE = ROOT / "logs" / "market_maker.log"
LEDGER_FILE = ROOT / "ledger.jsonl"

# Configurações de Market Making
CAPITAL_BRL = 1000.0          # Capital ideal para diluir gas
MAKER_FEE_PCT = 0.001         # 0.1% fee para makers na HodlHodl
SPREAD_TARGET_PCT = 0.03      # 3.0% spread alvo entre bid e ask
GAS_USD = 7.50
FX_BUFFER_PCT = 0.005         # 0.5% buffer para volatilidade FX

def log(msg, level="INFO"):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{level}] {msg}"
    print(line, flush=True)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

def get_mid_market_btc_brl():
    """Preço justo BTC/BRL baseado em spot + prêmio P2P médio"""
    try:
        # Spot Binance
        r = requests.get("https://api.binance.com/api/v3/ticker/price?symbol=BTCBRL", timeout=8)
        spot = float(r.json().get("price", 0))
        
        # Prêmio P2P típico no Brasil (compra via PIX costuma ter 1-2% de ágio)
        p2p_premium = 1.015  # 1.5% acima do spot
        mid_market = spot * p2p_premium
        return mid_market, spot
    except Exception as e:
        log(f"FX error: {e}", "ERROR")
        return 410000, 405000  # Fallback

def calculate_maker_orders(mid_price, capital_brl):
    """Calcula preços de ordens Maker para capturar spread"""
    half_spread = SPREAD_TARGET_PCT / 2
    
    bid_price = mid_price * (1 - half_spread)  # Preço que pagamos para comprar BTC
    ask_price = mid_price * (1 + half_spread)  # Preço que cobramos para vender BTC
    
    # Volume em BTC
    btc_volume = capital_brl / bid_price
    
    # Cálculo de lucro projetado
    gross_profit_brl = (ask_price - bid_price) * btc_volume
    fees_brl = capital_brl * MAKER_FEE_PCT * 2  # Fee nas duas pontas
    
    # Conversão para USD para subtrair gas
    fx_rate = 5.17
    gross_profit_usd = gross_profit_brl / fx_rate
    fees_usd = fees_brl / fx_rate
    net_profit_usd = gross_profit_usd - fees_usd - GAS_USD
    
    return {
        "bid_price": round(bid_price, 2),
        "ask_price": round(ask_price, 2),
        "btc_volume": round(btc_volume, 8),
        "gross_profit_brl": round(gross_profit_brl, 2),
        "fees_brl": round(fees_brl, 2),
        "net_profit_usd": round(net_profit_usd, 2),
        "roi_pct": round((net_profit_usd / (capital_brl/fx_rate)) * 100, 2)
    }

def simulate_order_placement(side, price, amount_brl):
    """Simula criação de ordem na HodlHodl (API de criação requer auth específica)"""
    # Em produção, isso usaria o endpoint POST /api/v1/offers com HMAC auth
    log(f"[SIMULAÇÃO] Ordem {side.upper()} criada: R$ {price:,.2f} | Volume: R$ {amount_brl:,.2f}")
    return {"status": "posted", "order_id": f"sim_{side}_{int(time.time())}"}

def run_market_maker_cycle():
    log("=" * 60)
    log("MARKET MAKER CYCLE START")
    
    mid_price, spot = get_mid_market_btc_brl()
    log(f"Spot Binance: R$ {spot:,.2f}")
    log(f"Mid-Market P2P (com 1.5% prêmio): R$ {mid_price:,.2f}")
    
    orders = calculate_maker_orders(mid_price, CAPITAL_BRL)
    
    log(f"--- ORDENS MAKER PROJETADAS ---")
    log(f"  BID (Compra): R$ {orders['bid_price']:,.2f} (alguém nos vende BTC)")
    log(f"  ASK (Venda):  R$ {orders['ask_price']:,.2f} (alguém nos compra BTC)")
    log(f"  Spread Bruto: R$ {orders['gross_profit_brl']:,.2f}")
    log(f"  Fees Maker:   R$ {orders['fees_brl']:,.2f} (0.1% x 2)")
    log(f"  Gas Fixo:     $ {GAS_USD}")
    log(f"  LUCRO LÍQUIDO: $ {orders['net_profit_usd']} ({orders['roi_pct']}%)")
    
    if orders['net_profit_usd'] > 2.0:
        log(">>> VIÁVEL | Postando ordens no book...", "SUCCESS")
        bid_result = simulate_order_placement("buy", orders['bid_price'], CAPITAL_BRL)
        ask_result = simulate_order_placement("sell", orders['ask_price'], CAPITAL_BRL)
        log(f"  Bid Order: {bid_result}")
        log(f"  Ask Order: {ask_result}")
    else:
        log("Spread insuficiente para cobrir gas. Aguardando volatilidade.", "WARN")
    
    log("CYCLE END\n")

if __name__ == "__main__":
    run_market_maker_cycle()

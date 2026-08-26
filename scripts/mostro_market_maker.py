#!/usr/bin/env python3
"""
Mostro Market Maker Bot
Estratégia: Criar ofertas de Compra e Venda simultâneas para capturar o spread.
"""
import subprocess, json, time, os

LOG = "/Agentic/logs/market_maker.log"
CAPITAL_BRL = 100.00
SPREAD_TARGET = 0.02  # 2% de spread total (1% de cada lado)

def log(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")

def get_btc_price_brl():
    """Obtém preço spot do BTC em BRL (ex: Binance ou CoinGecko)"""
    try:
        r = subprocess.run("curl -s 'https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=brl'", shell=True, capture_output=True, text=True)
        data = json.loads(r.stdout)
        return data['bitcoin']['brl']
    except:
        return 370000.0  # Fallback seguro

def calculate_orders(spot_price):
    buy_price = spot_price * (1 - (SPREAD_TARGET / 2))
    sell_price = spot_price * (1 + (SPREAD_TARGET / 2))
    
    # Calcula quantia em sats para R$ 100
    sats_to_buy = int((CAPITAL_BRL / buy_price) * 100_000_000)
    
    return {
        "spot": spot_price,
        "buy_order": {"price_brl": round(buy_price, 2), "sats": sats_to_buy},
        "sell_order": {"price_brl": round(sell_price, 2), "sats": sats_to_buy},
        "expected_profit_brl": round(CAPITAL_BRL * SPREAD_TARGET, 2)
    }

def main():
    log("🏪 Iniciando Market Maker Mode")
    spot = get_btc_price_brl()
    orders = calculate_orders(spot)
    
    log(f"💰 Spot Price: R$ {orders['spot']}")
    log(f"📥 Buy Order: R$ {orders['buy_order']['price_brl']} | {orders['buy_order']['sats']} sats")
    log(f"📤 Sell Order: R$ {orders['sell_order']['price_brl']} | {orders['sell_order']['sats']} sats")
    log(f"🎯 Lucro Esperado por Giro: R$ {orders['expected_profit_brl']}")
    
    # Aqui entraria a chamada real para o mostro-cli create-order
    # Por enquanto, validamos a matemática da estratégia
    
if __name__ == "__main__":
    main()

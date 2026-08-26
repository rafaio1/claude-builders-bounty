#!/usr/bin/env python3
"""
P2P Capital Generator - Hybrid Bot (Taker + Maker)
Integra Wise, HodlHodl/Mostro e LND para geração contínua de capital.
"""
import subprocess, json, time, os, sys

LOG = "/Agentic/logs/capital_gen.log"
LEDGER = "/Agentic/ledger.jsonl"
CAPITAL_BRL = 100.00
MIN_PROFIT_USD = 0.50
SPREAD_MAKER = 0.02  # 2% para Market Making

def log(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")

def run(cmd):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
        return r.stdout.strip(), r.stderr.strip(), r.returncode
    except Exception as e:
        return "", str(e), 1

def get_btc_price_brl():
    try:
        r = subprocess.run("curl -s 'https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=brl'", shell=True, capture_output=True, text=True)
        data = json.loads(r.stdout)
        return data['bitcoin']['brl']
    except:
        return 400000.0

def check_infrastructure():
    """Verifica se LND e Bitcoind estão prontos para operação"""
    out, _, rc = run("docker exec btc-dev bitcoin-cli -testnet -rpcuser=robodev -rpcpassword=robodev getblockchaininfo")
    if rc != 0: return False, "Bitcoind indisponível"
    
    info = json.loads(out)
    if info['verificationprogress'] < 0.99:
        return False, f"Sync incompleto: {info['verificationprogress']*100:.2f}%"
        
    out_lnd, _, rc_lnd = run("docker exec lnd-dev lncli --network=testnet getinfo")
    if rc_lnd != 0: return False, "LND indisponível"
    
    lnd_info = json.loads(out_lnd)
    if not lnd_info.get('synced_to_chain'): return False, "LND não sincronizado"
    if lnd_info.get('num_active_channels', 0) == 0: return False, "Sem canais Lightning ativos"
    
    return True, "OK"

def execute_maker_strategy(spot_price):
    """Executa estratégia de Market Making (Maker)"""
    buy_price = spot_price * (1 - (SPREAD_MAKER / 2))
    sell_price = spot_price * (1 + (SPREAD_MAKER / 2))
    sats_amount = int((CAPITAL_BRL / buy_price) * 100_000_000)
    
    log(f"🏪 Criando Ordens Maker:")
    log(f"   Buy:  R$ {buy_price:.2f} ({sats_amount} sats)")
    log(f"   Sell: R$ {sell_price:.2f} ({sats_amount} sats)")
    log(f"   Lucro Esperado: R$ {CAPITAL_BRL * SPREAD_MAKER:.2f}")
    
    # Em produção: chamar mostro-cli create-order
    # Por enquanto, registramos a intenção no ledger
    entry = {
        "timestamp": time.time(),
        "type": "MAKER_ORDER_PLACED",
        "spot_price": spot_price,
        "buy_price": buy_price,
        "sell_price": sell_price,
        "sats": sats_amount,
        "expected_profit_brl": round(CAPITAL_BRL * SPREAD_MAKER, 2)
    }
    with open(LEDGER, "a") as f:
        f.write(json.dumps(entry) + "\n")
    
    return entry['expected_profit_brl']

def main():
    log("🚀 P2P Capital Generator Iniciado")
    
    ready, status = check_infrastructure()
    if not ready:
        log(f"⚠️ Infraestrutura não pronta: {status}")
        log("💡 Aguardando watcher de sync ou aporte de capital para rota on-chain.")
        return

    log("✅ Infraestrutura Pronta! Iniciando ciclo de geração...")
    spot = get_btc_price_brl()
    profit = execute_maker_strategy(spot)
    
    log(f"🎯 Ciclo concluído. Lucro potencial: R$ {profit}")

if __name__ == "__main__":
    main()

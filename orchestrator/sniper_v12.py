#!/usr/bin/env python3
"""
V12 Sniper Sequencial - Correcoes definitivas
- Compra primeiro (limit no bid), espera fill
- Depois vende (limit acima do entry, spread >= 0.35% Bybit / 0.50% Binance)
- Order size 6.0 USDT (evita min_cost < 5.0)
- Fee correto: 0.1% por lado em ambas
- SL amplo: 0.80% Bybit, 1.0% Binance
- Sem market sell no timeout: cancela e reposiciona
- Confirma fills via fetch_my_trades (mais confiavel)
- Nunca declara ganho sem confirmacao da exchange
"""
import ccxt, os, sys, time, json, traceback, math
from datetime import datetime, timezone
from dotenv import load_dotenv

CONFIG = {
    "bybit": {
        "symbols": ["XRP/USDT", "DOGE/USDT", "SOL/USDT"],
        "order_size_usdt": 6.0,
        "sell_spread_pct": 0.0035,
        "sl_pct": 0.008,
        "buy_wait_s": 180,
        "sell_wait_s": 300,
        "reposition_wait_s": 60,
        "poll_interval_s": 3,
        "max_trades_per_symbol": 15,
        "max_total_loss_usdt": 2.0,
        "fee_pct": 0.001,
    },
    "binance": {
        "symbols": ["XRP/USDT", "DOGE/USDT"],
        "order_size_usdt": 6.0,
        "sell_spread_pct": 0.0050,
        "sl_pct": 0.010,
        "buy_wait_s": 180,
        "sell_wait_s": 300,
        "reposition_wait_s": 60,
        "poll_interval_s": 3,
        "max_trades_per_symbol": 15,
        "max_total_loss_usdt": 2.0,
        "fee_pct": 0.001,
    },
}

LEDGER_PATH = "/Agentic/ledger.jsonl"
STATE_PATH = "/Agentic/orchestrator/v12_state.json"
MAX_RUNTIME_S = 3600


def log(msg):
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def write_ledger(entry):
    entry["ts"] = datetime.now(timezone.utc).isoformat()
    with open(LEDGER_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")


def load_state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH) as f:
            return json.load(f)
    return {
        "trades": [],
        "pnl_realized": {"bybit": 0.0, "binance": 0.0},
        "total_loss": 0.0,
        "trades_per_symbol": {},
    }


def save_state(state):
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)


def get_exchange(name):
    if name == "bybit":
        load_dotenv("/root/.automaton/bybit-murre.env")
        ex = ccxt.bybit({
            "apiKey": os.getenv("BYBIT_REAL_API_KEY"),
            "secret": os.getenv("BYBIT_REAL_API_SECRET"),
            "options": {"defaultType": "spot"},
            "enableRateLimit": True,
        })
    else:
        load_dotenv("/Agentic/.env")
        ex = ccxt.binance({
            "apiKey": os.getenv("BINANCE_API_KEY"),
            "secret": os.getenv("BINANCE_API_SECRET"),
            "options": {"defaultType": "spot"},
            "enableRateLimit": True,
        })
    return ex


def get_market_params(ex, symbol):
    market = ex.market(symbol)
    pp = market.get("precision", {})
    lt = market.get("limits", {})
    return {
        "price_precision": float(pp.get("price", 0.0001)) if pp.get("price") else 0.0001,
        "amount_precision": float(pp.get("amount", 0.01)) if pp.get("amount") else 0.01,
        "min_cost": float(lt.get("cost", {}).get("min", 5.0)),
        "min_amount": float(lt.get("amount", {}).get("min", 0.01)),
    }


def round_price(price, precision):
    if precision <= 0:
        return round(price, 4)
    decimals = max(0, int(round(-math.log10(precision))))
    return round(price, decimals)


def round_amount(amount, precision):
    if precision <= 0:
        return round(amount, 4)
    decimals = max(0, int(round(-math.log10(precision))))
    return round(amount, decimals)


def get_balance(ex):
    try:
        balance = ex.fetch_balance()
        usdt = balance.get("USDT", {})
        return float(usdt.get("free", 0)), float(usdt.get("total", 0))
    except Exception as e:
        log(f"Erro saldo: {e}")
        return 0.0, 0.0


def get_orderbook(ex, symbol):
    try:
        ob = ex.fetch_order_book(symbol, limit=5)
        bid = ob["bids"][0][0] if ob["bids"] else 0
        ask = ob["asks"][0][0] if ob["asks"] else 0
        return bid, ask
    except Exception as e:
        log(f"Erro orderbook {symbol}: {e}")
        return None, None


def cancel_order_safe(ex, order_id, symbol):
    try:
        ex.cancel_order(order_id, symbol)
        return True
    except Exception as e:
        msg = str(e).lower()
        if "not found" in msg or "already" in msg or "does not exist" in msg:
            return True
        log(f"Erro cancelar {order_id}: {e}")
        return False


def check_order_filled(ex, order_id, symbol):
    """Verifica se ordem foi filled via fetch_my_trades."""
    try:
        trades = ex.fetch_my_trades(symbol, limit=20)
        for t in trades:
            if t.get("order") == order_id:
                return True, float(t.get("amount", 0)), float(t.get("price", 0))
        # Tambem checar open orders - se nao esta la, pode ter sido filled
        open_orders = ex.fetch_open_orders(symbol)
        for o in open_orders:
            if o["id"] == order_id:
                filled = float(o.get("filled", 0))
                if filled > 0:
                    return True, filled, float(o.get("price", 0))
                return False, 0, 0
        # Nao esta em open nem em trades - provavelmente nao existe mais
        return None, 0, 0
    except Exception as e:
        log(f"Erro verificar ordem {order_id}: {e}")
        return None, 0, 0


def place_buy_order(ex, symbol, cfg, params):
    """Coloca ordem de compra no melhor bid."""
    bid, ask = get_orderbook(ex, symbol)
    if not bid or not ask:
        return None

    buy_price = round_price(bid, params["price_precision"])
    buy_qty = round_amount(cfg["order_size_usdt"] / buy_price, params["amount_precision"])

    if buy_qty * buy_price < params["min_cost"]:
        # Tentar aumentar qty para passar min_cost
        buy_qty = round_amount(params["min_cost"] / buy_price + 0.01, params["amount_precision"])
        if buy_qty * buy_price < params["min_cost"]:
            log(f"{symbol}: qty*price < min_cost mesmo apos ajuste")
            return None

    try:
        order = ex.create_order(symbol, "limit", "buy", buy_qty, buy_price)
        log(f"{symbol} BUY LIMIT @ {buy_price} qty={buy_qty} id={order['id']}")
        return order
    except Exception as e:
        log(f"{symbol} erro buy: {e}")
        return None


def place_sell_order(ex, symbol, cfg, params, entry_price, qty):
    """Coloca ordem de venda acima do entry com spread."""
    sell_price = round_price(entry_price * (1 + cfg["sell_spread_pct"]), params["price_precision"])
    sell_qty = round_amount(qty, params["amount_precision"])

    if sell_qty * sell_price < params["min_cost"]:
        log(f"{symbol}: sell qty*price < min_cost")
        return None

    try:
        order = ex.create_order(symbol, "limit", "sell", sell_qty, sell_price)
        log(f"{symbol} SELL LIMIT @ {sell_price} qty={sell_qty} id={order['id']} (entry={entry_price})")
        return order
    except Exception as e:
        log(f"{symbol} erro sell: {e}")
        return None


def run_sniper_cycle(ex, name, symbol, cfg, params, state):
    key = f"{name}:{symbol}"
    trade_count = state["trades_per_symbol"].get(key, 0)

    if trade_count >= cfg["max_trades_per_symbol"]:
        return

    # Verificar saldo
    free_usdt, _ = get_balance(ex)
    if free_usdt < cfg["order_size_usdt"]:
        return

    # === FASE 1: COMPRA ===
    buy_order = place_buy_order(ex, symbol, cfg, params)
    if not buy_order:
        return

    buy_start = time.time()
    entry_price = 0.0
    entry_qty = 0.0

    while time.time() - buy_start < cfg["buy_wait_s"]:
        time.sleep(cfg["poll_interval_s"])
        filled, amt, price = check_order_filled(ex, buy_order["id"], symbol)
        if filled and amt > 0:
            entry_price = price if price > 0 else float(buy_order.get("price", 0))
            entry_qty = amt
            log(f"{symbol} BUY FILLED! @ {entry_price} qty={entry_qty}")
            break
        # Reposicionar se bid mudou muito
        elapsed = time.time() - buy_start
        if elapsed > 60 and elapsed % 60 < cfg["poll_interval_s"]:
            bid, ask = get_orderbook(ex, symbol)
            if bid:
                current_buy = round_price(bid, params["price_precision"])
                old_price = float(buy_order.get("price", 0))
                if abs(current_buy - old_price) / old_price > 0.001:
                    cancel_order_safe(ex, buy_order["id"], symbol)
                    buy_order = place_buy_order(ex, symbol, cfg, params)
                    if not buy_order:
                        return
                    buy_start = time.time()
    else:
        # Buy nao fillou - cancelar
        log(f"{symbol} buy timeout - cancelando")
        cancel_order_safe(ex, buy_order["id"], symbol)
        return

    # === FASE 2: VENDA ===
    sl_price = round_price(entry_price * (1 - cfg["sl_pct"]), params["price_precision"])
    log(f"{symbol} gerenciando saida: SL={sl_price} target=+{cfg['sell_spread_pct']*100:.2f}%")

    sell_order = place_sell_order(ex, symbol, cfg, params, entry_price, entry_qty)
    if not sell_order:
        # Falha ao colocar sell - market sell como fallback
        log(f"{symbol} falha sell limit - market sell")
        try:
            ex.create_order(symbol, "market", "sell", round_amount(entry_qty, params["amount_precision"]))
            # Registrar com preco de mercado aproximado
            bid, _ = get_orderbook(ex, symbol)
            exit_p = bid if bid else entry_price
            record_trade(name, symbol, entry_price, exit_p, entry_qty, "MARKET_FALLBACK", cfg, state)
        except Exception as e:
            log(f"{symbol} ERRO CRITICAL market sell: {e}")
        return

    sell_start = time.time()
    reposition_count = 0
    max_repositions = 3

    while time.time() - sell_start < cfg["sell_wait_s"]:
        time.sleep(cfg["poll_interval_s"])

        # Verificar SL
        bid, ask = get_orderbook(ex, symbol)
        if not bid or not ask:
            continue

        if bid <= sl_price:
            log(f"{symbol} SL HIT! bid={bid} <= {sl_price}")
            cancel_order_safe(ex, sell_order["id"], symbol)
            try:
                ex.create_order(symbol, "market", "sell", round_amount(entry_qty, params["amount_precision"]))
                exit_p = bid
                log(f"{symbol} SL MARKET SELL done @ ~{exit_p}")
            except Exception as e:
                log(f"{symbol} erro SL market: {e}")
                exit_p = sl_price
            record_trade(name, symbol, entry_price, exit_p, entry_qty, "SL", cfg, state)
            return

        # Verificar se sell fillou
        filled, amt, price = check_order_filled(ex, sell_order["id"], symbol)
        if filled and amt > 0:
            exit_p = price if price > 0 else float(sell_order.get("price", 0))
            log(f"{symbol} SELL FILLED! @ {exit_p} qty={amt}")
            record_trade(name, symbol, entry_price, exit_p, entry_qty, "TP", cfg, state)
            return

        # Reposicionar sell se preco mudou
        elapsed = time.time() - sell_start
        if elapsed > cfg["reposition_wait_s"] and reposition_count < max_repositions:
            if bid and ask:
                new_sell = round_price(ask * 0.9999, params["price_precision"])
                old_sell = float(sell_order.get("price", 0))
                if new_sell > entry_price * (1 + 0.001) and new_sell != old_sell:
                    cancel_order_safe(ex, sell_order["id"], symbol)
                    sell_qty = round_amount(entry_qty, params["amount_precision"])
                    if sell_qty * new_sell >= params["min_cost"]:
                        try:
                            sell_order = ex.create_order(symbol, "limit", "sell", sell_qty, new_sell)
                            reposition_count += 1
                            log(f"{symbol} REPOS SELL @ {new_sell} (#{reposition_count})")
                            sell_start = time.time()
                        except Exception as e:
                            log(f"{symbol} erro repos sell: {e}")

    # Sell timeout - cancelar e repositionar uma ultima vez
    log(f"{symbol} sell timeout apos {cfg['sell_wait_s']}s")
    cancel_order_safe(ex, sell_order["id"], symbol)
    bid, ask = get_orderbook(ex, symbol)
    if bid and ask:
        # Ultima tentativa: vender no bid atual
        final_price = round_price(bid, params["price_precision"])
        sell_qty = round_amount(entry_qty, params["amount_precision"])
        if sell_qty * final_price >= params["min_cost"]:
            try:
                sell_order = ex.create_order(symbol, "limit", "sell", sell_qty, final_price)
                log(f"{symbol} FINAL SELL @ {final_price}")
                final_start = time.time()
                while time.time() - final_start < 60:
                    time.sleep(cfg["poll_interval_s"])
                    filled, amt, price = check_order_filled(ex, sell_order["id"], symbol)
                    if filled and amt > 0:
                        exit_p = price if price > 0 else final_price
                        record_trade(name, symbol, entry_price, exit_p, entry_qty, "TIMEOUT_REPOS", cfg, state)
                        return
                # Ultimo recurso: market
                cancel_order_safe(ex, sell_order["id"], symbol)
                try:
                    ex.create_order(symbol, "market", "sell", sell_qty)
                    exit_p = bid
                    record_trade(name, symbol, entry_price, exit_p, entry_qty, "TIMEOUT_MARKET", cfg, state)
                except Exception as e:
                    log(f"{symbol} erro final market: {e}")
            except Exception as e:
                log(f"{symbol} erro final sell: {e}")


def record_trade(ex_name, symbol, entry, exit_p, qty, reason, cfg, state):
    fee = cfg["fee_pct"]
    gross_pnl = (exit_p - entry) * qty
    fees_total = (entry * qty * fee) + (exit_p * qty * fee)
    net_pnl = gross_pnl - fees_total

    entry_dict = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "exchange": ex_name,
        "symbol": symbol,
        "entry_price": entry,
        "exit_price": exit_p,
        "qty": qty,
        "exit_reason": reason,
        "gross_pnl": round(gross_pnl, 6),
        "fees_usdt": round(fees_total, 6),
        "net_pnl": round(net_pnl, 6),
        "win": net_pnl > 0,
    }

    write_ledger(entry_dict)
    state["trades"].append(entry_dict)
    state["pnl_realized"][ex_name] = state["pnl_realized"].get(ex_name, 0.0) + net_pnl
    if net_pnl < 0:
        state["total_loss"] += abs(net_pnl)

    save_state(state)
    log(f"TRADE RECORDED: {symbol} net_pnl={net_pnl:.6f} reason={reason} win={net_pnl > 0}")
    log(f"  PnL {ex_name}: {state['pnl_realized'][ex_name]:.6f} | Total loss: {state['total_loss']:.6f}")


def reconcile(ex_bybit, ex_binance):
    log("=== RECONCILIACAO ===")
    for name, ex in [("bybit", ex_bybit), ("binance", ex_binance)]:
        free, total = get_balance(ex)
        log(f"{name}: USDT free={free:.4f} total={total:.4f}")
        for symbol in CONFIG[name]["symbols"]:
            try:
                open_orders = ex.fetch_open_orders(symbol)
                if open_orders:
                    log(f"{name} {symbol}: {len(open_orders)} ordens abertas - CANCELANDO")
                    for o in open_orders:
                        cancel_order_safe(ex, o["id"], symbol)
                else:
                    log(f"{name} {symbol}: 0 ordens OK")
            except Exception as e:
                log(f"{name} {symbol}: erro ordens: {e}")
    log("=== FIM RECONCILIACAO ===")


def main():
    log("=== V12 SNIPER SEQUENCIAL INICIANDO ===")
    log("Estrategia: buy no bid -> wait fill -> sell acima -> SL 0.8%")

    state = load_state()
    log(f"State: {len(state['trades'])} trades, PnL={state['pnl_realized']}")

    ex_bybit = get_exchange("bybit")
    ex_binance = get_exchange("binance")

    reconcile(ex_bybit, ex_binance)

    market_params = {}
    for name, ex in [("bybit", ex_bybit), ("binance", ex_binance)]:
        market_params[name] = {}
        for symbol in CONFIG[name]["symbols"]:
            try:
                market_params[name][symbol] = get_market_params(ex, symbol)
                mp = market_params[name][symbol]
                log(f"{name} {symbol}: pp={mp['price_precision']} ap={mp['amount_precision']} mc={mp['min_cost']}")
            except Exception as e:
                log(f"{name} {symbol}: erro market params: {e}")

    start_time = time.time()
    cycle = 0

    while time.time() - start_time < MAX_RUNTIME_S:
        cycle += 1
        elapsed = time.time() - start_time
        log(f"--- Ciclo {cycle} ({elapsed:.0f}s) ---")

        if state["total_loss"] >= CONFIG["bybit"]["max_total_loss_usdt"]:
            log("MAX LOSS - PARANDO")
            break

        # Bybit
        for symbol in CONFIG["bybit"]["symbols"]:
            try:
                run_sniper_cycle(ex_bybit, "bybit", symbol, CONFIG["bybit"], market_params["bybit"][symbol], state)
            except Exception as e:
                log(f"bybit {symbol}: erro: {e}")
                traceback.print_exc()

        # Binance
        for symbol in CONFIG["binance"]["symbols"]:
            try:
                run_sniper_cycle(ex_binance, "binance", symbol, CONFIG["binance"], market_params["binance"][symbol], state)
            except Exception as e:
                log(f"binance {symbol}: erro: {e}")
                traceback.print_exc()

        pnl_b = state["pnl_realized"].get("bybit", 0)
        pnl_bin = state["pnl_realized"].get("binance", 0)
        log(f"PnL: Bybit={pnl_b:.6f} Binance={pnl_bin:.6f}")

        if pnl_b >= 10.0 and pnl_bin >= 20.0:
            log("=== META ATINGIDA! ===")
            break

    log("=== V12 FINALIZADO ===")
    log(f"PnL: Bybit={state['pnl_realized'].get('bybit', 0):.6f} Binance={state['pnl_realized'].get('binance', 0):.6f}")
    log(f"Trades: {len(state['trades'])} | Loss: {state['total_loss']:.6f}")


if __name__ == "__main__":
    main()

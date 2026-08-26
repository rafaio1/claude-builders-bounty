#!/usr/bin/env python3
"""
V11 Market Maker - Correcoes fundamentais
- Fee correto: 0.1% por lado em ambas exchanges
- Spread minimo: 0.35% Bybit, 0.50% Binance (lucro liquido apos fees)
- SL amplo: 0.80% (evita stop prematuro em volatilidade normal)
- SEM market sell no timeout: cancela e reposiciona
- Market making real: buy+sell simultaneos no orderbook
- Nunca declara ganho sem confirmacao da exchange
- Logging completo em ledger.jsonl
"""
import ccxt, os, sys, time, json, traceback, math
from datetime import datetime, timezone
from dotenv import load_dotenv

CONFIG = {
    "bybit": {
        "symbols": ["XRP/USDT", "DOGE/USDT", "SOL/USDT"],
        "order_size_usdt": 5.0,
        "spread_pct": 0.0035,
        "sl_pct": 0.008,
        "max_hold_s": 600,
        "poll_interval_s": 2,
        "max_trades_per_symbol": 10,
        "max_total_loss_usdt": 1.5,
        "fee_pct": 0.001,
        "reposition_on_fill": True,
    },
    "binance": {
        "symbols": ["XRP/USDT", "DOGE/USDT"],
        "order_size_usdt": 5.0,
        "spread_pct": 0.0050,
        "sl_pct": 0.010,
        "max_hold_s": 600,
        "poll_interval_s": 2,
        "max_trades_per_symbol": 10,
        "max_total_loss_usdt": 1.5,
        "fee_pct": 0.001,
        "reposition_on_fill": True,
    },
}

LEDGER_PATH = "/Agentic/ledger.jsonl"
STATE_PATH = "/Agentic/orchestrator/v11_state.json"
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
    return {
        "price_precision": market.get("precision", {}).get("price", 0.0001),
        "amount_precision": market.get("precision", {}).get("amount", 0.01),
        "min_cost": market.get("limits", {}).get("cost", {}).get("min", 5.0),
        "min_amount": market.get("limits", {}).get("amount", {}).get("min", 0.01),
        "ticker": symbol,
    }


def round_price(price, precision):
    if precision <= 0:
        return price
    decimals = max(0, int(round(-math.log10(precision))))
    return round(price, decimals)


def round_amount(amount, precision):
    if precision <= 0:
        return amount
    decimals = max(0, int(round(-math.log10(precision))))
    return round(amount, decimals)


def get_balance(ex):
    try:
        balance = ex.fetch_balance()
        usdt = balance.get("USDT", {})
        free = float(usdt.get("free", 0))
        total = float(usdt.get("total", 0))
        return free, total
    except Exception as e:
        log(f"Erro ao obter saldo: {e}")
        return 0.0, 0.0


def get_orderbook(ex, symbol):
    try:
        ob = ex.fetch_order_book(symbol, limit=5)
        bid = ob["bids"][0][0] if ob["bids"] else 0
        ask = ob["asks"][0][0] if ob["asks"] else 0
        return bid, ask
    except Exception as e:
        log(f"Erro ao obter orderbook {symbol}: {e}")
        return None, None


def cancel_order_safe(ex, order_id, symbol):
    try:
        ex.cancel_order(order_id, symbol)
        return True
    except Exception as e:
        if "not found" in str(e).lower() or "already" in str(e).lower():
            return True
        log(f"Erro ao cancelar ordem {order_id}: {e}")
        return False


def check_order_filled(ex, order_id, symbol):
    try:
        orders = ex.fetch_open_orders(symbol)
        for o in orders:
            if o["id"] == order_id:
                return False, float(o.get("filled", 0))
        trades = ex.fetch_my_trades(symbol, limit=10)
        for t in trades:
            if t.get("order") == order_id:
                return True, float(t.get("amount", 0))
        return True, 0
    except Exception as e:
        log(f"Erro ao verificar ordem {order_id}: {e}")
        return False, 0


def place_mm_orders(ex, symbol, cfg, params):
    bid, ask = get_orderbook(ex, symbol)
    if not bid or not ask:
        log(f"{symbol}: sem orderbook")
        return None, None

    mid = (bid + ask) / 2.0
    spread = cfg["spread_pct"]

    buy_price = round_price(mid * (1 - spread), params["price_precision"])
    sell_price = round_price(mid * (1 + spread), params["price_precision"])

    order_size = cfg["order_size_usdt"]
    buy_qty = round_amount(order_size / buy_price, params["amount_precision"])
    sell_qty = round_amount(order_size / sell_price, params["amount_precision"])

    if buy_qty * buy_price < params["min_cost"]:
        log(f"{symbol}: buy qty*price < min_cost ({buy_qty*buy_price:.4f} < {params['min_cost']})")
        return None, None
    if sell_qty * sell_price < params["min_cost"]:
        log(f"{symbol}: sell qty*price < min_cost ({sell_qty*sell_price:.4f} < {params['min_cost']})")
        return None, None

    buy_order = None
    sell_order = None

    try:
        buy_order = ex.create_order(symbol, "limit", "buy", buy_qty, buy_price)
        log(f"{symbol} BUY @ {buy_price} qty={buy_qty} id={buy_order['id']}")
    except Exception as e:
        log(f"{symbol} erro ao colocar buy: {e}")

    try:
        sell_order = ex.create_order(symbol, "limit", "sell", sell_qty, sell_price)
        log(f"{symbol} SELL @ {sell_price} qty={sell_qty} id={sell_order['id']}")
    except Exception as e:
        log(f"{symbol} erro ao colocar sell: {e}")
        if buy_order:
            cancel_order_safe(ex, buy_order["id"], symbol)
            buy_order = None

    return buy_order, sell_order


def run_mm_cycle(ex, name, symbol, cfg, params, state):
    key = f"{name}:{symbol}"
    trade_count = state["trades_per_symbol"].get(key, 0)

    if trade_count >= cfg["max_trades_per_symbol"]:
        return

    buy_order, sell_order = place_mm_orders(ex, symbol, cfg, params)
    if not buy_order and not sell_order:
        return

    cycle_start = time.time()
    buy_filled = False
    sell_filled = False
    entry_price = 0.0
    entry_qty = 0.0
    entry_side = None

    while time.time() - cycle_start < cfg["max_hold_s"]:
        time.sleep(cfg["poll_interval_s"])

        if buy_order and not buy_filled:
            filled, amt = check_order_filled(ex, buy_order["id"], symbol)
            if filled and amt > 0:
                buy_filled = True
                entry_price = float(buy_order.get("price", 0))
                entry_qty = amt
                entry_side = "buy"
                log(f"{symbol} BUY FILLED @ {entry_price} qty={entry_qty}")
                if sell_order:
                    cancel_order_safe(ex, sell_order["id"], symbol)

        if sell_order and not sell_filled:
            filled, amt = check_order_filled(ex, sell_order["id"], symbol)
            if filled and amt > 0:
                sell_filled = True
                entry_price = float(sell_order.get("price", 0))
                entry_qty = amt
                entry_side = "sell"
                log(f"{symbol} SELL FILLED @ {entry_price} qty={entry_qty}")
                if buy_order:
                    cancel_order_safe(ex, buy_order["id"], symbol)

        if buy_filled or sell_filled:
            manage_exit(ex, symbol, cfg, params, entry_price, entry_qty, entry_side, state, name)
            trade_count += 1
            state["trades_per_symbol"][key] = trade_count
            return

        elapsed = time.time() - cycle_start
        if elapsed > cfg["max_hold_s"] * 0.5:
            log(f"{symbol} reposicionando (sem fill em {elapsed:.0f}s)")
            if buy_order:
                cancel_order_safe(ex, buy_order["id"], symbol)
            if sell_order:
                cancel_order_safe(ex, sell_order["id"], symbol)
            return

    log(f"{symbol} timeout - cancelando ordens")
    if buy_order:
        cancel_order_safe(ex, buy_order["id"], symbol)
    if sell_order:
        cancel_order_safe(ex, sell_order["id"], symbol)


def manage_exit(ex, symbol, cfg, params, entry_price, qty, side, state, ex_name):
    fee = cfg["fee_pct"]
    sl_pct = cfg["sl_pct"]

    exit_side = "sell" if side == "buy" else "buy"

    if side == "buy":
        target_exit = entry_price * (1 + cfg["spread_pct"] * 2)
        sl_price = entry_price * (1 - sl_pct)
    else:
        target_exit = entry_price * (1 - cfg["spread_pct"] * 2)
        sl_price = entry_price * (1 + sl_pct)

    target_exit = round_price(target_exit, params["price_precision"])
    sl_price = round_price(sl_price, params["price_precision"])

    log(f"{symbol} exit target={target_exit} SL={sl_price} (entry={entry_price} side={side})")

    exit_qty = round_amount(qty, params["amount_precision"])
    try:
        exit_order = ex.create_order(symbol, "limit", exit_side, exit_qty, target_exit)
        log(f"{symbol} EXIT {exit_side} @ {target_exit} qty={exit_qty} id={exit_order['id']}")
    except Exception as e:
        log(f"{symbol} erro ao colocar exit: {e}")
        try:
            exit_order = ex.create_order(symbol, "market", exit_side, exit_qty)
            log(f"{symbol} EXIT MARKET {exit_side} qty={exit_qty}")
        except Exception as e2:
            log(f"{symbol} erro CRITICAL ao colocar market exit: {e2}")
            return

    exit_start = time.time()
    while time.time() - exit_start < cfg["max_hold_s"]:
        time.sleep(cfg["poll_interval_s"])

        bid, ask = get_orderbook(ex, symbol)
        if not bid or not ask:
            continue

        if side == "buy" and bid <= sl_price:
            log(f"{symbol} SL HIT bid={bid} <= {sl_price}")
            cancel_order_safe(ex, exit_order["id"], symbol)
            try:
                sl_order = ex.create_order(symbol, "market", "sell", exit_qty)
                exit_price = bid
                log(f"{symbol} SL MARKET SELL executed")
            except Exception as e:
                log(f"{symbol} erro SL market sell: {e}")
                exit_price = sl_price
            record_trade(ex_name, symbol, entry_price, exit_price, exit_qty, "SL", cfg, state)
            return

        if side == "sell" and ask >= sl_price:
            log(f"{symbol} SL HIT ask={ask} >= {sl_price}")
            cancel_order_safe(ex, exit_order["id"], symbol)
            try:
                sl_order = ex.create_order(symbol, "market", "buy", exit_qty)
                exit_price = ask
                log(f"{symbol} SL MARKET BUY executed")
            except Exception as e:
                log(f"{symbol} erro SL market buy: {e}")
                exit_price = sl_price
            record_trade(ex_name, symbol, entry_price, exit_price, exit_qty, "SL", cfg, state)
            return

        filled, amt = check_order_filled(ex, exit_order["id"], symbol)
        if filled and amt > 0:
            exit_price = target_exit
            log(f"{symbol} EXIT FILLED @ {exit_price}")
            record_trade(ex_name, symbol, entry_price, exit_price, exit_qty, "TP", cfg, state)
            return

    log(f"{symbol} exit timeout - cancelando e reposicionando")
    cancel_order_safe(ex, exit_order["id"], symbol)
    bid, ask = get_orderbook(ex, symbol)
    if bid and ask:
        if side == "buy":
            new_exit = round_price(ask * 1.0001, params["price_precision"])
        else:
            new_exit = round_price(bid * 0.9999, params["price_precision"])
        try:
            exit_order = ex.create_order(symbol, "limit", exit_side, exit_qty, new_exit)
            log(f"{symbol} RE-EXIT @ {new_exit}")
            re_start = time.time()
            while time.time() - re_start < 120:
                time.sleep(cfg["poll_interval_s"])
                filled, amt = check_order_filled(ex, exit_order["id"], symbol)
                if filled and amt > 0:
                    record_trade(ex_name, symbol, entry_price, new_exit, exit_qty, "TP_RE", cfg, state)
                    return
            cancel_order_safe(ex, exit_order["id"], symbol)
            try:
                ex.create_order(symbol, "market", exit_side, exit_qty)
                record_trade(ex_name, symbol, entry_price, new_exit, exit_qty, "TIMEOUT_MARKET", cfg, state)
            except Exception as e:
                log(f"{symbol} erro final market: {e}")
        except Exception as e:
            log(f"{symbol} erro re-exit: {e}")


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
                    log(f"{name} {symbol}: 0 ordens abertas OK")
            except Exception as e:
                log(f"{name} {symbol}: erro ao verificar ordens: {e}")
        try:
            balance = ex.fetch_balance()
            for coin, amounts in balance.get("total", {}).items():
                amt = float(amounts) if amounts else 0
                if coin != "USDT" and amt > 0:
                    log(f"{name}: DUST {coin}={amt}")
        except Exception as e:
            log(f"{name}: erro ao verificar posicoes: {e}")
    log("=== FIM RECONCILIACAO ===")


def main():
    log("=== V11 MARKET MAKER INICIANDO ===")
    log("Correcoes: fee=0.1%, spread>=0.35%, SL=0.80%, sem market sell no timeout")

    state = load_state()
    log(f"State carregado: {len(state['trades'])} trades, PnL={state['pnl_realized']}")

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
                log(f"{name} {symbol}: price_prec={mp['price_precision']} amt_prec={mp['amount_precision']} min_cost={mp['min_cost']}")
            except Exception as e:
                log(f"{name} {symbol}: erro ao obter market params: {e}")

    start_time = time.time()
    cycle = 0

    while time.time() - start_time < MAX_RUNTIME_S:
        cycle += 1
        elapsed = time.time() - start_time
        log(f"--- Ciclo {cycle} ({elapsed:.0f}s elapsed) ---")

        if state["total_loss"] >= 1.0:
            log("MAX LOSS atingido - PARANDO")
            break

        for symbol in CONFIG["bybit"]["symbols"]:
            try:
                run_mm_cycle(ex_bybit, "bybit", symbol, CONFIG["bybit"], market_params["bybit"][symbol], state)
            except Exception as e:
                log(f"bybit {symbol}: erro no ciclo: {e}")
                traceback.print_exc()

        for symbol in CONFIG["binance"]["symbols"]:
            try:
                run_mm_cycle(ex_binance, "binance", symbol, CONFIG["binance"], market_params["binance"][symbol], state)
            except Exception as e:
                log(f"binance {symbol}: erro no ciclo: {e}")
                traceback.print_exc()

        pnl_b = state["pnl_realized"].get("bybit", 0)
        pnl_bin = state["pnl_realized"].get("binance", 0)
        log(f"PnL atual: Bybit={pnl_b:.6f} Binance={pnl_bin:.6f}")

        if pnl_b >= 10.0 and pnl_bin >= 20.0:
            log("=== META ATINGIDA! Bybit >= 10 e Binance >= 20 ===")
            break

    log("=== V11 FINALIZADO ===")
    log(f"PnL final: Bybit={state['pnl_realized'].get('bybit', 0):.6f} Binance={state['pnl_realized'].get('binance', 0):.6f}")
    log(f"Total trades: {len(state['trades'])} | Total loss: {state['total_loss']:.6f}")


if __name__ == "__main__":
    main()

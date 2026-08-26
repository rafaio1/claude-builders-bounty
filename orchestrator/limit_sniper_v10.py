#!/usr/bin/env python3
"""
V10 Limit Sniper - Grid Maker Corrigido
- Fix: fetch_open_orders/fetch_closed_orders em vez de fetch_order
- Multi-simbolo simultaneo
- Bybit: 0% fee, spread 0.08%
- Binance: 0.1% fee, spread 0.40%
- Controles deterministicos: SL, timeout, max_trades, max_loss
- Nunca declara ganho sem confirmacao da exchange
"""
import ccxt, os, sys, time, json, traceback
from datetime import datetime, timezone
from dotenv import load_dotenv

CONFIG = {
    "bybit": {
        "symbols": ["XRP/USDT", "DOGE/USDT", "SOL/USDT", "ADA/USDT"],
        "order_size_usdt": 5.0,
        "buy_spread_pct": 0.0001,
        "sell_spread_pct": 0.0008,
        "sl_pct": 0.0030,
        "buy_wait_s": 40,
        "sell_hold_s": 120,
        "poll_interval_s": 3,
        "max_trades_per_symbol": 3,
        "max_total_loss_usdt": 1.0,
        "fee_pct": 0.0,
    },
    "binance": {
        "symbols": ["XRP/USDT", "DOGE/USDT"],
        "order_size_usdt": 5.0,
        "buy_spread_pct": 0.0002,
        "sell_spread_pct": 0.0040,
        "sl_pct": 0.0050,
        "buy_wait_s": 50,
        "sell_hold_s": 150,
        "poll_interval_s": 3,
        "max_trades_per_symbol": 3,
        "max_total_loss_usdt": 1.0,
        "fee_pct": 0.001,
    },
}

LEDGER_PATH = "/Agentic/ledger.jsonl"
STATE_PATH = "/Agentic/orchestrator/v10_state.json"
MAX_RUNTIME_S = 1800


def log(msg):
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def write_ledger(entry):
    with open(LEDGER_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")


def load_state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH) as f:
            return json.load(f)
    return {"trades": [], "pnl_realized": {"bybit": 0.0, "binance": 0.0}, "total_loss": 0.0}


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
        load_dotenv("/Agentic/.env", override=True)
        ex = ccxt.binance({
            "apiKey": os.getenv("BINANCE_API_KEY"),
            "secret": os.getenv("BINANCE_API_SECRET"),
            "enableRateLimit": True,
        })
    ex.load_markets()
    return ex


def get_precision(ex, sym):
    m = ex.markets[sym]
    return {
        "price_prec": m.get("precision", {}).get("price", 0.0001),
        "amount_prec": m.get("precision", {}).get("amount", 0.01),
        "min_cost": m.get("limits", {}).get("cost", {}).get("min", 5.0),
        "min_amt": m.get("limits", {}).get("amount", {}).get("min", 0.01),
    }


def round_to_step(value, step):
    if step >= 1:
        return round(value / step) * step
    return round(value / step) * step


def get_best_bid_ask(ex, sym):
    ob = ex.fetch_order_book(sym, limit=5)
    return ob["bids"][0][0], ob["asks"][0][0]


def cancel_all_open(ex, sym):
    try:
        orders = ex.fetch_open_orders(sym)
        for o in orders:
            ex.cancel_order(o["id"], sym)
            log(f"  Cancelled {o['id']} ({o['side']} {o['amount']} {sym})")
    except Exception as e:
        log(f"  Cancel error: {e}")


def check_order_status(ex, order_id, sym):
    """FIX V10: usa fetch_open_orders e fetch_closed_orders em vez de fetch_order"""
    try:
        open_orders = ex.fetch_open_orders(sym)
        for o in open_orders:
            if o["id"] == order_id:
                return "open"
    except Exception as e:
        log(f"  fetch_open_orders error: {e}")
    try:
        closed = ex.fetch_closed_orders(sym, limit=50)
        for o in closed:
            if o["id"] == order_id:
                return o["status"]
    except Exception as e:
        log(f"  fetch_closed_orders error: {e}")
    return "unknown"


def get_filled_order(ex, order_id, sym):
    try:
        closed = ex.fetch_closed_orders(sym, limit=50)
        for o in closed:
            if o["id"] == order_id:
                return o
    except:
        pass
    return None


def execute_trade(ex, ex_name, sym, cfg, state):
    prec = get_precision(ex, sym)

    best_bid, best_ask = get_best_bid_ask(ex, sym)
    mid = (best_bid + best_ask) / 2

    buy_price = best_bid + (best_ask - best_bid) * cfg["buy_spread_pct"] * 100
    buy_price = round_to_step(buy_price, prec["price_prec"])

    buy_value = cfg["order_size_usdt"]
    buy_amount = round_to_step(buy_value / buy_price, prec["amount_prec"])

    if buy_amount < prec["min_amt"]:
        log(f"  [{ex_name}] {sym} amount {buy_amount} < min {prec['min_amt']}, skip")
        return 0.0, "skip_min_amt"

    if buy_amount * buy_price < prec["min_cost"]:
        log(f"  [{ex_name}] {sym} cost {buy_amount * buy_price:.2f} < min_cost {prec['min_cost']}, skip")
        return 0.0, "skip_min_cost"

    log(f"  [{ex_name}] BUY LIMIT {sym} {buy_amount} @ {buy_price} (value={buy_amount*buy_price:.2f})")
    try:
        order = ex.create_order(sym, "limit", "buy", buy_amount, buy_price)
        order_id = order["id"]
        log(f"  [{ex_name}] Buy order placed: {order_id}")
    except Exception as e:
        log(f"  [{ex_name}] Buy order FAILED: {e}")
        return 0.0, "buy_failed"

    buy_filled = False
    fill_start = time.time()
    while time.time() - fill_start < cfg["buy_wait_s"]:
        status = check_order_status(ex, order_id, sym)
        if status == "closed":
            buy_filled = True
            break
        elif status in ("canceled", "expired"):
            log(f"  [{ex_name}] Buy order {status}")
            break
        time.sleep(cfg["poll_interval_s"])

    if not buy_filled:
        try:
            ex.cancel_order(order_id, sym)
        except:
            pass
        log(f"  [{ex_name}] Buy TIMEOUT, cancelled")
        return 0.0, "buy_timeout"

    filled_order = get_filled_order(ex, order_id, sym)
    if not filled_order:
        log(f"  [{ex_name}] Buy filled but cannot get details, skip sell")
        return 0.0, "buy_no_details"

    actual_buy_price = float(filled_order.get("average") or filled_order.get("price") or buy_price)
    actual_buy_amount = float(filled_order.get("filled") or filled_order.get("amount") or buy_amount)

    fee_buy = actual_buy_amount * actual_buy_price * cfg["fee_pct"]
    log(f"  [{ex_name}] BUY FILLED: {actual_buy_amount} @ {actual_buy_price} (fee={fee_buy:.6f})")

    sell_price = actual_buy_price * (1 + cfg["sell_spread_pct"])
    sell_price = round_to_step(sell_price, prec["price_prec"])
    sell_amount = round_to_step(actual_buy_amount, prec["amount_prec"])

    sl_price = actual_buy_price * (1 - cfg["sl_pct"])
    sl_price = round_to_step(sl_price, prec["price_prec"])

    log(f"  [{ex_name}] SELL LIMIT {sym} {sell_amount} @ {sell_price} (SL={sl_price})")

    try:
        sell_order = ex.create_order(sym, "limit", "sell", sell_amount, sell_price)
        sell_order_id = sell_order["id"]
        log(f"  [{ex_name}] Sell order placed: {sell_order_id}")
    except Exception as e:
        log(f"  [{ex_name}] Sell order FAILED: {e}, dumping at market")
        try:
            sell_order = ex.create_order(sym, "market", "sell", sell_amount)
            sell_order_id = sell_order["id"]
            log(f"  [{ex_name}] Market sell fallback: {sell_order_id}")
        except Exception as e2:
            log(f"  [{ex_name}] Market sell also FAILED: {e2}")
            return 0.0, "sell_failed_and_market_failed"

    sell_start = time.time()
    sell_result = "sell_timeout"

    while time.time() - sell_start < cfg["sell_hold_s"]:
        status = check_order_status(ex, sell_order_id, sym)
        if status == "closed":
            sell_result = "sell_filled"
            break
        elif status in ("canceled", "expired"):
            sell_result = f"sell_{status}"
            break

        try:
            ticker = ex.fetch_ticker(sym)
            current_price = ticker["last"]
            if current_price <= sl_price:
                log(f"  [{ex_name}] SL TRIGGERED: price={current_price} <= {sl_price}")
                try:
                    ex.cancel_order(sell_order_id, sym)
                except:
                    pass
                try:
                    sl_order = ex.create_order(sym, "market", "sell", sell_amount)
                    sell_order_id = sl_order["id"]
                    log(f"  [{ex_name}] Market sell (SL): {sell_order_id}")
                    time.sleep(3)
                    sl_filled = get_filled_order(ex, sell_order_id, sym)
                    if sl_filled:
                        sell_result = "sl_triggered"
                        break
                except Exception as e:
                    log(f"  [{ex_name}] Market sell SL FAILED: {e}")
        except Exception as e:
            log(f"  [{ex_name}] Ticker check error: {e}")

        time.sleep(cfg["poll_interval_s"])

    if sell_result not in ("sell_filled", "sl_triggered"):
        try:
            ex.cancel_order(sell_order_id, sym)
        except:
            pass
        try:
            final_sell = ex.create_order(sym, "market", "sell", sell_amount)
            sell_order_id = final_sell["id"]
            time.sleep(3)
            sell_result = "market_sell_timeout"
        except Exception as e:
            log(f"  [{ex_name}] Final market sell FAILED: {e}")
            return 0.0, sell_result

    sell_filled_order = get_filled_order(ex, sell_order_id, sym)
    if not sell_filled_order:
        log(f"  [{ex_name}] Sell filled but no details")
        return 0.0, sell_result + "_no_details"

    actual_sell_price = float(sell_filled_order.get("average") or sell_filled_order.get("price") or sell_price)
    actual_sell_amount = float(sell_filled_order.get("filled") or sell_filled_order.get("amount") or sell_amount)

    fee_sell = actual_sell_amount * actual_sell_price * cfg["fee_pct"]

    gross_pnl = (actual_sell_price - actual_buy_price) * actual_sell_amount
    total_fees = fee_buy + fee_sell
    net_pnl = gross_pnl - total_fees

    log(f"  [{ex_name}] TRADE COMPLETE: buy@{actual_buy_price} sell@{actual_sell_price}")
    log(f"  [{ex_name}] Gross={gross_pnl:.6f} Fees={total_fees:.6f} NET={net_pnl:.6f} USDT")

    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "exchange": ex_name,
        "symbol": sym,
        "side": "buy+sell",
        "buy_price": actual_buy_price,
        "sell_price": actual_sell_price,
        "amount": actual_sell_amount,
        "gross_pnl": round(gross_pnl, 6),
        "fees": round(total_fees, 6),
        "net_pnl": round(net_pnl, 6),
        "result": sell_result,
        "version": "v10",
    }
    write_ledger(entry)

    state["trades"].append(entry)
    state["pnl_realized"][ex_name] += net_pnl
    if net_pnl < 0:
        state["total_loss"] += abs(net_pnl)
    save_state(state)

    return net_pnl, sell_result


def main():
    log("=" * 60)
    log("V10 Limit Sniper - INICIO")
    log("=" * 60)

    state = load_state()
    log(f"State: trades={len(state['trades'])} pnl_bybit={state['pnl_realized']['bybit']:.4f} pnl_binance={state['pnl_realized']['binance']:.4f}")

    try:
        bybit = get_exchange("bybit")
        log("Bybit connected")
    except Exception as e:
        log(f"Bybit connection FAILED: {e}")
        bybit = None

    try:
        binance = get_exchange("binance")
        log("Binance connected")
    except Exception as e:
        log(f"Binance connection FAILED: {e}")
        binance = None

    if not bybit and not binance:
        log("FATAL: No exchange connected")
        sys.exit(1)

    if bybit:
        try:
            bal = bybit.fetch_balance()
            usdt_free = float(bal.get("USDT", {}).get("free", 0))
            log(f"Bybit USDT: {usdt_free}")
        except:
            log("Bybit balance check failed")

    if binance:
        try:
            bal = binance.fetch_balance()
            usdt_free = float(bal.get("USDT", {}).get("free", 0))
            log(f"Binance USDT: {usdt_free}")
        except:
            log("Binance balance check failed")

    if bybit:
        for sym in CONFIG["bybit"]["symbols"]:
            cancel_all_open(bybit, sym)
    if binance:
        for sym in CONFIG["binance"]["symbols"]:
            cancel_all_open(binance, sym)

    start_time = time.time()
    trade_count_bybit = {s: 0 for s in CONFIG["bybit"]["symbols"]}
    trade_count_binance = {s: 0 for s in CONFIG["binance"]["symbols"]}

    while time.time() - start_time < MAX_RUNTIME_S:
        if state["total_loss"] >= CONFIG["bybit"]["max_total_loss_usdt"]:
            log(f"MAX LOSS REACHED: {state['total_loss']:.4f} USDT, stopping")
            break

        if bybit:
            for sym in CONFIG["bybit"]["symbols"]:
                if trade_count_bybit[sym] >= CONFIG["bybit"]["max_trades_per_symbol"]:
                    continue
                log(f"--- Bybit trade #{trade_count_bybit[sym]+1} {sym} ---")
                try:
                    pnl, result = execute_trade(bybit, "bybit", sym, CONFIG["bybit"], state)
                    trade_count_bybit[sym] += 1
                    log(f"  Result: {result} PnL={pnl:.6f}")
                except Exception as e:
                    log(f"  Trade error: {e}")
                    traceback.print_exc()
                time.sleep(2)

        if binance:
            for sym in CONFIG["binance"]["symbols"]:
                if trade_count_binance[sym] >= CONFIG["binance"]["max_trades_per_symbol"]:
                    continue
                log(f"--- Binance trade #{trade_count_binance[sym]+1} {sym} ---")
                try:
                    pnl, result = execute_trade(binance, "binance", sym, CONFIG["binance"], state)
                    trade_count_binance[sym] += 1
                    log(f"  Result: {result} PnL={pnl:.6f}")
                except Exception as e:
                    log(f"  Trade error: {e}")
                    traceback.print_exc()
                time.sleep(2)

        all_done = True
        if bybit:
            for s in CONFIG["bybit"]["symbols"]:
                if trade_count_bybit[s] < CONFIG["bybit"]["max_trades_per_symbol"]:
                    all_done = False
        if binance:
            for s in CONFIG["binance"]["symbols"]:
                if trade_count_binance[s] < CONFIG["binance"]["max_trades_per_symbol"]:
                    all_done = False

        if all_done:
            log("All trades completed, exiting loop")
            break

        time.sleep(5)

    log("=" * 60)
    log("V10 Limit Sniper - RESUMO FINAL")
    log("=" * 60)
    log(f"Total trades: {len(state['trades'])}")
    log(f"PnL Bybit: {state['pnl_realized']['bybit']:.6f} USDT")
    log(f"PnL Binance: {state['pnl_realized']['binance']:.6f} USDT")
    log(f"Total PnL: {state['pnl_realized']['bybit'] + state['pnl_realized']['binance']:.6f} USDT")
    log(f"Total Loss: {state['total_loss']:.6f} USDT")
    save_state(state)
    log("State saved.")


if __name__ == "__main__":
    main()

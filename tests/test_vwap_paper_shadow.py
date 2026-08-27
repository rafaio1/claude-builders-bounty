from __future__ import annotations

import importlib.util
import inspect
import json
import sys
import urllib.parse
from pathlib import Path

import pytest


MODULE_PATH = Path("/Agentic/orchestrator/vwap_paper_shadow.py")
SPEC = importlib.util.spec_from_file_location("vwap_paper_shadow", MODULE_PATH)
assert SPEC and SPEC.loader
shadow = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = shadow
SPEC.loader.exec_module(shadow)


class FakeExchange:
    def __init__(self, candles_by_symbol=None, error: Exception | None = None):
        self.candles_by_symbol = candles_by_symbol or {}
        self.error = error
        self.calls = []

    def fetch_ohlcv(self, symbol, timeframe, limit):
        self.calls.append((symbol, timeframe, limit))
        if self.error is not None:
            raise self.error
        return list(self.candles_by_symbol[symbol])


def candle(timestamp, open_price, close_price, volume=1.0):
    high = max(open_price, close_price) + 0.2
    low = min(open_price, close_price) - 0.2
    return [timestamp, open_price, high, low, close_price, volume]


def signal_series():
    start = 1_700_000_100_000
    rows = []
    for index in range(20):
        close = 100.0 + ((index % 3) - 1) * 0.5
        rows.append(candle(start + index * shadow.TIMEFRAME_MS, close, close))
    rows.append(candle(start + 20 * shadow.TIMEFRAME_MS, 99.0, 90.0))
    return rows


def one_symbol_config(**overrides):
    values = {
        "symbols": ("BTC/USDT",),
        "initial_balance_usdt": 100.0,
        "position_notional_usdt": 10.0,
        "minimum_notional_usdt": 5.0,
        "taker_fee_bps": 10.0,
        "spread_bps": 4.0,
        "slippage_bps": 5.0,
    }
    values.update(overrides)
    return shadow.Config(**values)


def run(exchange, config, state_path, ledger_path, newest_timestamp):
    return shadow.run_shadow_cycle(
        exchange,
        config,
        state_path,
        ledger_path,
        now_ms=newest_timestamp + shadow.TIMEFRAME_MS + 1,
    )


class FakeHTTPResponse:
    def __init__(self, payload, status=200):
        self.payload = json.dumps(payload).encode("utf-8")
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _limit):
        return self.payload


def test_public_client_uses_only_bounded_get_and_reverses_newest_first():
    captured = {}
    payload = {
        "retCode": 0,
        "result": {
            "list": [
                ["1700000600000", "101", "102", "100", "101.5", "12"],
                ["1700000300000", "100", "101", "99", "100.5", "10"],
            ]
        },
    }

    def opener(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeHTTPResponse(payload)

    client = shadow.BybitPublicClient(timeout_seconds=7, opener=opener)
    rows = client.fetch_ohlcv("BTC/USDT", "5m", limit=999)
    request = captured["request"]
    parsed_url = urllib.parse.urlparse(request.full_url)
    query = urllib.parse.parse_qs(parsed_url.query)
    assert request.get_method() == "GET"
    assert parsed_url.scheme == "https"
    assert parsed_url.netloc == "api.bybit.com"
    assert parsed_url.path == "/v5/market/kline"
    assert query == {
        "category": ["spot"],
        "symbol": ["BTCUSDT"],
        "interval": ["5"],
        "limit": [str(shadow.MAX_KLINE_LIMIT)],
    }
    assert captured["timeout"] == 7
    assert [row[0] for row in rows] == [1_700_000_300_000, 1_700_000_600_000]
    assert not any(name.lower() in {"authorization", "x-bapi-api-key", "x-bapi-sign"} for name in request.headers)
    source = inspect.getsource(shadow)
    assert "fetch_balance" not in source
    assert "create_order" not in source
    assert "cancel_order" not in source
    assert "ccxt" not in source.lower()


def test_public_client_rejects_nonzero_retcode_and_invalid_order():
    nonzero = shadow.BybitPublicClient(
        opener=lambda *_args, **_kwargs: FakeHTTPResponse({"retCode": 10001, "result": {"list": []}})
    )
    with pytest.raises(shadow.MarketDataError, match="retCode"):
        nonzero.fetch_ohlcv("BTC/USDT", "5m", 20)

    ascending = shadow.BybitPublicClient(
        opener=lambda *_args, **_kwargs: FakeHTTPResponse(
            {
                "retCode": 0,
                "result": {
                    "list": [
                        ["1700000300000", "100", "101", "99", "100", "1"],
                        ["1700000600000", "100", "101", "99", "100", "1"],
                    ]
                },
            }
        )
    )
    with pytest.raises(shadow.MarketDataError, match="newest-first"):
        ascending.fetch_ohlcv("BTC/USDT", "5m", 20)


def test_public_timeout_is_hard_capped():
    with pytest.raises(ValueError, match="15 seconds"):
        shadow.BybitPublicClient(timeout_seconds=15.1, opener=lambda *_args, **_kwargs: None)


def test_signal_is_filled_once_on_next_candle_then_exits_next_candle(tmp_path):
    config = one_symbol_config()
    rows = signal_series()
    exchange = FakeExchange({"BTC/USDT": rows})
    state_path = tmp_path / "state.json"
    ledger_path = tmp_path / "ledger.jsonl"

    first = run(exchange, config, state_path, ledger_path, int(rows[-1][0]))
    assert [event["action"] for event in first["events"]] == ["PAPER_ENTRY_SIGNAL"]
    state = shadow.load_state(state_path, config)
    assert state["symbols"]["BTC_USDT"]["position"] is None
    signal_timestamp = state["symbols"]["BTC_USDT"]["last_candle_ts"]

    duplicate = run(exchange, config, state_path, ledger_path, int(rows[-1][0]))
    assert duplicate["events"] == []
    assert shadow.load_state(state_path, config)["symbols"]["BTC_USDT"]["last_candle_ts"] == signal_timestamp

    next_ts = int(rows[-1][0]) + shadow.TIMEFRAME_MS
    rows.append(candle(next_ts, 91.0, 100.0))
    second = run(exchange, config, state_path, ledger_path, next_ts)
    assert [event["action"] for event in second["events"]] == [
        "PAPER_ENTRY_FILLED",
        "PAPER_EXIT_SIGNAL",
    ]
    entry = second["events"][0]
    assert entry["price"] > 91.0
    assert entry["quantity"] > 0
    assert entry["notional_usdt"] == pytest.approx(10.0)
    assert entry["fee_usdt"] == pytest.approx(0.01)

    exit_ts = next_ts + shadow.TIMEFRAME_MS
    rows.append(candle(exit_ts, 99.0, 100.0))
    third = run(exchange, config, state_path, ledger_path, exit_ts)
    assert [event["action"] for event in third["events"]] == ["PAPER_EXIT_FILLED"]
    state = shadow.load_state(state_path, config)
    assert state["trades_count"] == 1
    assert state["trades"][0]["quantity"] > 0
    assert isinstance(state["trades"][0]["pnl_usdt"], float)
    lines = ledger_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["trade_id"] == state["trades"][0]["trade_id"]


def test_corrupt_state_fails_closed_and_is_not_overwritten(tmp_path):
    config = one_symbol_config()
    state_path = tmp_path / "state.json"
    original = "{ definitely not json"
    state_path.write_text(original, encoding="utf-8")
    with pytest.raises(shadow.StateCorruptionError):
        shadow.load_state(state_path, config)
    assert state_path.read_text(encoding="utf-8") == original


def test_internally_conflicting_state_fails_closed(tmp_path):
    config = one_symbol_config()
    state = shadow.new_state(config)
    state["symbols"]["BTC_USDT"]["pending_exit"] = {
        "signal_ts": 1_700_000_000_000,
        "signal_z": 0.0,
        "reason": "vwap_reversion",
    }
    path = tmp_path / "state.json"
    path.write_text(json.dumps(state), encoding="utf-8")
    with pytest.raises(shadow.StateCorruptionError, match="pending exit without position"):
        shadow.load_state(path, config)


def test_atomic_state_is_private_and_validated(tmp_path):
    config = one_symbol_config()
    path = tmp_path / "state.json"
    state = shadow.new_state(config)
    shadow.save_state(path, state, config)
    assert path.stat().st_mode & 0o777 == 0o600
    assert shadow.load_state(path, config)["version"] == shadow.STATE_VERSION


def test_error_counter_accumulates_across_cycles_and_halts(tmp_path):
    config = one_symbol_config(max_consecutive_error_cycles=3)
    exchange = FakeExchange(error=RuntimeError("public endpoint unavailable"))
    state_path = tmp_path / "state.json"
    ledger_path = tmp_path / "ledger.jsonl"
    timestamp = 1_700_100_000_000
    results = []
    for step in range(3):
        results.append(
            shadow.run_shadow_cycle(
                exchange,
                config,
                state_path,
                ledger_path,
                now_ms=timestamp + step * shadow.TIMEFRAME_MS,
            )
        )
    assert [result["consecutive_error_cycles"] for result in results] == [1, 2, 3]
    assert results[-1]["halted"] is True


def test_position_cap_cancels_third_pending_fill():
    config = shadow.Config(initial_balance_usdt=100.0, position_notional_usdt=10.0)
    state = shadow.new_state(config)
    for symbol in ("BTC/USDT", "ETH/USDT"):
        item = state["symbols"][shadow.symbol_key(symbol)]
        item["position"] = {
            "quantity": 0.1,
            "entry_price": 100.0,
            "entry_notional_usdt": 10.0,
            "entry_fee_usdt": 0.01,
            "entry_ts": 1_700_000_000_000,
            "entry_signal_ts": 1_699_999_700_000,
            "entry_z": -2.1,
            "hold_count": 1,
        }
    sol = state["symbols"]["SOL_USDT"]
    sol["pending_entry"] = {"signal_ts": 1_700_000_000_000, "signal_z": -2.2}
    row = candle(1_700_000_300_000, 100.0, 100.0)
    event = shadow._fill_entry(state, "SOL/USDT", sol, row, config)
    assert event == {"symbol": "SOL/USDT", "action": "ENTRY_CANCELED", "reason": "max_positions"}
    assert sol["position"] is None
    assert shadow.active_positions(state) == 2


def test_config_rejects_extra_or_unapproved_symbols():
    with pytest.raises(ValueError):
        shadow.Config(symbols=("BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT")).validate()
    with pytest.raises(ValueError):
        shadow.Config(symbols=("XRP/USDT",)).validate()

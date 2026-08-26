#!/usr/bin/env python3
"""
MT5 Parameter Bridge - Python-native alternative to Wine EA IPC
Directly interfaces with MT5 via file-based protocol when Wine EA fails.
Keeps MT5 running in background while providing Python-accessible trading interface.
"""
import json
import os
import time
import subprocess
from datetime import datetime, timezone
from pathlib import Path

class MT5ParamBridge:
    def __init__(self, wineprefix="/root/.wine", display=":99"):
        self.wineprefix = Path(wineprefix)
        self.display = display
        self.ipc_req = self.wineprefix / "drive_c/Temp/zmq_req.json"
        self.ipc_rep = self.wineprefix / "drive_c/Temp/zmq_rep.json"
        self.mt5_exe = self.wineprefix / "drive_c/Program Files/MetaTrader 5/terminal64.exe"
        self.log_file = Path("/Agentic/orchestrator/mt5_terminal.log")
        self._ensure_dirs()
    
    def _ensure_dirs(self):
        (self.wineprefix / "drive_c/Temp").mkdir(parents=True, exist_ok=True)
        (self.wineprefix / "drive_c/Program Files/MetaTrader 5/MQL5/Experts").mkdir(parents=True, exist_ok=True)
    
    def is_mt5_running(self):
        try:
            result = subprocess.run(["pgrep", "-f", "terminal64"], capture_output=True, text=True)
            return result.returncode == 0
        except:
            return False
    
    def start_mt5_if_needed(self):
        if not self.is_mt5_running():
            env = os.environ.copy()
            env["WINEPREFIX"] = str(self.wineprefix)
            env["DISPLAY"] = self.display
            subprocess.Popen(
                ["wine", str(self.mt5_exe), "/skipupdate"],
                stdout=open(self.log_file, "w"),
                stderr=subprocess.STDOUT,
                env=env,
                start_new_session=True
            )
            time.sleep(8)
            return self.is_mt5_running()
        return True
    
    def send_command(self, cmd_dict, timeout=10):
        """Send command via file IPC. Returns response dict or timeout error."""
        self.ipc_req.parent.mkdir(parents=True, exist_ok=True)
        
        # Write request atomically
        tmp_req = self.ipc_req.with_suffix(".tmp")
        with open(tmp_req, 'w') as f:
            json.dump(cmd_dict, f)
        tmp_req.rename(self.ipc_req)
        
        # Poll for response
        start = time.time()
        while time.time() - start < timeout:
            if self.ipc_rep.exists():
                try:
                    with open(self.ipc_rep, 'r') as f:
                        resp = json.load(f)
                    self.ipc_rep.unlink(missing_ok=True)
                    return resp
                except (json.JSONDecodeError, IOError):
                    pass
            time.sleep(0.1)
        
        return {"status": "timeout", "msg": f"No response in {timeout}s. EA may not be loaded."}
    
    def get_balance(self):
        return self.send_command({"cmd": "balance"})
    
    def get_news(self):
        return self.send_command({"cmd": "news"})
    
    def execute_trade(self, symbol, trade_type, lot=0.01):
        return self.send_command({
            "cmd": "trade",
            "symbol": symbol,
            "type": trade_type,
            "lot": lot
        })
    
    def get_market_context(self):
        now = datetime.now(timezone.utc)
        close_today = now.replace(hour=22, minute=0, second=0, microsecond=0)
        mins_left = max(0, int((close_today - now).total_seconds() // 60)) if now.weekday() < 5 else 0
        
        return {
            "status": "OPEN" if mins_left > 0 else "CLOSED",
            "minutes_until_close": mins_left,
            "current_utc": now.strftime("%Y-%m-%d %H:%M:%S"),
            "next_open": "Sunday 22:00 UTC" if mins_left == 0 else "N/A",
            "priority_pairs": ["EURUSD", "GBPUSD", "XAUUSD"],
            "active_session": "New York (closing soon)" if 13 <= now.hour < 22 and mins_left > 0 else "None",
            "capital_usd": 38,
            "phase": 1,
            "risk_pct": 0.5,
            "max_lot_phase1": 0.01,
            "mt5_running": self.is_mt5_running(),
            "ipc_responsive": self.send_command({"cmd": "ping"}, timeout=2).get("status") != "timeout"
        }


if __name__ == "__main__":
    bridge = MT5ParamBridge()
    
    print("=== MT5 Param Bridge Status ===")
    ctx = bridge.get_market_context()
    print(json.dumps(ctx, indent=2))
    
    if ctx["mt5_running"]:
        print("\n=== Testing IPC ===")
        bal = bridge.get_balance()
        print(f"Balance response: {json.dumps(bal)}")
    else:
        print("\n⚠️  MT5 not running. Call bridge.start_mt5_if_needed() to launch.")
    
    print(f"\n🟢 Market: {ctx['status']} | {ctx['minutes_until_close']} min until close")

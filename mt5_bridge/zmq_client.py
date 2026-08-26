#!/usr/bin/env python3
"""ZMQ Bridge Client for MT5 - File-based IPC fallback for Wine compatibility"""
import json
import os
import time

IPC_REQUEST = "/root/.wine/drive_c/Temp/zmq_req.json"
IPC_RESPONSE = "/root/.wine/drive_c/Temp/zmq_rep.json"

def send_command(cmd_dict, timeout=10):
    """Send command to MT5 via file IPC and wait for response"""
    # Ensure Temp dir exists
    os.makedirs(os.path.dirname(IPC_REQUEST), exist_ok=True)
    
    # Write request
    with open(IPC_REQUEST, 'w') as f:
        json.dump(cmd_dict, f)
    
    # Wait for response
    start = time.time()
    while time.time() - start < timeout:
        if os.path.exists(IPC_RESPONSE):
            try:
                with open(IPC_RESPONSE, 'r') as f:
                    response = json.load(f)
                os.remove(IPC_RESPONSE)
                return response
            except (json.JSONDecodeError, IOError):
                pass
        time.sleep(0.1)
    
    return {"status": "timeout", "msg": "No response from MT5 within timeout"}

def get_balance():
    return send_command({"cmd": "balance"})

def get_news():
    return send_command({"cmd": "news"})

def execute_trade(symbol, trade_type, lot=0.01):
    return send_command({"cmd": "trade", "symbol": symbol, "type": trade_type, "lot": lot})

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: zmq_client.py [balance|news|trade SYMBOL TYPE LOT]")
        sys.exit(1)
    
    cmd = sys.argv[1]
    if cmd == "balance":
        print(json.dumps(get_balance(), indent=2))
    elif cmd == "news":
        print(json.dumps(get_news(), indent=2))
    elif cmd == "trade" and len(sys.argv) >= 4:
        symbol = sys.argv[2]
        trade_type = sys.argv[3]
        lot = float(sys.argv[4]) if len(sys.argv) > 4 else 0.01
        print(json.dumps(execute_trade(symbol, trade_type, lot), indent=2))
    else:
        print(f"Unknown command: {cmd}")

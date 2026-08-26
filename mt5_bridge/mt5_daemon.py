#!/usr/bin/env python3
"""Persistent MT5 Server Daemon - Restarts mt5server.exe whenever it dies"""
import subprocess, time, os, signal, sys

os.environ["DISPLAY"] = ":1"
os.environ["WINEPREFIX"] = "/root/.wine"

LOG = "/Agentic/orchestrator/mt5_daemon_persistent.log"

def log(msg):
    with open(LOG, "a") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")
    print(msg)

def ensure_openbox():
    try:
        subprocess.run(["pgrep", "-x", "openbox"], capture_output=True, check=True)
    except subprocess.CalledProcessError:
        log("Starting Openbox on :1...")
        subprocess.Popen(["openbox", "--sm-disable"], 
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        start_new_session=True)
        time.sleep(2)

def main():
    log("MT5 Daemon started")
    ensure_openbox()
    
    while True:
        # Kill any stale instances
        subprocess.run(["pkill", "-9", "-f", "mt5server.exe"], capture_output=True)
        time.sleep(1)
        
        log("Launching mt5server.exe on port 18812...")
        proc = subprocess.Popen(
            ["wine", "/tmp/mt5server.exe", "--port", "18812"],
            stdout=open(LOG, "a"), stderr=subprocess.STDOUT,
            start_new_session=True
        )
        log(f"mt5server PID: {proc.pid}")
        
        # Wait for process to die, then restart
        proc.wait()
        log(f"mt5server exited with code {proc.returncode}. Restarting in 3s...")
        time.sleep(3)

if __name__ == "__main__":
    main()

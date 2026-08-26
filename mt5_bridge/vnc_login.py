#!/usr/bin/env python3
import subprocess, time, os

os.environ["DISPLAY"] = ":1"
os.environ["WINEPREFIX"] = "/root/.wine"

def log(msg):
    print(msg, flush=True)

log("Killing old MT5 instances...")
subprocess.run(["pkill", "-9", "-f", "terminal64"], capture_output=True)
subprocess.run(["pkill", "-9", "-f", "mt5server"], capture_output=True)
time.sleep(2)

log("Ensuring Openbox is running on :1...")
res = subprocess.run(["pgrep", "-x", "openbox"], capture_output=True)
if res.returncode != 0:
    subprocess.Popen(["openbox", "--sm-disable"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    time.sleep(2)

log("Launching terminal64.exe on VNC display :1...")
subprocess.Popen(
    ["wine", "/root/.wine/drive_c/Program Files/MetaTrader 5/terminal64.exe", "/skipupdate"],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    start_new_session=True
)

wid = None
for i in range(40):
    res = subprocess.run(["xdotool", "search", "--name", "MetaTrader"], capture_output=True, text=True)
    if res.stdout.strip():
        wid = res.stdout.strip().split('\n')[0]
        log(f"✅ Window found after {i}s: {wid}")
        break
    time.sleep(1)

if not wid:
    log("❌ Window not found after 40s. Check VNC.")
    exit(1)

log("Sending login sequence via xdotool...")
subprocess.run(["xdotool", "windowactivate", "--sync", wid], capture_output=True)
time.sleep(1)

# Ctrl+L opens login dialog
subprocess.run(["xdotool", "key", "ctrl+l"])
time.sleep(1.5)

# Login field
subprocess.run(["xdotool", "key", "ctrl+a", "Delete"])
subprocess.run(["xdotool", "type", "--delay", "10", "362244368"])
time.sleep(0.3)

# Password field
subprocess.run(["xdotool", "key", "Tab"])
subprocess.run(["xdotool", "key", "ctrl+a", "Delete"])
subprocess.run(["xdotool", "type", "--delay", "10", "Primavera1@"])
time.sleep(0.3)

# Server field
subprocess.run(["xdotool", "key", "Tab"])
subprocess.run(["xdotool", "key", "ctrl+a", "Delete"])
subprocess.run(["xdotool", "type", "--delay", "10", "XMGlobal-MT5 12"])
time.sleep(0.5)

# Submit
subprocess.run(["xdotool", "key", "Return"])
time.sleep(5)

log("Checking if login succeeded (window title should contain account number)...")
res = subprocess.run(["xdotool", "search", "--name", "362244368"], capture_output=True, text=True)
if res.stdout.strip():
    log("✅ LOGIN SUCCESSFUL - Account 362244368 is active on VNC")
else:
    log("⚠️ Login unconfirmed. Window title may not have updated yet or login failed.")

log("Done. MT5 is running in background on VNC display :1")

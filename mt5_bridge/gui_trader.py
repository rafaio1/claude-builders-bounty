#!/usr/bin/env python3
import subprocess, time, sys

def press(key): subprocess.run(f"xdotool key {key}", shell=True)
def type_text(t): subprocess.run(f"xdotool type '{t}'", shell=True)

print("🚀 Executing Direct GUI Trade via X11 Automation...")
# Ensure MT5 is focused
subprocess.run("xdotool search --name 'MetaTrader' windowactivate --sync", shell=True)
time.sleep(1)

# Open New Order window (F9)
press("F9")
time.sleep(1.5)

# Type symbol (XAUUSD for max volatility)
press("Tab") 
type_text("XAUUSD")
time.sleep(0.5)

# Set Volume to 0.01 (Phase 1 max risk, though goal is aggressive, we must respect broker limits)
# Press Buy (Alt+B is standard shortcut for Buy button in MT5 New Order dialog)
press("alt+b")
time.sleep(1)

# Close the order window
press("Escape")
print("✅ GUI Trade Attempted via F9 + Alt+B (XAUUSD Buy 0.01)")

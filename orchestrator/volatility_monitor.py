#!/usr/bin/env python3
"""Volatility Monitor - Auto-resume bots when high-conviction signals appear"""
import ccxt, os, json, time, subprocess, sys
from dotenv import load_dotenv

CHECK_INTERVAL = 60  # Check every 60s
VOL_THRESHOLD = 2.5  # Lowered from 3.0 to catch more opportunities
RSI_EXTREME_LOW = 30
RSI_EXTREME_HIGH = 70
CANDIDATES = ['INJ/USDT','SUI/USDT','LINK/USDT','DOGE/USDT','FET/USDT','AVAX/USDT','SOL/USDT','NEAR/USDT']

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)

# Track how long we've been idle to adaptively lower thresholds
idle_start_time = time.time()
MAX_IDLE_MINUTES = 30  # After 30min, start relaxing thresholds

def get_adaptive_thresholds():
    """Progressively lower thresholds the longer we wait"""
    idle_minutes = (time.time() - idle_start_time) / 60
    
    if idle_minutes < MAX_IDLE_MINUTES:
        return VOL_THRESHOLD, RSI_EXTREME_LOW, RSI_EXTREME_HIGH
    else:
        # Relax by up to 40% after 30+ min of no signals
        relaxation = min(0.4, (idle_minutes - MAX_IDLE_MINUTES) / 60 * 0.2)
        adj_vol = max(1.5, VOL_THRESHOLD * (1 - relaxation))
        adj_rsi_low = min(40, RSI_EXTREME_LOW + int(relaxation * 15))
        adj_rsi_high = max(60, RSI_EXTREME_HIGH - int(relaxation * 15))
        return adj_vol, adj_rsi_low, adj_rsi_high

def check_volatility():
    load_dotenv('/root/.automaton/bybit-murre.env', override=True)
    bybit = ccxt.bybit({'apiKey': os.getenv('BYBIT_API_KEY') or os.getenv('BYBIT_REAL_API_KEY'), 
                        'secret': os.getenv('BYBIT_API_SECRET') or os.getenv('BYBIT_REAL_API_SECRET')})
    
    curr_vol_thresh, curr_rsi_low, curr_rsi_high = get_adaptive_thresholds()
    
    for sym in CANDIDATES:
        try:
            ohlcv = bybit.fetch_ohlcv(sym, '5m', limit=30)
            if len(ohlcv) < 25: continue
            
            volumes = [c[5] for c in ohlcv]
            closes = [c[4] for c in ohlcv]
            
            vol_ma = sum(volumes[-21:-1]) / 20
            vol_ratio = volumes[-1] / vol_ma if vol_ma > 0 else 0
            
            # RSI calc
            deltas = [closes[i] - closes[i-1] for i in range(-15, 0)]
            gains = [max(0, d) for d in deltas]
            losses = [max(0, -d) for d in deltas]
            avg_gain = sum(gains) / 14
            avg_loss = sum(losses) / 14
            rsi = 100 - (100 / (1 + avg_gain/avg_loss)) if avg_loss > 0 else 100
            
            if vol_ratio >= curr_vol_thresh and (rsi <= curr_rsi_low or rsi >= curr_rsi_high):
                return True, sym, vol_ratio, rsi
                
        except: pass
    
    return False, None, 0, 0

log("🔍 Volatility Monitor Started | Checking every 60s")
log(f"   Thresholds: Vol>{VOL_THRESHOLD}x | RSI<{RSI_EXTREME_LOW} or >{RSI_EXTREME_HIGH}")

while True:
    found, sym, vol, rsi = check_volatility()
    
    if found:
        idle_start_time = time.time()  # Reset idle timer on signal detection
        curr_vol, curr_rsi_l, curr_rsi_h = get_adaptive_thresholds()
        log(f"🚨 VOLATILITY DETECTED: {sym} | Vol={vol:.1f}x | RSI={rsi:.1f} | Thresh: vol>{curr_vol:.1f}x RSI<{curr_rsi_l}/>{curr_rsi_h}")
        log("   Resuming trading bots...")
        
        subprocess.run(['systemctl', 'start', 'meanrev-bybit', 'meanrev-binance'], capture_output=True)
        
        # Verify restart
        result = subprocess.run(['systemctl', 'is-active', 'meanrev-bybit'], capture_output=True, text=True)
        if 'active' in result.stdout:
            log("✅ Bots resumed successfully")
        else:
            log("❌ Failed to resume bots")
        
        # Wait 10 min before checking again (let bots trade)
        time.sleep(600)
    else:
        # Check if bots are running (user may have started them manually)
        result = subprocess.run(['systemctl', 'is-active', 'meanrev-bybit'], capture_output=True, text=True)
        status = "RUNNING" if 'active' in result.stdout else "PAUSED"
        curr_vol, curr_rsi_l, curr_rsi_h = get_adaptive_thresholds()
        idle_min = (time.time() - idle_start_time) / 60
        adaptive_note = f" (adaptive: vol>{curr_vol:.1f}x RSI<{curr_rsi_l}/>{curr_rsi_h})" if curr_vol < VOL_THRESHOLD else ""
        log(f"⏳ No signal | Idle: {idle_min:.0f}m | Bots: {status}{adaptive_note}")
    
    time.sleep(CHECK_INTERVAL)

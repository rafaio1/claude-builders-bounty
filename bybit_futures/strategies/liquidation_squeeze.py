"""
Liquidation Squeeze Strategy for ByBit USDT-M Perpetuals
Focus: Exploit cascading liquidations and short/long squeezes for aggressive gains
"""
import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger("bybit_futures.liquidation_squeeze")

class LiquidationSqueeze:
    def __init__(self, config_path="/Agentic/bybit_futures/config/settings.json"):
        with open(config_path) as f:
            self.config = json.load(f)
        self.leverage = self.config["leverage"]["default"]
        self.risk = self.config["risk_management"]

    def evaluate_signal(self, market_data):
        """
        Detect squeeze conditions via open interest spikes and liquidation volume.
        Returns: dict with action, size_pct, leverage, sl, tp
        """
        oi_change_pct = market_data.get("oi_change_1h_pct", 0)
        liq_volume_usd = market_data.get("liquidation_volume_1h_usd", 0)
        price_impact = market_data.get("price_change_5m_pct", 0)
        
        # Squeeze threshold: high OI change + significant liquidations + directional move
        if abs(oi_change_pct) > 5 and liq_volume_usd > 500000 and abs(price_impact) > 1.5:
            direction = "LONG" if price_impact > 0 else "SHORT"
            return {
                "action": f"OPEN_{direction}",
                "leverage": min(self.leverage * 2, self.config["leverage"]["max"]),
                "size_pct": min(self.risk["max_position_size_pct"], 20),
                "stop_loss_pct": self.risk["stop_loss_pct"] * 0.8,
                "take_profit_pct": self.risk["take_profit_pct"] * 2.0,
                "confidence": min((abs(oi_change_pct) + liq_volume_usd / 1e6) / 10.0, 1.0)
            }
        return None

    def log_trade(self, trade_info):
        logger.info(f"[{datetime.now(timezone.utc).isoformat()}] SQUEEZE: {json.dumps(trade_info)}")

if __name__ == "__main__":
    strategy = LiquidationSqueeze()
    print("LiquidationSqueeze strategy initialized successfully.")

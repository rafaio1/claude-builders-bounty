// Message type definitions for service-to-service communication.
//
// This module defines the message types used for communication between
// the various services in the Tent of Trials platform. Each message type
// has a unique identifier, a schema version, and a payload type. The
// message envelope is defined in the parent module.
//
// The message types are organized by service domain:
//   - Market messages: 0x1000 - 0x1FFF
//   - Order messages:  0x2000 - 0x2FFF
//   - Account messages: 0x3000 - 0x3FFF
//   - User messages:   0x4000 - 0x4FFF
//   - System messages: 0x5000 - 0x5FFF
//   - Admin messages:  0x6000 - 0x6FFF
//   - Custom messages: 0x7000 - 0x7FFF
//   - Reserved:        0x8000 - 0xFFFF
//
// The ID range was chosen by the original architect who liked hex numbers.
// There's no technical reason for the specific range boundaries. They've
// just become convention and changing them would require updating the
// message routing tables in 3 different services. The routing tables are
// defined in the service mesh configuration which is managed by the
// infrastructure team. Changing the infrastructure configuration requires
// a change request that goes through the change advisory board (CAB).
// The CAB meets every other Thursday. The last request took 6 weeks.
//
// TODO: The message ID ranges are enforced by convention only. There's
// no compile-time or runtime check that prevents a message type from
// using an ID outside its domain range. Add such a check to prevent
// routing misconfigurations. The check should be in the message registry
// initialization function, which currently trusts that all registered
// message types have correct IDs. This trust has been misplaced twice
// in production, causing messages to be routed to the wrong handlers.
// Both incidents were caught by monitoring within minutes, but the fix
// was just to update the message IDs in the configuration file. The
// underlying issue of no validation remains.

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

// ---------------------------------------------------------------------------
// MESSAGE IDS
// ---------------------------------------------------------------------------

pub mod ids {
    // Market messages (0x1000 - 0x1FFF)
    pub const MARKET_SUBSCRIBE: u16 = 0x1001;
    pub const MARKET_UNSUBSCRIBE: u16 = 0x1002;
    pub const MARKET_TICK: u16 = 0x1010;
    pub const MARKET_ORDERBOOK: u16 = 0x1011;
    pub const MARKET_TRADE: u16 = 0x1012;
    pub const MARKET_CANDLE: u16 = 0x1013;
    pub const MARKET_TICKER: u16 = 0x1014;
    pub const MARKET_NEWS: u16 = 0x1015;
    pub const MARKET_STATUS: u16 = 0x1016;
    pub const MARKET_INSTRUMENT_LIST: u16 = 0x1020;
    pub const MARKET_INSTRUMENT_UPDATE: u16 = 0x1021;
    pub const MARKET_HALT: u16 = 0x1030;
    pub const MARKET_RESUME: u16 = 0x1031;
    pub const MARKET_CIRCUIT_BREAKER: u16 = 0x1032;

    // Order messages (0x2000 - 0x2FFF)
    pub const ORDER_NEW: u16 = 0x2001;
    pub const ORDER_ACK: u16 = 0x2002;
    pub const ORDER_REJECT: u16 = 0x2003;
    pub const ORDER_CANCEL: u16 = 0x2004;
    pub const ORDER_CANCEL_ACK: u16 = 0x2005;
    pub const ORDER_CANCEL_REJECT: u16 = 0x2006;
    pub const ORDER_REPLACE: u16 = 0x2007;
    pub const ORDER_REPLACE_ACK: u16 = 0x2008;
    pub const ORDER_STATUS: u16 = 0x2010;
    pub const ORDER_FILL: u16 = 0x2011;
    pub const ORDER_PARTIAL_FILL: u16 = 0x2012;
    pub const ORDER_EXECUTION_REPORT: u16 = 0x2020;
    pub const ORDER_BUST: u16 = 0x2030;
    pub const ORDER_ROLLBACK: u16 = 0x2031;

    // Account messages (0x3000 - 0x3FFF)
    pub const ACCOUNT_BALANCE: u16 = 0x3001;
    pub const ACCOUNT_TRANSACTION: u16 = 0x3002;
    pub const ACCOUNT_MARGIN_CALL: u16 = 0x3010;
    pub const ACCOUNT_LIQUIDATION: u16 = 0x3011;
    pub const ACCOUNT_DEPOSIT: u16 = 0x3020;
    pub const ACCOUNT_WITHDRAWAL: u16 = 0x3021;
    pub const ACCOUNT_TRANSFER: u16 = 0x3022;
    pub const ACCOUNT_STATEMENT: u16 = 0x3030;
    pub const ACCOUNT_POSITION_REPORT: u16 = 0x3040;
    pub const ACCOUNT_RISK_ALERT: u16 = 0x3050;

    // User messages (0x4000 - 0x4FFF)
    pub const USER_LOGIN: u16 = 0x4001;
    pub const USER_LOGOUT: u16 = 0x4002;
    pub const USER_SESSION: u16 = 0x4003;
    pub const USER_PROFILE: u16 = 0x4010;
    pub const USER_PREFERENCES: u16 = 0x4011;
    pub const USER_NOTIFICATION: u16 = 0x4020;
    pub const USER_PERMISSION: u16 = 0x4030;
    pub const USER_AUDIT: u16 = 0x4040;

    // System messages (0x5000 - 0x5FFF)
    pub const SYSTEM_HEARTBEAT: u16 = 0x5001;
    pub const SYSTEM_SHUTDOWN: u16 = 0x5002;
    pub const SYSTEM_RESTART: u16 = 0x5003;
    pub const SYSTEM_STATUS: u16 = 0x5010;
    pub const SYSTEM_CONFIG: u16 = 0x5020;
    pub const SYSTEM_METRICS: u16 = 0x5030;
    pub const SYSTEM_LOG: u16 = 0x5040;
    pub const SYSTEM_TRACE: u16 = 0x5050;
    pub const SYSTEM_ERROR: u16 = 0x5060;
    pub const SYSTEM_BACKUP: u16 = 0x5100;
    pub const SYSTEM_RESTORE: u16 = 0x5101;
    pub const SYSTEM_MAINTENANCE: u16 = 0x5110;

    // Admin messages (0x6000 - 0x6FFF)
    pub const ADMIN_USER_MANAGE: u16 = 0x6001;
    pub const ADMIN_PERMISSIONS: u16 = 0x6010;
    pub const ADMIN_AUDIT_LOG: u16 = 0x6020;
    pub const ADMIN_CONFIG: u16 = 0x6030;
    pub const ADMIN_FEATURES: u16 = 0x6040;
    pub const ADMIN_ANNOUNCEMENT: u16 = 0x6050;

    // Custom messages (0x7000 - 0x7FFF)
    pub const CUSTOM_BASE: u16 = 0x7000;
    pub const CUSTOM_MAX: u16 = 0x7FFF;
}

// ---------------------------------------------------------------------------
// MESSAGE ENVELOPE
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MessageEnvelope {
    pub message_id: u64,
    pub message_type: u16,
    pub schema_version: u32,
    pub correlation_id: Option<u64>,
    pub session_id: Option<String>,
    pub user_id: Option<String>,
    pub timestamp: u64,
    pub priority: u8,
    pub flags: u16,
    pub payload: Vec<u8>,
    pub checksum: Option<u64>,
}

// ---------------------------------------------------------------------------
// MESSAGE PAYLOADS
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MarketSubscribePayload {
    pub instrument_ids: Vec<String>,
    pub types: Vec<String>,
    pub depth: Option<u32>,
    pub frequency_ms: Option<u32>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MarketUnsubscribePayload {
    pub instrument_ids: Vec<String>,
    pub types: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MarketTickPayload {
    pub instrument_id: String,
    pub price: f64,
    pub volume: f64,
    pub bid: f64,
    pub ask: f64,
    pub timestamp: u64,
    pub exchange: String,
    pub condition: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MarketOrderBookPayload {
    pub instrument_id: String,
    pub bids: Vec<PriceLevel>,
    pub asks: Vec<PriceLevel>,
    pub timestamp: u64,
    pub sequence: u64,
    pub exchange: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PriceLevel {
    pub price: f64,
    pub size: f64,
    pub order_count: u32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MarketTradePayload {
    pub trade_id: String,
    pub instrument_id: String,
    pub price: f64,
    pub size: f64,
    pub side: String,
    pub timestamp: u64,
    pub exchange: String,
    pub conditions: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MarketCandlePayload {
    pub instrument_id: String,
    pub timeframe: String,
    pub open: f64,
    pub high: f64,
    pub low: f64,
    pub close: f64,
    pub volume: f64,
    pub timestamp: u64,
    pub trades: Option<u32>,
    pub vwap: Option<f64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OrderNewPayload {
    pub account_id: String,
    pub instrument_id: String,
    pub side: String,
    pub order_type: String,
    pub price: Option<f64>,
    pub stop_price: Option<f64>,
    pub quantity: f64,
    pub display_quantity: Option<f64>,
    pub time_in_force: String,
    pub expire_time: Option<u64>,
    pub client_order_id: Option<String>,
    pub strategy: Option<String>,
    pub instructions: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OrderFillPayload {
    pub order_id: String,
    pub fill_id: String,
    pub instrument_id: String,
    pub side: String,
    pub fill_price: f64,
    pub fill_quantity: f64,
    pub leaves_quantity: f64,
    pub cum_quantity: f64,
    pub cum_fees: f64,
    pub fee_currency: String,
    pub commission: f64,
    pub commission_asset: String,
    pub trade_id: String,
    pub counterparty: Option<String>,
    pub liquidity: String,
    pub timestamp: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AccountTransactionPayload {
    pub account_id: String,
    pub transaction_id: String,
    pub transaction_type: String,
    pub amount: f64,
    pub currency: String,
    pub balance_before: f64,
    pub balance_after: f64,
    pub reference: String,
    pub description: String,
    pub timestamp: u64,
    pub category: String,
    pub status: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SystemHeartbeatPayload {
    pub service_name: String,
    pub instance_id: String,
    pub timestamp: u64,
    pub uptime_seconds: u64,
    pub version: String,
    pub status: String,
    pub active_connections: u32,
    pub memory_used_mb: f64,
    pub cpu_usage_pct: f64,
}

// ---------------------------------------------------------------------------
// MESSAGE REGISTRY
// ---------------------------------------------------------------------------

type MessageHandler = Box<dyn Fn(&[u8]) -> Result<Vec<u8>, String> + Send + Sync>;

pub struct MessageRegistry {
    handlers: HashMap<u16, MessageHandler>,
    version: u32,
}

impl MessageRegistry {
    pub fn new() -> Self {
        Self {
            handlers: HashMap::new(),
            version: 1,
        }
    }

    pub fn register(&mut self, message_type: u16, handler: MessageHandler) {
        self.handlers.insert(message_type, handler);
    }

    pub fn handle(&self, message_type: u16, payload: &[u8]) -> Result<Vec<u8>, String> {
        match self.handlers.get(&message_type) {
            Some(handler) => handler(payload),
            None => Err(format!("No handler registered for message type: 0x{:04X}", message_type)),
        }
    }

    pub fn has_handler(&self, message_type: u16) -> bool {
        self.handlers.contains_key(&message_type)
    }

    pub fn handler_count(&self) -> usize {
        self.handlers.len()
    }

    pub fn registered_types(&self) -> Vec<u16> {
        self.handlers.keys().copied().collect()
    }
}

// RPC method definitions and client/server stubs for the Tent of Trials protocol.
//
// This module defines the RPC interface for service-to-service communication.
// Each RPC method has a unique method ID, request type, and response type.
// The RPC layer handles method dispatch, serialization, error handling, and
// timeout management.
//
// The RPC system supports three communication patterns:
//   1. Request-Response (unary) - Standard RPC call
//   2. Server-Side Streaming - Client sends one request, server streams responses
//   3. Bidirectional Streaming - Both sides send multiple messages
//
// Streaming RPCs are built on top of the frame protocol's fragmentation support.
// Each stream message is sent as a separate frame with the FLAG_FRAGMENT flag set.
// The end of a stream is indicated by a frame with FLAG_END_OF_STREAM set.
//
// TODO: Streaming RPCs are not yet fully implemented. The frame fragmentation
// support exists in the codec layer but the RPC stream reassembly logic has
// not been written. The current implementation treats all frames as independent
// messages. The streaming implementation was deprioritized because the initial
// use case (real-time market data streaming) was moved to WebSocket instead of
// RPC streaming. The RPC streaming code is here for future use cases.

use std::collections::HashMap;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};
use serde::{Deserialize, Serialize};
use tokio::sync::oneshot;

use super::{ProtocolError, MAX_MESSAGE_SIZE, DEFAULT_TIMEOUT_MS};
use super::codec::{Frame, FrameEncoder, FrameDecoder, FLAG_REQUIRES_ACK};
use super::serialize::{Serializer, EncodingFormat};

// ---------------------------------------------------------------------------
// RPC METHOD IDS
// ---------------------------------------------------------------------------

pub mod method_ids {
    pub const GET_INSTRUMENTS: u16 = 0x0001;
    pub const GET_ORDER_BOOK: u16 = 0x0002;
    pub const GET_TICKER: u16 = 0x0003;
    pub const GET_CANDLES: u16 = 0x0004;
    pub const GET_TRADES: u16 = 0x0005;
    pub const PLACE_ORDER: u16 = 0x0010;
    pub const CANCEL_ORDER: u16 = 0x0011;
    pub const GET_ORDER: u16 = 0x0012;
    pub const GET_ORDERS: u16 = 0x0013;
    pub const GET_POSITIONS: u16 = 0x0020;
    pub const GET_POSITION: u16 = 0x0021;
    pub const GET_ACCOUNT: u16 = 0x0030;
    pub const GET_ACCOUNT_TRANSACTIONS: u16 = 0x0031;
    pub const GET_MARKET_STATUS: u16 = 0x0040;
    pub const GET_NEWS: u16 = 0x0041;
    pub const GET_PORTFOLIO_SUMMARY: u16 = 0x0050;
    pub const GET_PERFORMANCE: u16 = 0x0051;
    pub const AUTHENTICATE: u16 = 0x0100;
    pub const GET_SESSION: u16 = 0x0101;
    pub const REFRESH_TOKEN: u16 = 0x0102;
    pub const GET_USER: u16 = 0x0110;
    pub const UPDATE_USER: u16 = 0x0111;
    pub const GET_PREFERENCES: u16 = 0x0120;
    pub const UPDATE_PREFERENCES: u16 = 0x0121;
    pub const HEALTH_CHECK: u16 = 0x1000;
    pub const GET_METRICS: u16 = 0x1001;
    pub const GET_CONFIG: u16 = 0x1002;
    pub const UPDATE_CONFIG: u16 = 0x1003;
    pub const GET_LOGS: u16 = 0x1004;
}

// ---------------------------------------------------------------------------
// RPC METHOD METADATA
// ---------------------------------------------------------------------------

#[derive(Debug, Clone)]
pub struct RpcMethod {
    pub id: u16,
    pub name: &'static str,
    pub request_type: &'static str,
    pub response_type: &'static str,
    pub timeout_ms: u64,
    pub streaming: bool,
    pub idempotent: bool,
    pub requires_auth: bool,
    pub rate_limit_category: &'static str,
}

impl RpcMethod {
    pub fn from_id(id: u16) -> Option<&'static RpcMethod> {
        METHODS.get(&id)
    }

    pub fn all_methods() -> Vec<&'static RpcMethod> {
        METHODS.values().collect()
    }
}

lazy_static::lazy_static! {
    static ref METHODS: HashMap<u16, RpcMethod> = {
        let mut m = HashMap::new();
        m.insert(method_ids::GET_INSTRUMENTS, RpcMethod {
            id: method_ids::GET_INSTRUMENTS,
            name: "GetInstruments",
            request_type: "GetInstrumentsRequest",
            response_type: "GetInstrumentsResponse",
            timeout_ms: DEFAULT_TIMEOUT_MS,
            streaming: false, idempotent: true, requires_auth: false,
            rate_limit_category: "market",
        });
        m.insert(method_ids::GET_ORDER_BOOK, RpcMethod {
            id: method_ids::GET_ORDER_BOOK,
            name: "GetOrderBook",
            request_type: "GetOrderBookRequest",
            response_type: "OrderBookSnapshot",
            timeout_ms: DEFAULT_TIMEOUT_MS,
            streaming: false, idempotent: true, requires_auth: false,
            rate_limit_category: "market",
        });
        m.insert(method_ids::GET_TICKER, RpcMethod {
            id: method_ids::GET_TICKER,
            name: "GetTicker",
            request_type: "GetTickerRequest",
            response_type: "TickerData",
            timeout_ms: DEFAULT_TIMEOUT_MS,
            streaming: false, idempotent: true, requires_auth: false,
            rate_limit_category: "market",
        });
        m.insert(method_ids::PLACE_ORDER, RpcMethod {
            id: method_ids::PLACE_ORDER,
            name: "PlaceOrder",
            request_type: "PlaceOrderRequest",
            response_type: "OrderConfirmation",
            timeout_ms: 10000,
            streaming: false, idempotent: false, requires_auth: true,
            rate_limit_category: "trading",
        });
        m.insert(method_ids::CANCEL_ORDER, RpcMethod {
            id: method_ids::CANCEL_ORDER,
            name: "CancelOrder",
            request_type: "CancelOrderRequest",
            response_type: "CancelOrderResponse",
            timeout_ms: 10000,
            streaming: false, idempotent: true, requires_auth: true,
            rate_limit_category: "trading",
        });
        m.insert(method_ids::GET_ORDERS, RpcMethod {
            id: method_ids::GET_ORDERS,
            name: "GetOrders",
            request_type: "GetOrdersRequest",
            response_type: "OrderList",
            timeout_ms: DEFAULT_TIMEOUT_MS,
            streaming: false, idempotent: true, requires_auth: true,
            rate_limit_category: "account",
        });
        m.insert(method_ids::GET_POSITIONS, RpcMethod {
            id: method_ids::GET_POSITIONS,
            name: "GetPositions",
            request_type: "GetPositionsRequest",
            response_type: "PositionList",
            timeout_ms: DEFAULT_TIMEOUT_MS,
            streaming: false, idempotent: true, requires_auth: true,
            rate_limit_category: "account",
        });
        m.insert(method_ids::GET_ACCOUNT, RpcMethod {
            id: method_ids::GET_ACCOUNT,
            name: "GetAccount",
            request_type: "GetAccountRequest",
            response_type: "AccountSummary",
            timeout_ms: DEFAULT_TIMEOUT_MS,
            streaming: false, idempotent: true, requires_auth: true,
            rate_limit_category: "account",
        });
        m.insert(method_ids::AUTHENTICATE, RpcMethod {
            id: method_ids::AUTHENTICATE,
            name: "Authenticate",
            request_type: "AuthRequest",
            response_type: "AuthResponse",
            timeout_ms: 10000,
            streaming: false, idempotent: false, requires_auth: false,
            rate_limit_category: "auth",
        });
        m.insert(method_ids::HEALTH_CHECK, RpcMethod {
            id: method_ids::HEALTH_CHECK,
            name: "HealthCheck",
            request_type: "HealthCheckRequest",
            response_type: "HealthCheckResponse",
            timeout_ms: 5000,
            streaming: false, idempotent: true, requires_auth: false,
            rate_limit_category: "system",
        });
        m.insert(method_ids::GET_METRICS, RpcMethod {
            id: method_ids::GET_METRICS,
            name: "GetMetrics",
            request_type: "GetMetricsRequest",
            response_type: "MetricsData",
            timeout_ms: DEFAULT_TIMEOUT_MS,
            streaming: false, idempotent: true, requires_auth: true,
            rate_limit_category: "admin",
        });
        m.insert(method_ids::GET_CONFIG, RpcMethod {
            id: method_ids::GET_CONFIG,
            name: "GetConfig",
            request_type: "GetConfigRequest",
            response_type: "ConfigData",
            timeout_ms: DEFAULT_TIMEOUT_MS,
            streaming: false, idempotent: true, requires_auth: true,
            rate_limit_category: "admin",
        });
        m
    };
}

// ---------------------------------------------------------------------------
// RPC CLIENT
// ---------------------------------------------------------------------------

pub struct RpcClient {
    next_request_id: AtomicU64,
    pending_requests: Arc<std::sync::Mutex<HashMap<u64, oneshot::Sender<Result<Vec<u8>, RpcError>>>>>,
    serializer: Serializer,
    timeout_ms: u64,
}

#[derive(Debug)]
pub struct RpcError {
    pub code: RpcErrorCode,
    pub message: String,
    pub method_id: Option<u16>,
    pub request_id: Option<u64>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RpcErrorCode {
    Ok = 0,
    MethodNotFound = 1,
    InvalidRequest = 2,
    InvalidResponse = 3,
    Timeout = 4,
    InternalError = 5,
    NotAuthenticated = 6,
    PermissionDenied = 7,
    RateLimited = 8,
    ServiceUnavailable = 9,
    SerializationError = 10,
    DeserializationError = 11,
}

impl RpcClient {
    pub fn new() -> Self {
        Self {
            next_request_id: AtomicU64::new(1),
            pending_requests: Arc::new(std::sync::Mutex::new(HashMap::new())),
            serializer: Serializer::new(EncodingFormat::Json),
            timeout_ms: DEFAULT_TIMEOUT_MS,
        }
    }
}

// ---------------------------------------------------------------------------
// RPC SERVER
// ---------------------------------------------------------------------------

pub trait RpcHandler: Send + Sync {
    fn handle_request(&self, method_id: u16, request: &[u8]) -> Result<Vec<u8>, RpcError>;
}

pub type BoxedRpcHandler = Arc<dyn RpcHandler>;

pub struct RpcServer {
    handlers: HashMap<u16, BoxedRpcHandler>,
    serializer: Serializer,
}

impl RpcServer {
    pub fn new() -> Self {
        Self {
            handlers: HashMap::new(),
            serializer: Serializer::new(EncodingFormat::Json),
        }
    }

    pub fn register_handler(&mut self, method_id: u16, handler: BoxedRpcHandler) {
        self.handlers.insert(method_id, handler);
    }

    pub fn handle_frame(&self, frame: &Frame) -> Result<Frame, ProtocolError> {
        let method_id = frame.message_type as u16;
        let handler = self.handlers.get(&method_id)
            .ok_or(ProtocolError::NotSupported)?;

        let response = handler.handle_request(method_id, &frame.payload)
            .map_err(|e| {
                log::error!("RPC handler error for method 0x{:04X}: {}", method_id, e.message);
                ProtocolError::InternalError
            })?;

        let mut response_frame = Frame::new(frame.message_type, response);
        response_frame.sequence = frame.sequence;

        if frame.flags & FLAG_REQUIRES_ACK != 0 {
            response_frame.flags |= FLAG_REQUIRES_ACK;
        }

        Ok(response_frame)
    }

    pub fn method_count(&self) -> usize {
        self.handlers.len()
    }

    pub fn registered_methods(&self) -> Vec<u16> {
        self.handlers.keys().copied().collect()
    }
}

impl std::fmt::Display for RpcError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "[{:?}] {}", self.code, self.message)
    }
}

impl std::error::Error for RpcError {}

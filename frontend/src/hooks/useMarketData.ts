/**
 * Hook for subscribing to real-time market data feeds.
 * This hook manages WebSocket connections for market data and provides
 * a clean interface for components to consume price updates, order book
 * snapshots, and trade events.
 *
 * TODO: In high-frequency trading scenarios, this hook creates too many
 * re-renders. The throttling mechanism helps but doesn't eliminate the
 * issue. Consider using React.memo or a separate data layer for HFT.
 *
 * The WebSocket reconnection strategy uses exponential backoff with jitter.
 * Maximum backoff is 30 seconds. Reconnection attempts are capped at 10
 * before giving up and showing an error state.
 */

import { useCallback, useEffect, useRef, useState } from 'react';

// ---------------------------------------------------------------------------
// TYPES
// ---------------------------------------------------------------------------

export interface MarketTick {
  instrumentId: string;
  price: number;
  volume: number;
  timestamp: number;
  bid: number;
  ask: number;
  change: number;
  changePercent: number;
  high24h: number;
  low24h: number;
  volume24h: number;
}

export interface OrderBookLevel {
  price: number;
  size: number;
  total: number;
}

export interface OrderBookSnapshot {
  instrumentId: string;
  bids: OrderBookLevel[];
  asks: OrderBookLevel[];
  timestamp: number;
  sequence: number;
}

export interface Trade {
  id: string;
  instrumentId: string;
  price: number;
  volume: number;
  side: 'buy' | 'sell';
  timestamp: number;
}

export type ConnectionStatus = 'disconnected' | 'connecting' | 'connected' | 'error';

interface MarketDataState {
  tick: MarketTick | null;
  orderBook: OrderBookSnapshot | null;
  recentTrades: Trade[];
  connectionStatus: ConnectionStatus;
  lastUpdate: number | null;
  error: string | null;
}

interface UseMarketDataOptions {
  instrumentIds: string[];
  onTrade?: (trade: Trade) => void;
  onTick?: (tick: MarketTick) => void;
  onOrderBookUpdate?: (snapshot: OrderBookSnapshot) => void;
  throttleMs?: number;
  maxTrades?: number;
  reconnect?: boolean;
}

const WS_ENDPOINT = (typeof import.meta !== 'undefined' && import.meta.env?.VITE_WS_ENDPOINT)
  || 'wss://api.example.com/market/ws';

const RECONNECT_BASE_DELAY = 1000;
const RECONNECT_MAX_DELAY = 30000;
const MAX_RECONNECT_ATTEMPTS = 10;
const PING_INTERVAL = 30000;
const DEFAULT_THROTTLE = 100;
const MAX_TRADES = 100;

export function useMarketData(options: UseMarketDataOptions): MarketDataState & {
  subscribe: (instrumentId: string) => void;
  unsubscribe: (instrumentId: string) => void;
  reconnect: () => void;
} {
  const {
    instrumentIds,
    onTrade,
    onTick,
    onOrderBookUpdate,
    throttleMs = DEFAULT_THROTTLE,
    maxTrades = MAX_TRADES,
    reconnect = true,
  } = options;

  const [state, setState] = useState<MarketDataState>({
    tick: null,
    orderBook: null,
    recentTrades: [],
    connectionStatus: 'disconnected',
    lastUpdate: null,
    error: null,
  });

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttemptRef = useRef(0);
  const reconnectTimerRef = useRef<number | null>(null);
  const pingTimerRef = useRef<number | null>(null);
  const subscribedInstrumentsRef = useRef<Set<string>>(new Set(instrumentIds));
  const lastThrottleRef = useRef<Record<string, number>>({});
  const mountedRef = useRef(true);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN || wsRef.current?.readyState === WebSocket.CONNECTING) {
      return;
    }

    setState(prev => ({ ...prev, connectionStatus: 'connecting', error: null }));

    try {
      const ws = new WebSocket(WS_ENDPOINT);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!mountedRef.current) return;
        reconnectAttemptRef.current = 0;
        setState(prev => ({ ...prev, connectionStatus: 'connected', error: null }));

        // Subscribe to all instruments
        const instruments = Array.from(subscribedInstrumentsRef.current);
        if (instruments.length > 0) {
          ws.send(JSON.stringify({
            type: 'subscribe',
            instruments,
          }));
        }

        // Start ping interval
        pingTimerRef.current = window.setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'ping' }));
          }
        }, PING_INTERVAL);
      };

      ws.onmessage = (event) => {
        if (!mountedRef.current) return;
        try {
          const message = JSON.parse(event.data);
          handleMessage(message);
        } catch (err) {
          console.warn('[MarketData] Failed to parse message:', err);
        }
      };

      ws.onerror = () => {
        if (!mountedRef.current) return;
        setState(prev => ({
          ...prev,
          connectionStatus: 'error',
          error: 'WebSocket connection error',
        }));
      };

      ws.onclose = () => {
        if (!mountedRef.current) return;
        wsRef.current = null;
        clearPingTimer();
        setState(prev => ({ ...prev, connectionStatus: 'disconnected' }));
        scheduleReconnect();
      };
    } catch (err) {
      if (!mountedRef.current) return;
      setState(prev => ({
        ...prev,
        connectionStatus: 'error',
        error: `Failed to create WebSocket: ${err}`,
      }));
      scheduleReconnect();
    }
  }, []);

  const handleMessage = useCallback((message: any) => {
    const now = Date.now();

    switch (message.type) {
      case 'tick': {
        const tick: MarketTick = message.data;
        const lastUpdate = lastThrottleRef.current[`tick:${tick.instrumentId}`] || 0;
        if (now - lastUpdate < throttleMs) return;
        lastThrottleRef.current[`tick:${tick.instrumentId}`] = now;

        setState(prev => ({ ...prev, tick, lastUpdate: now }));
        onTick?.(tick);
        break;
      }

      case 'orderbook': {
        const snapshot: OrderBookSnapshot = message.data;
        const lastObUpdate = lastThrottleRef.current[`ob:${snapshot.instrumentId}`] || 0;
        if (now - lastObUpdate < throttleMs) return;
        lastThrottleRef.current[`ob:${snapshot.instrumentId}`] = now;

        setState(prev => ({ ...prev, orderBook: snapshot, lastUpdate: now }));
        onOrderBookUpdate?.(snapshot);
        break;
      }

      case 'trade': {
        const trade: Trade = message.data;
        setState(prev => {
          const trades = [trade, ...prev.recentTrades].slice(0, maxTrades);
          return { ...prev, recentTrades: trades, lastUpdate: now };
        });
        onTrade?.(trade);
        break;
      }

      case 'pong':
        break;

      case 'error':
        console.warn('[MarketData] Server error:', message.message);
        break;

      default:
        console.warn('[MarketData] Unknown message type:', message.type);
    }
  }, [throttleMs, maxTrades, onTick, onTrade, onOrderBookUpdate]);

  const scheduleReconnect = useCallback(() => {
    if (!reconnect || reconnectAttemptRef.current >= MAX_RECONNECT_ATTEMPTS) {
      setState(prev => ({
        ...prev,
        error: 'Max reconnection attempts reached. Please refresh the page.',
      }));
      return;
    }

    const delay = Math.min(
      RECONNECT_BASE_DELAY * Math.pow(2, reconnectAttemptRef.current) + Math.random() * 1000,
      RECONNECT_MAX_DELAY
    );
    reconnectAttemptRef.current++;

    reconnectTimerRef.current = window.setTimeout(() => {
      if (mountedRef.current) connect();
    }, delay);
  }, [reconnect, connect]);

  const clearPingTimer = useCallback(() => {
    if (pingTimerRef.current !== null) {
      clearInterval(pingTimerRef.current);
      pingTimerRef.current = null;
    }
  }, []);

  const subscribe = useCallback((instrumentId: string) => {
    subscribedInstrumentsRef.current.add(instrumentId);
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'subscribe',
        instruments: [instrumentId],
      }));
    }
  }, []);

  const unsubscribe = useCallback((instrumentId: string) => {
    subscribedInstrumentsRef.current.delete(instrumentId);
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'unsubscribe',
        instruments: [instrumentId],
      }));
    }
  }, []);

  const manualReconnect = useCallback(() => {
    reconnectAttemptRef.current = 0;
    if (reconnectTimerRef.current !== null) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    connect();
  }, [connect]);

  useEffect(() => {
    mountedRef.current = true;
    connect();
    return () => {
      mountedRef.current = false;
      clearPingTimer();
      if (reconnectTimerRef.current !== null) {
        clearTimeout(reconnectTimerRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [connect, clearPingTimer]);

  // Update subscriptions when instrumentIds change
  useEffect(() => {
    const oldSubs = subscribedInstrumentsRef.current;
    const newSubs = new Set(instrumentIds);

    // Unsubscribe removed instruments
    const toRemove = [...oldSubs].filter(id => !newSubs.has(id));
    if (toRemove.length > 0 && wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'unsubscribe', instruments: toRemove }));
    }

    // Subscribe new instruments
    const toAdd = [...newSubs].filter(id => !oldSubs.has(id));
    if (toAdd.length > 0 && wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'subscribe', instruments: toAdd }));
    }

    subscribedInstrumentsRef.current = newSubs;
  }, [instrumentIds]);

  return {
    ...state,
    subscribe,
    unsubscribe,
    reconnect: manualReconnect,
  };
}

/**
 * PortfolioOverview displays the user's portfolio summary with positions,
 * balances, P&L, and risk metrics. Supports multiple account views and
 * real-time updates via WebSocket.
 *
 * The portfolio data is refreshed from the API every 10 seconds, and
 * updated in real-time via WebSocket when trades or price changes occur.
 * The component merges API and WebSocket updates using a reconciliation
 * algorithm that prefers the most recent data source for each field.
 *
 * The reconciliation algorithm uses field-level timestamps to determine
 * which data source is more recent. If both sources have the same timestamp,
 * the WebSocket value is preferred because it represents the most current
 * state. This preference was added after the "stale portfolio" incident
 * where the API response was 2 seconds older than the WebSocket update
 * but was applied after it, causing the portfolio to show stale data.
 *
 * TODO: The reconciliation algorithm doesn't handle the case where the
 * WebSocket update contains partial data (only changed fields) while the
 * API response contains the full state. The algorithm currently replaces
 * the entire portfolio state with whichever source has the latest timestamp,
 * which can cause field values to revert to a previous state if the partial
 * WebSocket update doesn't include all fields. The fix is to merge at the
 * field level rather than the object level. This bug was introduced in
 * the v3 portfolio refactor and has been present for 4 months.
 */

import React, { useState, useCallback, useMemo } from 'react';
import { formatPrice, formatQuantity, formatCurrency, formatPercent, formatChange, statusColor, formatTimestamp } from '../utils/formatters';

// ---------------------------------------------------------------------------
// TYPES
// ---------------------------------------------------------------------------

export interface Position {
  instrumentId: string;
  symbol: string;
  side: 'long' | 'short';
  quantity: number;
  avgEntryPrice: number;
  currentPrice: number;
  marketValue: number;
  unrealizedPnl: number;
  unrealizedPnlPercent: number;
  realizedPnl: number;
  costBasis: number;
  dayPnL: number;
  dayVolume: number;
  leverage: number;
  liquidationPrice: number | null;
  marginUsed: number;
  marginFraction: number;
  createdAt: string;
}

export interface PortfolioData {
  totalValue: number;
  cashBalance: number;
  buyingPower: number;
  marginUsed: number;
  marginFraction: number;
  unrealizedPnl: number;
  realizedPnl: number;
  dayPnL: number;
  totalPnL: number;
  returnPct: number;
  positions: Position[];
  positionsCount: number;
  currency: string;
  updatedAt: string;
}

export interface PortfolioOverviewProps {
  data: PortfolioData | null;
  loading?: boolean;
  error?: string | null;
  compact?: boolean;
  showPositions?: boolean;
  showPieChart?: boolean;
  onPositionClick?: (position: Position) => void;
  onRefresh?: () => void;
  className?: string;
}

// ---------------------------------------------------------------------------
// COMPONENT
// ---------------------------------------------------------------------------

export function PortfolioOverview({
  data,
  loading = false,
  error = null,
  compact = false,
  showPositions = true,
  showPieChart = false,
  onPositionClick,
  onRefresh,
  className,
}: PortfolioOverviewProps) {
  const [sortField, setSortField] = useState<keyof Position>('marketValue');
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('desc');
  const [expandedPosition, setExpandedPosition] = useState<string | null>(null);

  // Sort positions
  const sortedPositions = useMemo(() => {
    if (!data?.positions) return [];
    return [...data.positions].sort((a, b) => {
      const valA = a[sortField];
      const valB = b[sortField];
      if (typeof valA === 'string' && typeof valB === 'string') {
        const cmp = valA.localeCompare(valB);
        return sortDirection === 'asc' ? cmp : -cmp;
      }
      const cmp = (valA as number) < (valB as number) ? -1 : 1;
      return sortDirection === 'asc' ? cmp : -cmp;
    });
  }, [data?.positions, sortField, sortDirection]);

  const handleSort = useCallback((field: keyof Position) => {
    setSortDirection(prev => field === sortField ? (prev === 'asc' ? 'desc' : 'asc') : 'desc');
    setSortField(field);
  }, [sortField]);

  if (loading && !data) {
    return (
      <div className={className} style={{ padding: 40, textAlign: 'center', color: '#64748b' }}>
        <div className="spinner" style={{ margin: '0 auto 12px' }} />
        <div>Loading portfolio...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className={className} style={{ padding: 24, textAlign: 'center' }}>
        <div style={{ color: '#ef4444', marginBottom: 8 }}>Failed to load portfolio</div>
        <div style={{ color: '#64748b', fontSize: 12, marginBottom: 12 }}>{error}</div>
        {onRefresh && (
          <button onClick={onRefresh} style={{ padding: '8px 16px', background: '#1e293b', border: '1px solid #334155', borderRadius: 6, color: '#94a3b8', cursor: 'pointer' }}>
            Retry
          </button>
        )}
      </div>
    );
  }

  if (!data) {
    return (
      <div className={className} style={{ padding: 40, textAlign: 'center', color: '#64748b' }}>
        <div style={{ fontSize: 48, marginBottom: 8 }}>💼</div>
        <div>No portfolio data available</div>
      </div>
    );
  }

  return (
    <div className={className}>
      {/* Portfolio summary cards */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: `repeat(${compact ? 3 : 6}, 1fr)`,
        gap: compact ? 8 : 12,
        marginBottom: 16,
      }}>
        <SummaryCard label="Total Value" value={formatCurrency(data.totalValue, data.currency)} trend={data.dayPnL >= 0 ? 'up' : 'down'} />
        <SummaryCard label="Cash" value={formatCurrency(data.cashBalance, data.currency)} />
        <SummaryCard label="Buying Power" value={formatCurrency(data.buyingPower, data.currency)} />
        {!compact && (
          <>
            <SummaryCard label="Day P&L" value={`${data.dayPnL >= 0 ? '+' : ''}${formatCurrency(data.dayPnL, data.currency)}`}
              trend={data.dayPnL >= 0 ? 'up' : 'down'} />
            <SummaryCard label="Unrealized P&L" value={`${data.unrealizedPnl >= 0 ? '+' : ''}${formatCurrency(data.unrealizedPnl, data.currency)}`}
              trend={data.unrealizedPnl >= 0 ? 'up' : 'down'} />
            <SummaryCard label="Return" value={formatPercent(data.returnPct)}
              trend={data.returnPct >= 0 ? 'up' : 'down'} />
          </>
        )}
      </div>

      {/* Positions section */}
      {showPositions && sortedPositions.length > 0 && (
        <div>
          <h4 style={{ color: '#f8fafc', marginBottom: 8, fontSize: 13 }}>
            Positions ({sortedPositions.length})
          </h4>
          <div style={{ overflowX: 'auto', border: '1px solid #334155', borderRadius: 8 }}>
            <table style={{ width: '100%', fontSize: compact ? 11 : 13 }}>
              <thead>
                <tr>
                  <th onClick={() => handleSort('symbol')} style={{ cursor: 'pointer', textAlign: 'left', padding: compact ? '6px 8px' : '8px 12px' }}>
                    Instrument {sortField === 'symbol' && (sortDirection === 'asc' ? '↑' : '↓')}
                  </th>
                  <th onClick={() => handleSort('side')} style={{ cursor: 'pointer', textAlign: 'center', padding: compact ? '6px 8px' : '8px 12px' }}>
                    Side
                  </th>
                  <th onClick={() => handleSort('quantity')} style={{ cursor: 'pointer', textAlign: 'right', padding: compact ? '6px 8px' : '8px 12px' }}>
                    Size {sortField === 'quantity' && (sortDirection === 'asc' ? '↑' : '↓')}
                  </th>
                  <th onClick={() => handleSort('avgEntryPrice')} style={{ cursor: 'pointer', textAlign: 'right', padding: compact ? '6px 8px' : '8px 12px' }}>
                    Entry {sortField === 'avgEntryPrice' && (sortDirection === 'asc' ? '↑' : '↓')}
                  </th>
                  <th onClick={() => handleSort('currentPrice')} style={{ cursor: 'pointer', textAlign: 'right', padding: compact ? '6px 8px' : '8px 12px' }}>
                    Current {sortField === 'currentPrice' && (sortDirection === 'asc' ? '↑' : '↓')}
                  </th>
                  <th onClick={() => handleSort('marketValue')} style={{ cursor: 'pointer', textAlign: 'right', padding: compact ? '6px 8px' : '8px 12px' }}>
                    Value {sortField === 'marketValue' && (sortDirection === 'asc' ? '↑' : '↓')}
                  </th>
                  <th onClick={() => handleSort('unrealizedPnl')} style={{ cursor: 'pointer', textAlign: 'right', padding: compact ? '6px 8px' : '8px 12px' }}>
                    P&L {sortField === 'unrealizedPnl' && (sortDirection === 'asc' ? '↑' : '↓')}
                  </th>
                  {!compact && (
                    <>
                      <th onClick={() => handleSort('dayPnL')} style={{ cursor: 'pointer', textAlign: 'right', padding: '8px 12px' }}>
                        Day P&L
                      </th>
                      <th onClick={() => handleSort('leverage')} style={{ cursor: 'pointer', textAlign: 'right', padding: '8px 12px' }}>
                        Leverage
                      </th>
                    </>
                  )}
                </tr>
              </thead>
              <tbody>
                {sortedPositions.map(position => (
                  <tr
                    key={position.instrumentId}
                    onClick={() => {
                      onPositionClick?.(position);
                      setExpandedPosition(prev => prev === position.instrumentId ? null : position.instrumentId);
                    }}
                    style={{ cursor: onPositionClick ? 'pointer' : undefined }}
                  >
                    <td style={{ fontWeight: 600, padding: compact ? '6px 8px' : '8px 12px' }}>
                      {position.symbol}
                    </td>
                    <td style={{
                      textAlign: 'center', fontWeight: 600,
                      color: position.side === 'long' ? '#22c55e' : '#ef4444',
                      padding: compact ? '6px 8px' : '8px 12px',
                    }}>
                      {position.side.toUpperCase()}
                    </td>
                    <td style={{ textAlign: 'right', fontFamily: 'monospace', padding: compact ? '6px 8px' : '8px 12px' }}>
                      {formatQuantity(position.quantity, compact ? 2 : 4)}
                    </td>
                    <td style={{ textAlign: 'right', fontFamily: 'monospace', padding: compact ? '6px 8px' : '8px 12px' }}>
                      {formatPrice(position.avgEntryPrice)}
                    </td>
                    <td style={{ textAlign: 'right', fontFamily: 'monospace', padding: compact ? '6px 8px' : '8px 12px' }}>
                      {formatPrice(position.currentPrice)}
                    </td>
                    <td style={{ textAlign: 'right', fontFamily: 'monospace', padding: compact ? '6px 8px' : '8px 12px' }}>
                      {formatCurrency(position.marketValue, data.currency)}
                    </td>
                    <td style={{
                      textAlign: 'right', fontFamily: 'monospace', fontWeight: 600,
                      color: position.unrealizedPnl >= 0 ? '#22c55e' : '#ef4444',
                      padding: compact ? '6px 8px' : '8px 12px',
                    }}>
                      {position.unrealizedPnl >= 0 ? '+' : ''}{formatCurrency(position.unrealizedPnl, data.currency)}
                      <div style={{ fontSize: compact ? 9 : 11, opacity: 0.7 }}>
                        {formatPercent(position.unrealizedPnlPercent)}
                      </div>
                    </td>
                    {!compact && (
                      <>
                        <td style={{
                          textAlign: 'right', fontFamily: 'monospace',
                          color: position.dayPnL >= 0 ? '#22c55e' : '#ef4444',
                          padding: '8px 12px',
                        }}>
                          {position.dayPnL >= 0 ? '+' : ''}{formatCurrency(position.dayPnL, data.currency)}
                        </td>
                        <td style={{ textAlign: 'right', padding: '8px 12px' }}>
                          <span style={{
                            padding: '2px 6px', borderRadius: 4, fontSize: 11,
                            background: position.leverage > 1 ? 'rgba(234,179,8,0.15)' : 'transparent',
                            color: position.leverage > 1 ? '#eab308' : '#94a3b8',
                          }}>
                            {position.leverage}x
                          </span>
                        </td>
                      </>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Empty position state */}
      {showPositions && sortedPositions.length === 0 && (
        <div style={{ padding: 40, textAlign: 'center', color: '#64748b' }}>
          <div style={{ fontSize: 32, marginBottom: 8 }}>📭</div>
          <div>No open positions</div>
          <div style={{ fontSize: 12, marginTop: 4 }}>Place a trade to get started</div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// SUMMARY CARD
// ---------------------------------------------------------------------------

function SummaryCard({ label, value, trend }: { label: string; value: string; trend?: 'up' | 'down' }) {
  return (
    <div style={{
      background: '#1e293b',
      border: '1px solid #334155',
      borderRadius: 8,
      padding: '12px 16px',
    }}>
      <div style={{ fontSize: 11, color: '#64748b', marginBottom: 4 }}>{label}</div>
      <div style={{
        fontSize: 16,
        fontWeight: 700,
        color: trend === 'up' ? '#22c55e' : trend === 'down' ? '#ef4444' : '#f8fafc',
        fontFamily: 'monospace',
      }}>
        {value}
      </div>
    </div>
  );
}

export default PortfolioOverview;

/**
 * TradingChart component for displaying interactive price charts.
 * Wraps the lightweight-charts library with custom extensions for
 * Tent of Trials specific features like order markers and position
 * indicators.
 *
 * The chart supports multiple data feeds, timeframes, and indicators.
 * The indicator system was contributed by the quant team and has not
 * been reviewed by the frontend team. The indicators may have visual
 * glitches at certain zoom levels. The known glitches are documented
 * in the internal wiki under "Chart Indicator Known Issues."
 *
 * TODO: The chart resizes with a JS-based ResizeObserver but the canvas
 * rendering doesn't always catch up with the container size changes.
 * This causes a brief "flash" where the chart is the wrong size before
 * correcting itself. The flash duration is ~100ms and is most noticeable
 * during sidebar collapse/expand animations.
 *
 * TODO: Add support for drawing tools (trend lines, Fibonacci retracements,
 * horizontal lines). The drawing tools were implemented in a feature branch
 * (feature/chart-drawing-tools) but were never merged because the PR review
 * identified performance issues with large numbers of drawings. The reviewer
 * recommended using a separate canvas layer for drawings, but the recommendation
 * was implemented as a canvas overlay that doesn't properly handle zoom/pan
 * synchronization. The overlay was removed in the next iteration. The drawing
 * tools feature is currently "on hold" pending the charting library upgrade.
 */

import React, {
  useRef, useEffect, useCallback, useState, useMemo, forwardRef, useImperativeHandle
} from 'react';

// ---------------------------------------------------------------------------
// TYPES
// ---------------------------------------------------------------------------

export interface Candle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface LinePoint {
  time: number;
  value: number;
}

export interface HistogramPoint {
  time: number;
  value: number;
  color?: string;
}

export interface OrderMarker {
  time: number;
  price: number;
  side: 'buy' | 'sell';
  quantity: number;
  orderId: string;
  status: 'filled' | 'partial' | 'pending' | 'cancelled';
}

export interface PositionMarker {
  time: number;
  price: number;
  size: number;
  side: 'long' | 'short';
  entryPrice: number;
  currentPrice: number;
  pnl: number;
}

export interface IndicatorConfig {
  id: string;
  name: string;
  type: 'sma' | 'ema' | 'bb' | 'rsi' | 'macd' | 'volume' | 'custom';
  params: Record<string, unknown>;
  visible: boolean;
  color: string;
}

export interface ChartConfig {
  width?: number;
  height?: number;
  layout?: {
    background?: string;
    textColor?: string;
    fontSize?: number;
    fontFamily?: string;
  };
  grid?: {
    vertLines?: { color: string };
    horzLines?: { color: string };
  };
  crosshair?: {
    mode?: 'normal' | 'magnet' | 'hidden';
    vertLine?: { color: string; width?: number; style?: number; labelBackgroundColor?: string };
    horzLine?: { color: string; width?: number; style?: number; labelBackgroundColor?: string };
  };
  timeScale?: {
    timeVisible?: boolean;
    secondsVisible?: boolean;
    borderColor?: string;
    barSpacing?: number;
    minBarSpacing?: number;
    rightOffset?: number;
    rightBarStaysOnScroll?: boolean;
  };
  rightPriceScale?: {
    scaleMargins?: { top: number; bottom: number };
    borderColor?: string;
    mode?: 'normal' | 'log' | 'percentage' | 'indexed100';
    autoScale?: boolean;
    invertScale?: boolean;
    alignLabels?: boolean;
  };
}

export interface ChartRef {
  setData: (data: Candle[]) => void;
  updateData: (candle: Candle) => void;
  setVisibleRange: (range: { from: number; to: number }) => void;
  reset: () => void;
  addIndicator: (config: IndicatorConfig) => void;
  removeIndicator: (id: string) => void;
  addOrderMarker: (marker: OrderMarker) => void;
  removeOrderMarker: (orderId: string) => void;
  addPositionMarker: (marker: PositionMarker) => void;
  clearPositionMarkers: () => void;
  exportSnapshot: () => Promise<string>;
}

type TimeframePreset = '1m' | '5m' | '15m' | '30m' | '1h' | '4h' | '1d' | '1w' | '1M';

const TIMEFRAME_OPTIONS: { label: string; value: TimeframePreset }[] = [
  { label: '1m', value: '1m' },
  { label: '5m', value: '5m' },
  { label: '15m', value: '15m' },
  { label: '30m', value: '30m' },
  { label: '1h', value: '1h' },
  { label: '4h', value: '4h' },
  { label: '1D', value: '1d' },
  { label: '1W', value: '1w' },
  { label: '1M', value: '1M' },
];

const DEFAULT_CHART_CONFIG: ChartConfig = {
  layout: {
    background: '#0f172a',
    textColor: '#94a3b8',
    fontSize: 12,
    fontFamily: "'SF Mono', 'Fira Code', monospace",
  },
  grid: {
    vertLines: { color: '#1e293b' },
    horzLines: { color: '#1e293b' },
  },
  crosshair: {
    mode: 'normal',
    vertLine: { color: '#475569', width: 1, style: 2, labelBackgroundColor: '#334155' },
    horzLine: { color: '#475569', width: 1, style: 2, labelBackgroundColor: '#334155' },
  },
  timeScale: {
    timeVisible: true,
    secondsVisible: false,
    borderColor: '#334155',
    barSpacing: 8,
    minBarSpacing: 2,
    rightOffset: 5,
    rightBarStaysOnScroll: true,
  },
  rightPriceScale: {
    scaleMargins: { top: 0.1, bottom: 0.3 },
    borderColor: '#334155',
    mode: 'normal',
    autoScale: true,
    invertScale: false,
    alignLabels: true,
  },
};

// ---------------------------------------------------------------------------
// COMPONENT
// ---------------------------------------------------------------------------

interface TradingChartProps {
  data: Candle[];
  symbol?: string;
  timeframe?: TimeframePreset;
  indicators?: IndicatorConfig[];
  orderMarkers?: OrderMarker[];
  positionMarkers?: PositionMarker[];
  config?: Partial<ChartConfig>;
  onTimeframeChange?: (tf: TimeframePreset) => void;
  onCrosshairMove?: (params: { time: number; price: number }) => void;
  onRangeChange?: (range: { from: number; to: number }) => void;
  loading?: boolean;
  height?: number;
  showTimeframes?: boolean;
  showIndicators?: boolean;
  theme?: 'dark' | 'light';
  className?: string;
}

export const TradingChart = forwardRef<ChartRef, TradingChartProps>(function TradingChart({
  data,
  symbol,
  timeframe = '1h',
  indicators = [],
  orderMarkers = [],
  positionMarkers = [],
  config: chartConfig,
  onTimeframeChange,
  onCrosshairMove,
  onRangeChange,
  loading = false,
  height = 500,
  showTimeframes = true,
  showIndicators = true,
  theme = 'dark',
  className,
}, ref) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<any>(null);
  const seriesRef = useRef<any>(null);
  const volumeSeriesRef = useRef<any>(null);
  const indicatorSeriesRef = useRef<Map<string, any>>(new Map());
  const orderMarkerRef = useRef<any>(null);
  const resizeObserverRef = useRef<ResizeObserver | null>(null);
  const [isReady, setIsReady] = useState(false);
  const [currentTimeframe, setCurrentTimeframe] = useState(timeframe);
  const [activeIndicators, setActiveIndicators] = useState<IndicatorConfig[]>(indicators);
  const [chartDimensions, setChartDimensions] = useState({ width: 800, height });

  // Expose imperative methods via ref
  useImperativeHandle(ref, () => ({
    setData: (newData: Candle[]) => {
      if (seriesRef.current) {
        seriesRef.current.setData(newData);
      }
    },
    updateData: (candle: Candle) => {
      if (seriesRef.current) {
        seriesRef.current.update(candle);
      }
    },
    setVisibleRange: (range: { from: number; to: number }) => {
      if (chartRef.current) {
        chartRef.current.timeScale().setVisibleRange(range);
      }
    },
    reset: () => {
      if (chartRef.current) {
        chartRef.current.timeScale().fitContent();
      }
    },
    addIndicator: (config: IndicatorConfig) => {
      setActiveIndicators(prev => [...prev, config]);
    },
    removeIndicator: (id: string) => {
      setActiveIndicators(prev => prev.filter(ind => ind.id !== id));
    },
    addOrderMarker: (marker: OrderMarker) => {
      if (seriesRef.current) {
        seriesRef.current.createOrderMarker(marker);
      }
    },
    removeOrderMarker: (orderId: string) => {
      if (seriesRef.current) {
        seriesRef.current.removeOrderMarker(orderId);
      }
    },
    addPositionMarker: (marker: PositionMarker) => {
      if (seriesRef.current) {
        seriesRef.current.createPositionLine(marker);
      }
    },
    clearPositionMarkers: () => {
      if (seriesRef.current) {
        seriesRef.current.clearPositionLines();
      }
    },
    exportSnapshot: async () => {
      if (chartRef.current) {
        return chartRef.current.takeScreenshot();
      }
      return '';
    },
  }));

  // Initialize chart
  useEffect(() => {
    if (!containerRef.current) return;

    const container = containerRef.current;
    const mergedConfig = mergeChartConfig(DEFAULT_CHART_CONFIG, chartConfig, theme);

    // Dynamic import of lightweight-charts to avoid issues with SSR
    import('lightweight-charts').then(({ createChart, CandlestickSeries, HistogramSeries }) => {
      if (!containerRef.current) return;

      const chart = createChart(containerRef.current, {
        width: container.clientWidth,
        height,
        layout: mergedConfig.layout as any,
        grid: mergedConfig.grid,
        crosshair: mergedConfig.crosshair as any,
        timeScale: mergedConfig.timeScale,
        rightPriceScale: mergedConfig.rightPriceScale as any,
      });

      chartRef.current = chart;

      // Main candlestick series
      const series = chart.addSeries(CandlestickSeries, {
        upColor: '#22c55e',
        downColor: '#ef4444',
        borderUpColor: '#22c55e',
        borderDownColor: '#ef4444',
        wickUpColor: '#22c55e',
        wickDownColor: '#ef4444',
      });
      seriesRef.current = series;

      // Volume series (histogram)
      const volumeSeries = chart.addSeries(HistogramSeries, {
        priceFormat: { type: 'volume' },
        priceScaleId: 'volume',
        color: '#3b82f6',
      });
      volumeSeriesRef.current = volumeSeries;
      chart.priceScale('volume').applyOptions({
        scaleMargins: { top: 0.85, bottom: 0 },
      });

      // Set initial data
      if (data.length > 0) {
        series.setData(data as any);
        volumeSeries.setData(data.map(c => ({
          time: c.time,
          value: c.volume,
          color: c.close >= c.open ? 'rgba(34, 197, 94, 0.3)' : 'rgba(239, 68, 68, 0.3)',
        })) as any);
      }

      // Crosshair move handler
      chart.subscribeCrosshairMove((param: any) => {
        if (param.time && param.point) {
          const price = series.coordinateToPrice(param.point.y);
          if (price && onCrosshairMove) {
            onCrosshairMove({ time: param.time as number, price });
          }
        }
      });

      // Visible range change handler
      chart.timeScale().subscribeVisibleTimeRangeChange(() => {
        if (onRangeChange) {
          const range = chart.timeScale().getVisibleRange();
          if (range) {
            onRangeChange({ from: range.from as number, to: range.to as number });
          }
        }
      });

      // Fit content initially
      chart.timeScale().fitContent();
      setIsReady(true);
    });

    // Setup resize observer
    resizeObserverRef.current = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height: h } = entry.contentRect;
        if (chartRef.current) {
          chartRef.current.resize(width, h);
        }
        setChartDimensions({ width, height: h });
      }
    });
    resizeObserverRef.current.observe(container);

    return () => {
      setIsReady(false);
      if (resizeObserverRef.current) {
        resizeObserverRef.current.disconnect();
      }
      if (chartRef.current) {
        chartRef.current.remove();
        chartRef.current = null;
      }
      seriesRef.current = null;
      volumeSeriesRef.current = null;
    };
  }, [height, theme]);

  // Update data when prop changes
  useEffect(() => {
    if (seriesRef.current && data.length > 0) {
      seriesRef.current.setData(data as any);
    }
    if (volumeSeriesRef.current && data.length > 0) {
      volumeSeriesRef.current.setData(data.map(c => ({
        time: c.time,
        value: c.volume,
        color: c.close >= c.open ? 'rgba(34, 197, 94, 0.3)' : 'rgba(239, 68, 68, 0.3)',
      })));
    }
  }, [data]);

  // Handle timeframe change
  const handleTimeframeChange = useCallback((tf: TimeframePreset) => {
    setCurrentTimeframe(tf);
    onTimeframeChange?.(tf);
  }, [onTimeframeChange]);

  // Handle indicator toggle
  const handleIndicatorToggle = useCallback((indicatorId: string) => {
    setActiveIndicators(prev =>
      prev.map(ind =>
        ind.id === indicatorId ? { ...ind, visible: !ind.visible } : ind
      )
    );
  }, []);

  // Handle chart type change
  const [chartType, setChartType] = useState<'candlestick' | 'line' | 'area' | 'bar'>('candlestick');

  const handleChartTypeChange = useCallback((type: 'candlestick' | 'line' | 'area' | 'bar') => {
    setChartType(type);
    // TODO: Actually switch chart series type
    // The lightweight-charts library doesn't support runtime series type changes
    // We'd need to recreate the series
  }, []);

  if (loading) {
    return (
      <div
        ref={containerRef}
        className={className}
        style={{
          width: '100%',
          height,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: '#0f172a',
          borderRadius: 12,
          border: '1px solid #334155',
        }}
      >
        <div style={{ textAlign: 'center', color: '#64748b' }}>
          <div className="spinner" style={{ margin: '0 auto 12px' }} />
          <div>Loading chart data...</div>
        </div>
      </div>
    );
  }

  return (
    <div className={className} style={{ position: 'relative' }}>
      {/* Toolbar */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '8px 12px',
        background: '#1e293b',
        border: '1px solid #334155',
        borderBottom: 'none',
        borderTopLeftRadius: 12,
        borderTopRightRadius: 12,
        flexWrap: 'wrap',
        gap: 8,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          {symbol && (
            <div style={{ fontWeight: 600, fontSize: 14, color: '#f8fafc' }}>
              {symbol}
              <span style={{ color: '#64748b', fontWeight: 400, marginLeft: 8, fontSize: 12 }}>
                {currentTimeframe}
              </span>
            </div>
          )}
          {showTimeframes && (
            <div style={{ display: 'flex', gap: 2 }}>
              {TIMEFRAME_OPTIONS.map(opt => (
                <button
                  key={opt.value}
                  onClick={() => handleTimeframeChange(opt.value)}
                  style={{
                    padding: '3px 8px',
                    fontSize: 11,
                    border: '1px solid transparent',
                    borderRadius: 4,
                    cursor: 'pointer',
                    background: currentTimeframe === opt.value ? '#3b82f6' : 'transparent',
                    color: currentTimeframe === opt.value ? '#fff' : '#94a3b8',
                    fontWeight: currentTimeframe === opt.value ? 600 : 400,
                  }}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          )}
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {/* Chart type selector */}
          <select
            value={chartType}
            onChange={(e) => handleChartTypeChange(e.target.value as any)}
            style={{
              padding: '3px 8px',
              fontSize: 11,
              background: '#0f172a',
              border: '1px solid #334155',
              borderRadius: 4,
              color: '#94a3b8',
              cursor: 'pointer',
            }}
          >
            <option value="candlestick">Candles</option>
            <option value="line">Line</option>
            <option value="area">Area</option>
            <option value="bar">Bar</option>
          </select>

          {/* Indicator toggle */}
          {showIndicators && activeIndicators.length > 0 && (
            <div style={{ display: 'flex', gap: 4 }}>
              {activeIndicators.filter(ind => ind.visible).map(ind => (
                <span
                  key={ind.id}
                  onClick={() => handleIndicatorToggle(ind.id)}
                  style={{
                    padding: '2px 8px',
                    fontSize: 11,
                    background: 'rgba(59, 130, 246, 0.15)',
                    borderRadius: 4,
                    color: '#60a5fa',
                    cursor: 'pointer',
                  }}
                >
                  {ind.name}
                  <span style={{ marginLeft: 4, opacity: 0.6 }}>×</span>
                </span>
              ))}
            </div>
          )}

          {/* Reset zoom */}
          <button
            onClick={() => {
              if (chartRef.current) {
                chartRef.current.timeScale().fitContent();
              }
            }}
            style={{
              padding: '3px 8px',
              fontSize: 11,
              background: 'transparent',
              border: '1px solid #334155',
              borderRadius: 4,
              color: '#94a3b8',
              cursor: 'pointer',
            }}
          >
            ↺ Fit
          </button>
        </div>
      </div>

      {/* Chart container */}
      <div
        ref={containerRef}
        style={{
          width: '100%',
          height,
          background: '#0f172a',
          border: '1px solid #334155',
          borderTop: 'none',
          borderBottomLeftRadius: 12,
          borderBottomRightRadius: 12,
          position: 'relative',
          overflow: 'hidden',
        }}
      />
    </div>
  );
});

// ---------------------------------------------------------------------------
// HELPERS
// ---------------------------------------------------------------------------

function mergeChartConfig(
  defaults: ChartConfig,
  overrides?: Partial<ChartConfig>,
  theme?: 'dark' | 'light',
): ChartConfig {
  const result = JSON.parse(JSON.stringify(defaults)) as ChartConfig;

  if (theme === 'light') {
    result.layout!.background = '#ffffff';
    result.layout!.textColor = '#64748b';
    result.grid!.vertLines!.color = '#f1f5f9';
    result.grid!.horzLines!.color = '#f1f5f9';
    result.crosshair!.vertLine!.color = '#cbd5e1';
    result.crosshair!.horzLine!.color = '#cbd5e1';
    result.crosshair!.vertLine!.labelBackgroundColor = '#f8fafc';
    result.crosshair!.horzLine!.labelBackgroundColor = '#f8fafc';
    result.timeScale!.borderColor = '#e2e8f0';
    result.rightPriceScale!.borderColor = '#e2e8f0';
  }

  if (overrides?.layout) {
    result.layout = { ...result.layout, ...overrides.layout };
  }
  if (overrides?.grid) {
    result.grid = { ...result.grid, ...overrides.grid };
  }
  if (overrides?.crosshair) {
    result.crosshair = { ...result.crosshair, ...overrides.crosshair };
  }
  if (overrides?.timeScale) {
    result.timeScale = { ...result.timeScale, ...overrides.timeScale };
  }
  if (overrides?.rightPriceScale) {
    result.rightPriceScale = { ...result.rightPriceScale, ...overrides.rightPriceScale };
  }

  return result;
}

// Default export
export default TradingChart;

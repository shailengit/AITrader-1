import { useEffect, useRef } from 'react';
import {
  createChart,
  ColorType,
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  createSeriesMarkers,
  IChartApi,
  ISeriesApi,
  Time,
  CandlestickData,
  HistogramData,
  SeriesMarker,
  LineData,
  SeriesMarkerShape,
  SeriesMarkerPosition,
} from 'lightweight-charts';

interface OHLCVData {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

interface TradeMarker {
  time: number;
  price?: number;
  type: 'buy' | 'sell';
  size?: number;
  pnl?: number;
}

interface IndicatorData {
  time: number;
  value: number;
}

interface Indicator {
  name: string;
  type: string;
  data: IndicatorData[];
  color?: string;
  lineWidth?: number;
  /**
   * When false, the line series is not registered on the chart at all
   * (no legend entry, no render). When true (default) or omitted, the
   * series is created and plotted normally.
   */
  visible?: boolean;
}

interface CandleStickChartProps {
  data: OHLCVData[];
  trades?: TradeMarker[];
  indicators?: Indicator[];
  height?: number;
  cutoffDate?: string; // mm/dd/yyyy or yyyy-mm-dd dashed vertical line
  visibleRange?: { from: number; to: number };
}

/** Parse mm/dd/yyyy or yyyy-mm-dd to UTC timestamp in seconds. */
function parseDateToTimestamp(dateStr: string): number | null {
  // Try mm/dd/yyyy
  const slashParts = dateStr.split('/');
  if (slashParts.length === 3) {
    const month = parseInt(slashParts[0], 10);
    const day = parseInt(slashParts[1], 10);
    const year = parseInt(slashParts[2], 10);
    if (!isNaN(month) && !isNaN(day) && !isNaN(year)) {
      return Math.floor(Date.UTC(year, month - 1, day) / 1000);
    }
  }
  // Try yyyy-mm-dd
  const dashParts = dateStr.split('-');
  if (dashParts.length === 3) {
    const year = parseInt(dashParts[0], 10);
    const month = parseInt(dashParts[1], 10);
    const day = parseInt(dashParts[2], 10);
    if (!isNaN(year) && !isNaN(month) && !isNaN(day)) {
      return Math.floor(Date.UTC(year, month - 1, day) / 1000);
    }
  }
  return null;
}

/** Custom primitive to draw a dashed vertical line at a specific time. */
class VerticalLinePrimitive {
  private _chart: IChartApi | null = null;
  private _cutoffTime: Time;

  constructor(cutoffTime: Time) {
    this._cutoffTime = cutoffTime;
  }

  attached(param: any): void {
    this._chart = param.chart;
  }

  detached(): void {
    this._chart = null;
  }

  paneViews(): any[] {
    return [this._createPaneView()];
  }

  private _createPaneView(): any {
    const primitive = this;
    return {
      renderer() {
        return {
          draw(target: any) {
            if (!primitive._chart) return;
            const x = primitive._chart.timeScale().timeToCoordinate(primitive._cutoffTime);
            if (x === null) return;

            target.useBitmapCoordinateSpace((scope: any) => {
              const ctx = scope.context;
              const bitmapX = x * scope.horizontalPixelRatio;
              ctx.save();
              ctx.beginPath();
              ctx.setLineDash([6 * scope.horizontalPixelRatio, 4 * scope.horizontalPixelRatio]);
              ctx.strokeStyle = '#10B981';
              ctx.lineWidth = 2 * scope.horizontalPixelRatio;
              ctx.moveTo(bitmapX, 0);
              ctx.lineTo(bitmapX, scope.bitmapSize.height);
              ctx.stroke();
              ctx.restore();
            });
          },
        };
      },
      zOrder() {
        return 'top';
      },
    };
  }
}

export function CandleStickChart({
  data,
  trades = [],
  indicators = [],
  height = 400,
  cutoffDate,
  visibleRange,
}: CandleStickChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null);
  const indicatorSeriesRef = useRef<Record<string, ISeriesApi<'Line'>>>({});
  const cutoffLineRef = useRef<VerticalLinePrimitive | null>(null);

  const applyVisibleRange = () => {
    if (!chartRef.current) return;
    if (visibleRange?.from != null && visibleRange?.to != null) {
      try {
        chartRef.current.timeScale().setVisibleRange({
          from: Math.floor(visibleRange.from) as Time,
          to: Math.floor(visibleRange.to) as Time,
        });
        return;
      } catch (err) {
        console.error('Failed to set visible range:', err);
      }
    }
    chartRef.current.timeScale().fitContent();
  };

  // Initialize chart — runs ONCE on mount. The chart's height is later
  // adjusted via a separate effect that calls `applyOptions({ height })`
  // rather than re-initializing, so indicator series and the candle
  // series stay attached across height changes (expand/collapse).
  useEffect(() => {
    if (!chartContainerRef.current) return;

    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: '#d4d4d8',
      },
      grid: {
        vertLines: { color: 'rgba(255, 255, 255, 0.05)' },
        horzLines: { color: 'rgba(255, 255, 255, 0.05)' },
      },
      width: chartContainerRef.current.clientWidth,
      height: height,
      timeScale: {
        timeVisible: true,
        secondsVisible: false,
        borderColor: 'rgba(255, 255, 255, 0.1)',
      },
      rightPriceScale: {
        borderColor: 'rgba(255, 255, 255, 0.1)',
      },
      leftPriceScale: {
        visible: true,
        borderColor: 'rgba(255, 255, 255, 0.1)',
      },
    });

    chartRef.current = chart;

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#10b981',
      downColor: '#f43f5e',
      borderVisible: false,
      wickUpColor: '#10b981',
      wickDownColor: '#f43f5e',
      priceLineVisible: false,
    });

    candleSeriesRef.current = candleSeries;

    const handleResize = () => {
      if (chartContainerRef.current) {
        chart.applyOptions({ width: chartContainerRef.current.clientWidth });
      }
    };

    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
      volumeSeriesRef.current = null;
      cutoffLineRef.current = null;
    };
  }, []);

  // Adjust chart height without tearing down the chart. Runs whenever
  // the height prop changes. Lightweight-charts accepts a height change
  // via `applyOptions` and the series stay attached across height
  // changes (expand/collapse, full-page vs drawer).
  useEffect(() => {
    if (!chartRef.current) return;
    chartRef.current.applyOptions({ height });
  }, [height]);

  // Update candlestick data
  useEffect(() => {
    if (!candleSeriesRef.current || !data.length) return;

    const cleanData: CandlestickData[] = data
      .filter((d) => d && typeof d.time === 'number' && !isNaN(d.time))
      .map((d) => ({
        time: Math.floor(d.time) as Time,
        open: d.open || 0,
        high: d.high || 0,
        low: d.low || 0,
        close: d.close || 0,
      }))
      .filter(
        (item, index, self) =>
          index === self.findIndex((t) => t.time === item.time)
      )
      .sort((a, b) => (a.time as number) - (b.time as number));

    candleSeriesRef.current.setData(cleanData);

    // Add volume if present
    const hasVolume = data.some((d) => d.volume > 0);
    if (hasVolume && chartRef.current) {
      if (!volumeSeriesRef.current) {
        const volumeSeries = chartRef.current.addSeries(HistogramSeries, {
          color: '#3b82f6',
          priceFormat: { type: 'volume' },
          priceScaleId: 'left',
        });

        volumeSeries.priceScale().applyOptions({
          scaleMargins: {
            top: 0.8,
            bottom: 0,
          },
        });
        // Ensure volume is visible by not auto-scaling with price data
        candleSeriesRef.current.priceScale().applyOptions({
          scaleMargins: {
            top: 0,
            bottom: 0.2,
          },
        });

        volumeSeriesRef.current = volumeSeries;
      }

      // Create a lookup map for OHLCV data by time
      const dataByTime = new Map<number, OHLCVData>();
      data.forEach((d) => {
        const timeKey = Math.floor(d.time);
        dataByTime.set(timeKey, d);
      });

      const volData: HistogramData[] = cleanData.map((d) => {
        const original = dataByTime.get(d.time as number);
        return {
          time: d.time,
          value: original?.volume || 0,
          color:
            d.close >= d.open
              ? 'rgba(16, 185, 129, 0.65)'
              : 'rgba(244, 63, 94, 0.65)',
        };
      });

      volumeSeriesRef.current.setData(volData);
    }

    applyVisibleRange();
  }, [data]);

  // Update trade markers
  useEffect(() => {
    if (!candleSeriesRef.current || !trades.length) return;

    const markers: SeriesMarker<Time>[] = trades
      .filter((trade) => trade && trade.time && trade.type)
      .map((trade) => ({
        time: Math.floor(trade.time) as Time,
        position: (trade.type === 'buy' ? 'belowBar' : 'aboveBar') as SeriesMarkerPosition,
        color: trade.type === 'buy' ? '#10b981' : '#f43f5e',
        shape: (trade.type === 'buy' ? 'arrowUp' : 'arrowDown') as SeriesMarkerShape,
        text: trade.type.toUpperCase(),
        size: 1,
        price: trade.price || 0,
      }))
      .sort((a, b) => (a.time as number) - (b.time as number));

    if (markers.length > 0) {
      createSeriesMarkers(candleSeriesRef.current, markers);
    }
  }, [trades]);

  // Update indicators
  useEffect(() => {
    if (!chartRef.current || !indicators.length) return;

    // Clear existing indicator series
    Object.values(indicatorSeriesRef.current).forEach((series) => {
      if (series && chartRef.current) {
        try {
          chartRef.current.removeSeries(series);
        } catch {
          // Series may already be removed during unmount; ignore
        }
      }
    });
    indicatorSeriesRef.current = {};

    indicators.forEach((indicator, index) => {
      // Skip indicators the caller marked invisible. The caller is
      // responsible for not sending the data; we also skip the
      // series creation entirely so the legend doesn't show a hidden
      // overlay.
      if (indicator.visible === false) return;
      if (!indicator?.data?.length) return;

      try {
        const hue = (index * 137.508) % 360;
        const color = indicator.color || `hsl(${hue}, 70%, 50%)`;

        const lineSeries = chartRef.current!.addSeries(LineSeries, {
          color: color,
          lineWidth: (indicator.lineWidth || 2) as 1 | 2 | 3 | 4,
          priceLineVisible: false,
          crosshairMarkerVisible: true,
          lastValueVisible: true,
          priceScaleId: 'right',
        });

        const indicatorData: LineData[] = indicator.data
          .filter((d) => d && d.time && d.value !== undefined)
          .map((d) => ({
            time: (typeof d.time === 'number' ? Math.floor(d.time) : d.time) as Time,
            value: d.value,
          }))
          .sort((a, b) => (a.time as number) - (b.time as number));

        lineSeries.setData(indicatorData);
        indicatorSeriesRef.current[indicator.name] = lineSeries;
      } catch (error) {
        console.error('Failed to add indicator:', indicator.name, error);
      }
    });

    applyVisibleRange();
  }, [indicators]);

  // Re-apply visible range whenever the prop changes (e.g. returning to Dashboard)
  useEffect(() => {
    applyVisibleRange();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visibleRange?.from, visibleRange?.to]);

  // Draw dashed green vertical line at cutoff date using custom primitive
  useEffect(() => {
    if (!chartRef.current || !candleSeriesRef.current || !cutoffDate || !data.length) {
      if (cutoffLineRef.current && candleSeriesRef.current) {
        try {
          candleSeriesRef.current.detachPrimitive(cutoffLineRef.current);
        } catch { /* ignore */ }
        cutoffLineRef.current = null;
      }
      return;
    }

    const cutoffTs = parseDateToTimestamp(cutoffDate);
    if (cutoffTs === null) return;

    // Find the nearest data point time to the cutoff for exact timeToCoordinate match
    let nearestTime = data[0].time;
    let minDiff = Math.abs(data[0].time - cutoffTs);
    for (const d of data) {
      const diff = Math.abs(d.time - cutoffTs);
      if (diff < minDiff) {
        minDiff = diff;
        nearestTime = d.time;
      }
    }

    try {
      if (cutoffLineRef.current && candleSeriesRef.current) {
        candleSeriesRef.current.detachPrimitive(cutoffLineRef.current);
      }
      const primitive = new VerticalLinePrimitive(Math.floor(nearestTime) as Time);
      candleSeriesRef.current.attachPrimitive(primitive);
      cutoffLineRef.current = primitive;
    } catch (err) {
      console.error('Failed to draw cutoff line:', err);
    }
  }, [cutoffDate, data]);

  return (
    <div
      ref={chartContainerRef}
      className="w-full relative"
      style={{ height: `${height}px` }}
    />
  );
}

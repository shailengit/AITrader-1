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
}

interface CandleStickChartProps {
  data: OHLCVData[];
  trades?: TradeMarker[];
  indicators?: Indicator[];
  height?: number;
}

export function CandleStickChart({
  data,
  trades = [],
  indicators = [],
  height = 400,
}: CandleStickChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null);
  const indicatorSeriesRef = useRef<Record<string, ISeriesApi<'Line'>>>({});

  // Initialize chart
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
    };
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

    chartRef.current?.timeScale().fitContent();
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

    chartRef.current?.timeScale().fitContent();
  }, [indicators]);

  return (
    <div
      ref={chartContainerRef}
      className="w-full relative"
      style={{ height: `${height}px` }}
    />
  );
}

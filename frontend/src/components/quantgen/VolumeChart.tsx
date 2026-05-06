import { useEffect, useRef } from 'react';
import {
  createChart,
  ColorType,
  HistogramSeries,
  IChartApi,
  ISeriesApi,
  Time,
} from 'lightweight-charts';

interface VolumeData {
  time: number;
  value: number;
  color?: string;
}

interface VolumeChartProps {
  data: VolumeData[];
  height?: number;
}

export function VolumeChart({
  data,
  height = 200,
}: VolumeChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null);

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
    });

    chartRef.current = chart;

    const volumeSeries = chart.addSeries(HistogramSeries, {
      color: '#3b82f6',
      priceFormat: { type: 'volume' },
    });

    volumeSeriesRef.current = volumeSeries;

    const handleResize = () => {
      if (chartContainerRef.current) {
        chart.applyOptions({ width: chartContainerRef.current.clientWidth });
      }
    };

    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.remove();
    };
  }, [height]);

  // Update volume data
  useEffect(() => {
    if (!volumeSeriesRef.current || !data.length) return;

    const cleanData = data
      .filter((d) => d && typeof d.time === 'number' && !isNaN(d.time))
      .map((d) => ({
        time: Math.floor(d.time) as Time,
        value: d.value || 0,
        color: d.color,
      }))
      .filter(
        (item, index, self) =>
          index === self.findIndex((t) => t.time === item.time)
      )
      .sort((a, b) => (a.time as number) - (b.time as number));

    volumeSeriesRef.current.setData(cleanData);
    chartRef.current?.timeScale().fitContent();
  }, [data]);

  return (
    <div
      ref={chartContainerRef}
      className="w-full relative"
      style={{ height: `${height}px` }}
    />
  );
}

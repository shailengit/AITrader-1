import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { Map as MapIcon, List as ListIcon, TrendingUp, Eye, EyeOff } from 'lucide-react';
import { motion } from 'framer-motion';
import { useState, useMemo, useRef, useEffect } from 'react';

interface WFOWindow {
  window: number;
  train_start: string;
  train_end: string;
  test_start?: string;
  test_end?: string;
  test_date?: string;
  best_param: string;
  train_metric: number;
  test_metric?: number;
  signal?: 'BUY' | 'SELL' | 'HOLD';
}

interface HeatmapRow {
  metric: number;
  [key: string]: number | string;
}

interface OptimizationData {
  mode: 'simple' | 'wfo' | 'true_wfo';
  heatmap?: HeatmapRow[];
  windows?: WFOWindow[];
  oos_equity?: { time: number | string; value: number }[];
  max_windows?: number;
}

interface OptimizationResultsProps {
  data: OptimizationData;
}

export default function OptimizationResults({ data }: OptimizationResultsProps) {
  if (!data) return null;

  const { mode, heatmap, windows, oos_equity, max_windows } = data;
  const fmt = (val: number | string | undefined) => {
    if (typeof val === 'number') return val.toFixed(3);
    return val ?? 'N/A';
  };

  const [showAllWindows, setShowAllWindows] = useState(false);
  const DEFAULT_WINDOW_LIMIT = 10;
  const tableContainerRef = useRef<HTMLDivElement>(null);

  const displayWindows = useMemo(() => {
    if (!windows) return [];
    return showAllWindows ? windows : windows.slice(0, DEFAULT_WINDOW_LIMIT);
  }, [windows, showAllWindows]);

  const [visibleRange, setVisibleRange] = useState({ start: 0, end: 50 });
  const ROW_HEIGHT = 40;

  useEffect(() => {
    if (!tableContainerRef.current || !showAllWindows) return;
    const container = tableContainerRef.current;
    const handleScroll = () => {
      const scrollTop = container.scrollTop;
      const ch = container.clientHeight;
      const start = Math.floor(scrollTop / ROW_HEIGHT);
      const end = Math.min(start + Math.ceil(ch / ROW_HEIGHT) + 10, windows?.length || 0);
      setVisibleRange({ start: Math.max(0, start - 5), end });
    };
    container.addEventListener('scroll', handleScroll);
    handleScroll();
    return () => container.removeEventListener('scroll', handleScroll);
  }, [showAllWindows, windows?.length]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        <h2 style={{ fontSize: '18px', fontWeight: 700, letterSpacing: '-0.02em', color: 'var(--accent)' }}>
          {mode === 'wfo' || mode === 'true_wfo' ? 'Walk-Forward Analysis' : 'Optimization Results'}
        </h2>
      </motion.div>

      {/* Max Windows info */}
      {(mode === 'wfo' || mode === 'true_wfo') && max_windows && (
        <div style={{ padding: '10px 14px', borderRadius: '10px', backgroundColor: 'var(--surface)', border: '1px solid var(--border)', fontSize: '12px', color: 'var(--muted)' }}>
          <strong>Max Possible Windows:</strong> {max_windows} |{' '}
          <strong>Windows Used:</strong> {windows?.length || 0}
          {windows && windows.length < max_windows && (
            <span style={{ color: '#f59e0b', marginLeft: '6px' }}>(capped from config)</span>
          )}
        </div>
      )}

      {/* OOS Equity Curve */}
      {(mode === 'wfo' || mode === 'true_wfo') && oos_equity && oos_equity.length > 0 && (
        <div style={{ borderRadius: '14px', padding: '20px', backgroundColor: 'var(--surface)', border: '1px solid var(--border)' }}>
          <h3 style={{ fontSize: '13px', fontWeight: 600, color: 'var(--foreground)', marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '6px' }}>
            <TrendingUp size={14} style={{ color: 'var(--accent)' }} /> Out-of-Sample Equity (Stitched)
          </h3>
          <div style={{ height: '240px' }}>
            <ResponsiveContainer width="99%" height="100%">
              <AreaChart data={oos_equity}>
                <defs>
                  <linearGradient id="colorOOS" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" opacity={0.3} vertical={false} />
                <XAxis dataKey="time" tickFormatter={(v) => typeof v === 'number' ? new Date(v * 1000).toISOString().split('T')[0] : String(v).split('T')[0]} tick={{ fontSize: 10, fill: 'var(--muted)' }} minTickGap={50} />
                <YAxis domain={['auto', 'auto']} tick={{ fontSize: 10, fill: 'var(--muted)' }} />
                <Tooltip contentStyle={{ backgroundColor: 'var(--surface)', borderColor: 'var(--border)', borderRadius: '8px' }} labelFormatter={(v) => typeof v === 'number' ? new Date(v * 1000).toISOString().split('T')[0] : String(v).split('T')[0]} />
                <Area type="monotone" dataKey="value" stroke="#10b981" fill="url(#colorOOS)" strokeWidth={2} name="OOS Equity" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* WFO Windows Table */}
      {(mode === 'wfo' || mode === 'true_wfo') && windows && (
        <div style={{ borderRadius: '14px', overflow: 'hidden', backgroundColor: 'var(--surface)', border: '1px solid var(--border)' }}>
          <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border)', backgroundColor: 'var(--surface-raised)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', fontWeight: 600, color: 'var(--foreground)' }}>
              <ListIcon size={15} /> Walk-Forward Windows
              <span style={{ fontSize: '11px', fontWeight: 400, color: 'var(--muted)' }}>({windows.length} total)</span>
            </div>
            <button
              onClick={() => setShowAllWindows(!showAllWindows)}
              style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '6px 12px', fontSize: '11px', fontWeight: 600, borderRadius: '8px', border: '1px solid var(--border)', cursor: 'pointer', backgroundColor: 'var(--surface)', color: 'var(--muted)' }}
            >
              {showAllWindows ? <><EyeOff size={13} /> Show First {DEFAULT_WINDOW_LIMIT}</> : <><Eye size={13} /> Show All {windows.length > DEFAULT_WINDOW_LIMIT && `(${windows.length})`}</>}
            </button>
          </div>

          {!showAllWindows && windows.length > DEFAULT_WINDOW_LIMIT && (
            <div style={{ padding: '8px 16px', backgroundColor: 'rgba(245, 158, 11, 0.08)', borderBottom: '1px solid rgba(245, 158, 11, 0.15)', fontSize: '11px', color: '#f59e0b', display: 'flex', alignItems: 'center', gap: '8px' }}>
              Showing first {DEFAULT_WINDOW_LIMIT} of {windows.length} windows.
              <button onClick={() => setShowAllWindows(true)} style={{ background: 'none', border: 'none', color: '#f59e0b', textDecoration: 'underline', cursor: 'pointer', fontSize: '11px', padding: 0 }}>Show all</button>
            </div>
          )}

          <div ref={tableContainerRef} style={{ overflowX: 'auto', overflowY: showAllWindows ? 'auto' : 'hidden', maxHeight: showAllWindows ? '400px' : undefined }}>
            <table style={{ width: '100%', fontSize: '12px', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ backgroundColor: 'var(--canvas)', fontSize: '10px', letterSpacing: '0.04em', textTransform: 'uppercase', color: 'var(--muted)' }}>
                  <th style={{ padding: '8px 12px', textAlign: 'left', position: 'sticky', top: 0, backgroundColor: 'var(--canvas)' }}>Window</th>
                  <th style={{ padding: '8px 12px', textAlign: 'left', position: 'sticky', top: 0, backgroundColor: 'var(--canvas)' }}>Train Range</th>
                  {mode === 'true_wfo' ? (
                    <>
                      <th style={{ padding: '8px 12px', textAlign: 'left', position: 'sticky', top: 0, backgroundColor: 'var(--canvas)' }}>Test Date</th>
                      <th style={{ padding: '8px 12px', textAlign: 'left', position: 'sticky', top: 0, backgroundColor: 'var(--canvas)' }}>Best Param</th>
                      <th style={{ padding: '8px 12px', textAlign: 'center', position: 'sticky', top: 0, backgroundColor: 'var(--canvas)' }}>Signal</th>
                    </>
                  ) : (
                    <>
                      <th style={{ padding: '8px 12px', textAlign: 'left', position: 'sticky', top: 0, backgroundColor: 'var(--canvas)' }}>Test Range</th>
                      <th style={{ padding: '8px 12px', textAlign: 'left', position: 'sticky', top: 0, backgroundColor: 'var(--canvas)' }}>Best Param</th>
                      <th style={{ padding: '8px 12px', textAlign: 'right', position: 'sticky', top: 0, backgroundColor: 'var(--canvas)' }}>Train Metric</th>
                      <th style={{ padding: '8px 12px', textAlign: 'right', position: 'sticky', top: 0, backgroundColor: 'var(--canvas)' }}>Test Metric</th>
                    </>
                  )}
                </tr>
              </thead>
              <tbody>
                {showAllWindows ? (
                  <>
                    <tr style={{ height: `${visibleRange.start * ROW_HEIGHT}px` }} />
                    {windows.slice(visibleRange.start, visibleRange.end).map((w, idx) => {
                      const actualIndex = visibleRange.start + idx;
                      return (
                        <tr key={actualIndex} style={{ borderTop: '1px solid var(--border)' }}>
                          <td style={{ padding: '8px 12px', fontFamily: 'JetBrains Mono, monospace', color: 'var(--foreground)' }}>{w.window}</td>
                          <td style={{ padding: '8px 12px', color: 'var(--foreground)' }}>{w.train_start} → {w.train_end}</td>
                          {mode === 'true_wfo' ? (
                            <>
                              <td style={{ padding: '8px 12px', color: 'var(--muted)', fontSize: '11px' }}>{w.test_date || '-'}</td>
                              <td style={{ padding: '8px 12px', fontFamily: 'JetBrains Mono, monospace', color: 'var(--accent)', fontSize: '11px' }}>{w.best_param}</td>
                              <td style={{ padding: '8px 12px', textAlign: 'center' }}>
                                {w.signal === 'BUY' ? <span style={{ padding: '2px 8px', borderRadius: '4px', fontSize: '10px', fontWeight: 700, backgroundColor: 'rgba(16,185,129,0.15)', color: 'var(--accent)' }}>BUY</span>
                                : w.signal === 'SELL' ? <span style={{ padding: '2px 8px', borderRadius: '4px', fontSize: '10px', fontWeight: 700, backgroundColor: 'rgba(244,63,94,0.15)', color: '#f43f5e' }}>SELL</span>
                                : <span style={{ padding: '2px 8px', borderRadius: '4px', fontSize: '10px', backgroundColor: 'var(--surface-overlay)', color: 'var(--muted)' }}>HOLD</span>}
                              </td>
                            </>
                          ) : (
                            <>
                              <td style={{ padding: '8px 12px', color: 'var(--muted)', fontSize: '11px' }}>{w.test_start && w.test_end ? `${w.test_start} → ${w.test_end}` : 'Next Day'}</td>
                              <td style={{ padding: '8px 12px', fontFamily: 'JetBrains Mono, monospace', color: 'var(--accent)', fontSize: '11px' }}>{w.best_param}</td>
                              <td style={{ padding: '8px 12px', textAlign: 'right', color: 'var(--foreground)', fontVariantNumeric: 'tabular-nums' }}>{fmt(w.train_metric)}</td>
                              <td style={{ padding: '8px 12px', textAlign: 'right', fontWeight: 700, fontVariantNumeric: 'tabular-nums', color: w.test_metric && w.test_metric > 0 ? 'var(--accent)' : '#f43f5e' }}>{fmt(w.test_metric)}</td>
                            </>
                          )}
                        </tr>
                      );
                    })}
                    <tr style={{ height: `${(windows.length - visibleRange.end) * ROW_HEIGHT}px` }} />
                  </>
                ) : (
                  displayWindows.map((w, i) => (
                    <tr key={i} style={{ borderTop: '1px solid var(--border)' }}>
                      <td style={{ padding: '8px 12px', fontFamily: 'JetBrains Mono, monospace', color: 'var(--foreground)' }}>{w.window}</td>
                      <td style={{ padding: '8px 12px', color: 'var(--foreground)' }}>{w.train_start} → {w.train_end}</td>
                      {mode === 'true_wfo' ? (
                        <>
                          <td style={{ padding: '8px 12px', color: 'var(--muted)', fontSize: '11px' }}>{w.test_date || '-'}</td>
                          <td style={{ padding: '8px 12px', fontFamily: 'JetBrains Mono, monospace', color: 'var(--accent)', fontSize: '11px' }}>{w.best_param}</td>
                          <td style={{ padding: '8px 12px', textAlign: 'center' }}>
                            {w.signal === 'BUY' ? <span style={{ padding: '2px 8px', borderRadius: '4px', fontSize: '10px', fontWeight: 700, backgroundColor: 'rgba(16,185,129,0.15)', color: 'var(--accent)' }}>BUY</span>
                            : w.signal === 'SELL' ? <span style={{ padding: '2px 8px', borderRadius: '4px', fontSize: '10px', fontWeight: 700, backgroundColor: 'rgba(244,63,94,0.15)', color: '#f43f5e' }}>SELL</span>
                            : <span style={{ padding: '2px 8px', borderRadius: '4px', fontSize: '10px', backgroundColor: 'var(--surface-overlay)', color: 'var(--muted)' }}>HOLD</span>}
                          </td>
                        </>
                      ) : (
                        <>
                          <td style={{ padding: '8px 12px', color: 'var(--muted)', fontSize: '11px' }}>{w.test_start && w.test_end ? `${w.test_start} → ${w.test_end}` : 'Next Day'}</td>
                          <td style={{ padding: '8px 12px', fontFamily: 'JetBrains Mono, monospace', color: 'var(--accent)', fontSize: '11px' }}>{w.best_param}</td>
                          <td style={{ padding: '8px 12px', textAlign: 'right', color: 'var(--foreground)', fontVariantNumeric: 'tabular-nums' }}>{fmt(w.train_metric)}</td>
                          <td style={{ padding: '8px 12px', textAlign: 'right', fontWeight: 700, fontVariantNumeric: 'tabular-nums', color: w.test_metric && w.test_metric > 0 ? 'var(--accent)' : '#f43f5e' }}>{fmt(w.test_metric)}</td>
                        </>
                      )}
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          <div style={{ padding: '8px 16px', borderTop: '1px solid var(--border)', backgroundColor: 'var(--surface-raised)', fontSize: '11px', color: 'var(--muted)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span>Showing {showAllWindows ? 'all' : displayWindows.length} of {windows.length} windows</span>
            {windows.length > DEFAULT_WINDOW_LIMIT && !showAllWindows && (
              <button onClick={() => setShowAllWindows(true)} style={{ background: 'none', border: 'none', color: 'var(--accent)', cursor: 'pointer', fontSize: '11px', fontWeight: 600 }}>Show all {windows.length} windows →</button>
            )}
          </div>
        </div>
      )}

      {/* Simple Mode: Heatmap */}
      {mode === 'simple' && heatmap && (() => {
        const sortedHeatmap = [...heatmap].sort((a, b) => (b.metric || 0) - (a.metric || 0));
        const fmtPercent = (val: number) => typeof val !== 'number' || isNaN(val) ? 'N/A' : `${(val * 100).toFixed(2)}%`;

        return (
          <div style={{ borderRadius: '14px', overflow: 'hidden', maxHeight: '500px', display: 'flex', flexDirection: 'column', backgroundColor: 'var(--surface)', border: '1px solid var(--border)' }}>
            <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border)', backgroundColor: 'var(--surface-raised)', display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', fontWeight: 600, color: 'var(--foreground)' }}>
              <MapIcon size={15} /> Parameter Heatmap (Sorted Best → Worst)
            </div>
            <div style={{ overflowY: 'auto', flex: 1 }}>
              <table style={{ width: '100%', fontSize: '12px', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ backgroundColor: 'var(--canvas)', fontSize: '10px', letterSpacing: '0.04em', textTransform: 'uppercase', color: 'var(--muted)' }}>
                    <th style={{ padding: '8px 12px', textAlign: 'left', position: 'sticky', top: 0, backgroundColor: 'var(--canvas)', width: '40px' }}>#</th>
                    {Object.keys(sortedHeatmap[0] || {}).filter((k) => k !== 'metric').map((k) => (
                      <th key={k} style={{ padding: '8px 12px', textAlign: 'left', position: 'sticky', top: 0, backgroundColor: 'var(--canvas)' }}>{k}</th>
                    ))}
                    <th style={{ padding: '8px 12px', textAlign: 'right', position: 'sticky', top: 0, backgroundColor: 'var(--canvas)' }}>Return</th>
                  </tr>
                </thead>
                <tbody>
                  {sortedHeatmap.slice(0, 100).map((row, i) => (
                    <tr key={i} style={{ borderTop: '1px solid var(--border)', backgroundColor: i === 0 ? 'rgba(16,185,129,0.06)' : 'transparent' }}>
                      <td style={{ padding: '8px 12px', color: 'var(--subtle)', fontFamily: 'JetBrains Mono, monospace', fontSize: '11px' }}>{i + 1}</td>
                      {Object.entries(row).filter(([k]) => k !== 'metric').map(([k, v]) => (
                        <td key={k} style={{ padding: '8px 12px', fontFamily: 'JetBrains Mono, monospace', color: 'var(--foreground)' }}>{v as string}</td>
                      ))}
                      <td style={{ padding: '8px 12px', textAlign: 'right', fontWeight: 700, fontVariantNumeric: 'tabular-nums', color: row.metric >= 0 ? 'var(--accent)' : '#f43f5e' }}>{fmtPercent(row.metric)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {sortedHeatmap.length > 100 && (
              <div style={{ padding: '8px', textAlign: 'center', fontSize: '11px', color: 'var(--muted)', borderTop: '1px solid var(--border)' }}>
                Showing top 100 of {sortedHeatmap.length} combinations
              </div>
            )}
          </div>
        );
      })()}
    </div>
  );
}

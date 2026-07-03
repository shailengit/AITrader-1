/**
 * Indicator descriptor — used by the chart overlay system to tell the chart
 * endpoint which column to fetch and the chart component how to render it.
 *
 * Originally defined in components/screener/ChartModal.tsx. Moved here so
 * TickerDetailDrawer (and any other component that overlays indicators on a
 * chart) can import it without pulling in the chart modal implementation.
 */
export interface IndicatorDescriptor {
  /** Backend column name (e.g. "ema_20", "sma_200") — used for fetch + data lookup. */
  id: string;
  /** Human-readable label for the toggle chip. */
  label: string;
  /** Optional fixed color override. If omitted, a color from the curated palette
   *  is assigned in the indicator's display order. */
  color?: string;
  /**
   * Optional custom-param override forwarded to the chart endpoint so the
   * same indicator with non-default params is recomputed server-side
   * (e.g. `ema_20` with `{window: 200}` for a 200-period EMA).
   */
  params?: Record<string, number>;
}

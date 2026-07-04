import { useTheme } from '../../context/ThemeContext';
import { Calendar } from 'lucide-react';

/** TickerDetail shape returned by GET /api/screener/ticker/{ticker}. */
export interface TickerDetail {
  ticker: string;
  company_name: string;
  sector: string;
  close: number;
  as_of_date: string;
  fundamentals: {
    market_cap: number | null;
    beta: number | null;
    peg_ratio: number | null;
    eps_growth_qoq: number | null;
    revenue_growth_qoq: number | null;
  };
  indicators: {
    rsi: number | null;
    macd: number | null;
    mfi: number | null;
    bbw: number | null;
    volume_ratio: number | null;
    ath_proximity: number | null;
    volume_cluster_count: number | null;
    rs_vs_sector: number | null;
  };
  earnings_next: {
    date: string | null;
    days_away: number | null;
    eps_estimate: number | null;
  } | null;
}

interface TickerMetadataPanelProps {
  data: TickerDetail | null;
  loading: boolean;
  error?: string | null;
  /** "rail" makes sections slightly tighter; "drawer" matches the existing layout. */
  variant?: 'drawer' | 'rail';
  /** Optional hide controls — both variants show price by default. Set false to hide. */
  showPrice?: boolean;
}

function formatPct(v: number | null | undefined): string {
  if (v == null) return '--';
  return `${v.toFixed(1)}%`;
}

function formatDollar(v: number | null | undefined): string {
  if (v == null) return '--';
  return v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatMarketCap(v: number | null | undefined): string {
  if (v == null) return '--';
  if (Math.abs(v) >= 1e12) return `$${(v / 1e12).toFixed(2)}T`;
  if (Math.abs(v) >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
  if (Math.abs(v) >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
  return `$${v.toLocaleString()}`;
}

export default function TickerMetadataPanel({
  data,
  loading,
  error,
  variant = 'drawer',
  showPrice = true,
}: TickerMetadataPanelProps) {
  const { isDarkMode } = useTheme();

  const colors = {
    text: isDarkMode ? '#FAFAFA' : '#1d1d1f',
    muted: isDarkMode ? 'rgba(255,255,255,0.48)' : 'rgba(0,0,0,0.48)',
    subtle: isDarkMode ? 'rgba(255,255,255,0.3)' : 'rgba(0,0,0,0.3)',
    border: isDarkMode ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)',
    surface: isDarkMode ? '#0a0a0a' : '#f5f5f7',
    surfaceRaised: isDarkMode ? '#111111' : '#fafafc',
    accent: '#10B981',
    danger: '#EF4444',
    warning: '#F59E0B',
  };

  const priceMb = variant === 'rail' ? 12 : 16;
  const sectionMb = variant === 'rail' ? 12 : 16;

  return (
    <div>
      {showPrice && (
        <div
          style={{
            display: 'flex',
            alignItems: 'baseline',
            gap: 12,
            marginBottom: priceMb,
          }}
        >
          <span style={{ fontSize: 22, fontWeight: 700, color: colors.text }}>
            ${formatDollar(data?.close)}
          </span>
          <span style={{ fontSize: 11, color: colors.subtle, marginLeft: 'auto' }}>
            as of {data?.as_of_date ?? '—'}
          </span>
        </div>
      )}

      {/* Fundamentals */}
      <div style={{ marginBottom: sectionMb }}>
        <SectionLabel colors={colors}>Fundamentals</SectionLabel>
        {loading && !data ? <SkeletonGrid colors={colors} /> : (
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: '1fr 1fr',
              gap: 1,
              backgroundColor: colors.border,
              borderRadius: 6,
              overflow: 'hidden',
              border: `1px solid ${colors.border}`,
            }}
          >
            <FundCell label="P/E (TTM)" value={null} colors={colors} hint="Not in this version" />
            <FundCell label="PEG" value={data?.fundamentals.peg_ratio} colors={colors} />
            <FundCell
              label="Mkt Cap"
              value={data ? formatMarketCap(data.fundamentals.market_cap) : null}
              colors={colors}
              asString
            />
            <FundCell
              label="Beta"
              value={data?.fundamentals.beta}
              colors={colors}
              format={(v) => v != null ? v.toFixed(2) : '--'}
            />
            <FundCell
              label="EPS Growth QoQ"
              value={data?.fundamentals.eps_growth_qoq}
              colors={colors}
              format={(v) => v != null ? `${v.toFixed(1)}%` : '--'}
              positiveIsGood
            />
            <FundCell
              label="Rev Growth QoQ"
              value={data?.fundamentals.revenue_growth_qoq}
              colors={colors}
              format={(v) => v != null ? `${v.toFixed(1)}%` : '--'}
              positiveIsGood
            />
          </div>
        )}
      </div>

      {/* Indicators */}
      <div style={{ marginBottom: sectionMb }}>
        <SectionLabel colors={colors}>Indicators</SectionLabel>
        {loading && !data ? <SkeletonLines colors={colors} /> : (
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: '1fr 1fr',
              gap: '4px 12px',
              fontSize: 12,
              color: colors.muted,
              lineHeight: 1.8,
            }}
          >
            <IndRow label="RSI (14)" value={data?.indicators.rsi} colors={colors} fmt={(v) => v.toFixed(1)} />
            <IndRow label="MACD" value={data?.indicators.macd} colors={colors} fmt={(v) => v.toFixed(2)} />
            <IndRow label="Vol Ratio" value={data?.indicators.volume_ratio} colors={colors} fmt={(v) => v.toFixed(2)} />
            <IndRow label="ATH Prox" value={data?.indicators.ath_proximity} colors={colors} fmt={(v) => formatPct(v * 100)} />
            <IndRow label="MFI (14)" value={data?.indicators.mfi} colors={colors} fmt={(v) => v.toFixed(1)} />
            <IndRow label="Vol Cluster" value={data?.indicators.volume_cluster_count} colors={colors} fmt={(v) => `${v} / 5`} />
            <IndRow label="RS vs Sector" value={data?.indicators.rs_vs_sector} colors={colors} fmt={(v) => v.toFixed(2)} />
          </div>
        )}
      </div>

      {/* Earnings */}
      {data?.earnings_next && (
        <div
          style={{
            backgroundColor:
              (data.earnings_next.days_away ?? 999) <= 14
                ? 'rgba(245,158,11,0.08)'
                : colors.surfaceRaised,
            border: `1px solid ${
              (data.earnings_next.days_away ?? 999) <= 14
                ? 'rgba(245,158,11,0.3)'
                : colors.border
            }`,
            borderRadius: 6,
            padding: '8px 10px',
            marginBottom: sectionMb,
            fontSize: 12,
          }}
        >
          <div
            style={{
              color:
                (data.earnings_next.days_away ?? 999) <= 14
                  ? colors.warning
                  : colors.muted,
              fontWeight: 600,
              marginBottom: 2,
              display: 'flex',
              alignItems: 'center',
              gap: 6,
            }}
          >
            <Calendar size={12} />
            {data.earnings_next.days_away != null
              ? `EARNINGS in ${data.earnings_next.days_away} day${data.earnings_next.days_away === 1 ? '' : 's'}`
              : 'EARNINGS upcoming'}
          </div>
          <div style={{ color: colors.text }}>
            {data.earnings_next.date ?? '—'}
            {data.earnings_next.eps_estimate != null &&
              ` · EPS est. $${data.earnings_next.eps_estimate.toFixed(2)}`}
          </div>
        </div>
      )}

      {/* Error */}
      {error && (
        <div
          style={{
            padding: '8px 10px',
            border: `1px solid ${colors.danger}50`,
            borderRadius: 6,
            color: colors.danger,
            fontSize: 12,
          }}
        >
          Failed to load detail: {error}
        </div>
      )}
    </div>
  );
}

// ── Sub-components (small, in-file) ───────────────────────

function SectionLabel({ children, colors }: { children: React.ReactNode; colors: any }) {
  return (
    <div
      style={{
        fontSize: 10,
        fontWeight: 600,
        color: colors.accent,
        letterSpacing: '0.1em',
        textTransform: 'uppercase',
        marginBottom: 8,
      }}
    >
      {children}
    </div>
  );
}

function FundCell({
  label,
  value,
  colors,
  format,
  positiveIsGood,
  asString,
  hint,
}: {
  label: string;
  value: number | string | null | undefined;
  colors: any;
  format?: (v: number) => string;
  positiveIsGood?: boolean;
  asString?: boolean;
  hint?: string;
}) {
  let display = '--';
  let textColor = colors.text;
  if (value != null) {
    if (asString) {
      display = String(value);
    } else if (typeof value === 'string') {
      display = value;
    } else if (format) {
      display = format(value);
    } else {
      display = String(value);
    }
    if (!asString && typeof value === 'number' && positiveIsGood) {
      if (value < 0) textColor = colors.danger;
      else if (value > 0) textColor = colors.accent;
    }
  }
  return (
    <div
      style={{ backgroundColor: colors.surfaceRaised, padding: '8px 10px' }}
      title={hint}
    >
      <div style={{ fontSize: 10, color: colors.muted, marginBottom: 2 }}>{label}</div>
      <div style={{ fontSize: 14, fontWeight: 600, color: textColor }}>{display}</div>
    </div>
  );
}

function IndRow({
  label,
  value,
  colors,
  fmt,
}: {
  label: string;
  value: number | null | undefined;
  colors: any;
  fmt: (v: number) => string;
}) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
      <span>{label}:</span>
      <span style={{ color: colors.text, fontWeight: 500 }}>
        {value != null ? fmt(value) : '--'}
      </span>
    </div>
  );
}

function SkeletonGrid({ colors: _colors }: { colors: any }) {
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: '1fr 1fr',
        gap: 1,
        borderRadius: 6,
        overflow: 'hidden',
        border: '1px solid rgba(255,255,255,0.08)',
      }}
    >
      {Array.from({ length: 6 }).map((_, i) => (
        <div
          key={i}
          style={{
            backgroundColor: 'rgba(255,255,255,0.04)',
            padding: '8px 10px',
            height: 50,
          }}
        />
      ))}
    </div>
  );
}

function SkeletonLines({ colors: _colors }: { colors: any }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      {Array.from({ length: 7 }).map((_, i) => (
        <div
          key={i}
          style={{
            backgroundColor: 'rgba(255,255,255,0.04)',
            height: 14,
            borderRadius: 3,
            width: i % 2 === 0 ? '90%' : '70%',
          }}
        />
      ))}
    </div>
  );
}

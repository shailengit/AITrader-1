import { Eye, EyeOff, X } from 'lucide-react';
import type { IndicatorDescriptor } from '../../../../types/indicators';

interface OverlaysListProps {
  overlays: IndicatorDescriptor[];
  /** Set of overlay ids that are currently visible on the chart. */
  activeIds: Set<string>;
  onToggle: (id: string) => void;
  onRemove: (id: string) => void;
  colors: Record<string, string>;
}

const PALETTE = ['#3B82F6', '#EF4444', '#F59E0B', '#A855F7', '#10B981', '#06B6D4', '#EC4899', '#84CC16'];

/**
 * Vertical list of active chart overlays. Each row shows a color swatch
 * (assigned in display order), the overlay's display label, a visibility
 * toggle (eye/eye-off), and a remove button. Empty state: prompt the
 * user to add an overlay.
 */
export default function OverlaysList({
  overlays,
  activeIds,
  onToggle,
  onRemove,
  colors,
}: OverlaysListProps) {
  if (overlays.length === 0) {
    return (
      <div style={{ fontSize: 11, color: colors.muted, padding: '4px 0' }}>
        No overlays. Add one below.
      </div>
    );
  }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      {overlays.map((ov, i) => {
        const active = activeIds.has(ov.id);
        return (
          <div
            key={ov.id}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              padding: '4px 8px',
              borderRadius: 6,
              backgroundColor: colors.surfaceRaised,
              border: `1px solid ${active ? colors.accent + '40' : colors.border}`,
              fontSize: 11,
              opacity: active ? 1 : 0.55,
              transition: 'opacity 150ms ease, border-color 150ms ease',
            }}
          >
            <span
              style={{
                width: 8,
                height: 8,
                borderRadius: 2,
                backgroundColor: active
                  ? PALETTE[i % PALETTE.length]
                  : colors.muted,
                flexShrink: 0,
              }}
            />
            <span
              style={{
                color: active ? colors.text : colors.muted,
                fontWeight: 500,
                flex: 1,
                textDecoration: active ? 'none' : 'line-through',
              }}
            >
              {ov.label}
            </span>
            <button
              onClick={() => onToggle(ov.id)}
              aria-label={active ? `Hide ${ov.label}` : `Show ${ov.label}`}
              title={active ? 'Hide overlay' : 'Show overlay'}
              style={{
                background: 'none',
                border: 'none',
                color: active ? colors.accent : colors.muted,
                cursor: 'pointer',
                padding: 2,
                display: 'flex',
                alignItems: 'center',
              }}
            >
              {active ? <Eye size={12} /> : <EyeOff size={12} />}
            </button>
            <button
              onClick={() => onRemove(ov.id)}
              aria-label={`Remove ${ov.label}`}
              title="Remove overlay"
              style={{
                background: 'none',
                border: 'none',
                color: colors.muted,
                cursor: 'pointer',
                padding: 2,
                display: 'flex',
                alignItems: 'center',
              }}
            >
              <X size={11} />
            </button>
          </div>
        );
      })}
    </div>
  );
}

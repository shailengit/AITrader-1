import { X } from 'lucide-react';
import type { IndicatorDescriptor } from '../../../../types/indicators';

interface OverlaysListProps {
  overlays: IndicatorDescriptor[];
  onRemove: (id: string) => void;
  colors: Record<string, string>;
}

const PALETTE = ['#3B82F6', '#EF4444', '#F59E0B', '#A855F7', '#10B981', '#06B6D4', '#EC4899', '#84CC16'];

/**
 * Vertical list of active chart overlays. Each row shows a color swatch
 * (assigned in display order), the overlay's display label, and a remove
 * button. Empty state: prompt the user to add an overlay.
 */
export default function OverlaysList({ overlays, onRemove, colors }: OverlaysListProps) {
  if (overlays.length === 0) {
    return (
      <div style={{ fontSize: 11, color: colors.muted, padding: '4px 0' }}>
        No overlays. Add one below.
      </div>
    );
  }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      {overlays.map((ov, i) => (
        <div
          key={ov.id}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            padding: '4px 8px',
            borderRadius: 6,
            backgroundColor: colors.surfaceRaised,
            border: `1px solid ${colors.border}`,
            fontSize: 11,
          }}
        >
          <span
            style={{
              width: 8,
              height: 8,
              borderRadius: 2,
              backgroundColor: PALETTE[i % PALETTE.length],
              flexShrink: 0,
            }}
          />
          <span style={{ color: colors.text, fontWeight: 500, flex: 1 }}>{ov.label}</span>
          <button
            onClick={() => onRemove(ov.id)}
            aria-label={`Remove ${ov.label}`}
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
      ))}
    </div>
  );
}

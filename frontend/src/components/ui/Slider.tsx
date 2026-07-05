import { useId } from 'react';
import { useTheme } from '../../context/ThemeContext';

interface SliderProps {
  value: number;
  onChange: (value: number) => void;
  min: number;
  max: number;
  step?: number;
  ariaLabel: string;
  disabled?: boolean;
}

/**
 * shadcn-style controlled range slider. Inline styles per the project's
 * conventions (see CLAUDE.md "Tailwind Spacing Classes Not Applied" lesson).
 */
export default function Slider({
  value, onChange, min, max, step = 1, ariaLabel, disabled = false,
}: SliderProps) {
  const { isDarkMode } = useTheme();
  const id = useId();
  const colors = {
    track: isDarkMode ? 'rgba(255,255,255,0.12)' : 'rgba(0,0,0,0.10)',
    fill: '#10B981',
    thumb: '#10B981',
    text: isDarkMode ? '#FAFAFA' : '#1d1d1f',
    muted: isDarkMode ? 'rgba(255,255,255,0.48)' : 'rgba(0,0,0,0.48)',
  };
  const pct = ((value - min) / (max - min)) * 100;

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
      <div style={{ flex: 1, position: 'relative', height: 24, display: 'flex', alignItems: 'center' }}>
        {/* Track */}
        <div
          style={{
            position: 'absolute', left: 0, right: 0, height: 4, borderRadius: 2,
            backgroundColor: colors.track,
          }}
        />
        {/* Fill */}
        <div
          style={{
            position: 'absolute', left: 0, width: `${pct}%`, height: 4, borderRadius: 2,
            backgroundColor: disabled ? colors.muted : colors.fill,
          }}
        />
        {/* Native range input on top for accessibility */}
        <input
          id={id}
          type="range"
          min={min}
          max={max}
          step={step}
          value={value}
          disabled={disabled}
          aria-label={ariaLabel}
          onChange={(e) => onChange(Number(e.target.value))}
          style={{
            position: 'absolute', inset: 0, width: '100%', height: 24,
            opacity: 0, cursor: disabled ? 'not-allowed' : 'pointer', margin: 0,
          }}
        />
        {/* Visible thumb */}
        <div
          aria-hidden
          style={{
            position: 'absolute', left: `calc(${pct}% - 8px)`, width: 16, height: 16,
            borderRadius: 8, backgroundColor: disabled ? colors.muted : colors.thumb,
            boxShadow: '0 1px 3px rgba(0,0,0,0.3)', pointerEvents: 'none',
          }}
        />
      </div>
      <span style={{ minWidth: 56, textAlign: 'right', fontSize: 12, color: colors.muted, fontVariantNumeric: 'tabular-nums' }}>
        {value} / {max}
      </span>
    </div>
  );
}

import { useTheme } from '../../../context/ThemeContext';

interface GroupHeaderProps {
  match: 'all' | 'any';
  onMatchChange: (match: 'all' | 'any') => void;
  conditionCount: number;
}

export default function GroupHeader({ match, onMatchChange, conditionCount }: GroupHeaderProps) {
  const { isDarkMode } = useTheme();

  const colors = {
    text: isDarkMode ? '#FAFAFA' : '#1d1d1f',
    muted: isDarkMode ? 'rgba(255,255,255,0.48)' : 'rgba(0,0,0,0.48)',
    border: isDarkMode ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)',
    surface: isDarkMode ? '#272729' : '#f5f5f7',
    activeBg: isDarkMode ? 'rgba(16,185,129,0.15)' : 'rgba(16,185,129,0.1)',
    activeText: '#10B981',
    inactiveBg: isDarkMode ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.04)',
    inactiveText: isDarkMode ? 'rgba(255,255,255,0.4)' : 'rgba(0,0,0,0.4)',
  };

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '12px 16px',
        borderRadius: '12px',
        border: `1px solid ${colors.border}`,
        backgroundColor: colors.surface,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <span style={{ fontSize: 14, fontWeight: 600, color: colors.text }}>
          Filter Group
        </span>
        <span
          style={{
            fontSize: 12,
            fontWeight: 500,
            color: colors.muted,
            padding: '2px 8px',
            borderRadius: 6,
            border: `1px solid ${colors.border}`,
          }}
        >
          {conditionCount} {conditionCount === 1 ? 'condition' : 'conditions'}
        </span>
      </div>

      <div
        style={{
          display: 'flex',
          borderRadius: 8,
          border: `1px solid ${colors.border}`,
          overflow: 'hidden',
        }}
      >
        <button
          onClick={() => onMatchChange('all')}
          style={{
            padding: '6px 14px',
            fontSize: 13,
            fontWeight: 600,
            border: 'none',
            cursor: 'pointer',
            backgroundColor: match === 'all' ? colors.activeBg : colors.inactiveBg,
            color: match === 'all' ? colors.activeText : colors.inactiveText,
            transition: 'all 150ms ease',
          }}
        >
          Match all
        </button>
        <button
          onClick={() => onMatchChange('any')}
          style={{
            padding: '6px 14px',
            fontSize: 13,
            fontWeight: 600,
            border: 'none',
            cursor: 'pointer',
            backgroundColor: match === 'any' ? colors.activeBg : colors.inactiveBg,
            color: match === 'any' ? colors.activeText : colors.inactiveText,
            transition: 'all 150ms ease',
          }}
        >
          Match any
        </button>
      </div>
    </div>
  );
}

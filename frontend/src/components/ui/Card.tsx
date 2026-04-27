import { HTMLAttributes, forwardRef } from 'react'
import { Link } from 'react-router-dom'
import { useTheme } from '../../context/ThemeContext'

// Base Card
interface CardProps extends HTMLAttributes<HTMLDivElement> {
  variant?: 'base' | 'raised' | 'overlay'
  hover?: boolean
}

export const Card = forwardRef<HTMLDivElement, CardProps>(
  ({ variant = 'base', hover = false, children, className = '', ...props }, ref) => {
    const { isDarkMode } = useTheme()

    // Theme-aware background colors
    const bgColors = {
      base: isDarkMode ? '#272729' : '#ffffff',
      raised: isDarkMode ? '#2a2a2d' : '#fafafc',
      overlay: isDarkMode ? '#28282a' : '#ededf2',
    }

    return (
      <div
        ref={ref}
        className={`rounded-xl ${hover ? 'transition-colors' : ''} ${className}`}
        style={{
          backgroundColor: bgColors[variant],
        }}
        {...props}
      >
        {children}
      </div>
    )
  }
)
Card.displayName = 'Card'

// Data Card - for stock tickers, metrics with accent bar
interface DataCardProps extends HTMLAttributes<HTMLDivElement> {
  accentColor?: 'apple' | 'white' | 'muted' | 'red'
  active?: boolean
}

export const DataCard = forwardRef<HTMLDivElement, DataCardProps>(
  ({ accentColor = 'apple', active = false, children, className = '', ...props }, ref) => {
    const { isDarkMode } = useTheme()

    const accentColors = {
      apple: 'border-l-[#0071e3]',
      white: isDarkMode ? 'border-l-white' : 'border-l-[#1d1d1f]',
      muted: isDarkMode ? 'border-l-[rgba(255,255,255,0.48)]' : 'border-l-[rgba(0,0,0,0.48)]',
      red: 'border-l-[#ff3b30]',
    }

    return (
      <div
        ref={ref}
        className={`rounded-lg p-6 border-l-4 ${accentColors[accentColor]} ${active ? 'shadow-[rgba(0,0,0,0.22)_3px_5px_30px_0px]' : ''} ${className}`}
        style={{
          backgroundColor: isDarkMode ? '#272729' : '#ffffff',
        }}
        {...props}
      >
        {children}
      </div>
    )
  }
)
DataCard.displayName = 'DataCard'

// Stat Card - for key metrics display
interface StatCardProps extends HTMLAttributes<HTMLDivElement> {
  label: string
  value: string | number
  change?: string
  changeType?: 'positive' | 'negative' | 'neutral'
  suffix?: string
}

export const StatCard = forwardRef<HTMLDivElement, StatCardProps>(
  ({ label, value, change, changeType = 'neutral', suffix, className = '', ...props }, ref) => {
    const { isDarkMode } = useTheme()

    const changeColors = {
      positive: isDarkMode ? 'text-[#34c759]' : 'text-[#248a3d]',
      negative: isDarkMode ? 'text-[#ff3b30]' : 'text-[#dc2626]',
      neutral: isDarkMode ? 'text-white/48' : 'text-[#6e6e73]',
    }

    const textColor = isDarkMode ? '#ffffff' : '#1d1d1f'
    const mutedColor = isDarkMode ? 'rgba(255,255,255,0.48)' : 'rgba(0,0,0,0.48)'
    const bgColor = isDarkMode ? '#272729' : '#ffffff'
    const hoverBg = isDarkMode ? '#2a2a2d' : '#fafafc'

    return (
      <div
        ref={ref}
        className={`rounded-lg p-6 text-center transition-colors ${className}`}
        style={{
          backgroundColor: bgColor,
        }}
        onMouseEnter={(e) => e.currentTarget.style.backgroundColor = hoverBg}
        onMouseLeave={(e) => e.currentTarget.style.backgroundColor = bgColor}
        {...props}
      >
        <p className="text-[28px] font-normal mb-1 tabular-nums leading-[1.14] tracking-[0.196px]" style={{ color: textColor }}>
          {value}{suffix && <span className="text-[17px] ml-1" style={{ color: mutedColor }}>{suffix}</span>}
        </p>
        <p className="text-[14px] mb-1 tracking-[-0.224px]" style={{ color: mutedColor }}>{label}</p>
        {change && <p className={`text-[14px] font-medium tracking-[-0.224px] ${changeColors[changeType]}`}>{change}</p>}
      </div>
    )
  }
)
StatCard.displayName = 'StatCard'

// Feature Card - for landing page tool cards
interface FeatureCardProps {
  title: string
  description: string
  icon: React.ReactNode
  features: string[]
  accentColor: 'emerald' | 'blue' | 'purple'
  linkTo: string
}

const featureCardStyles = {
  emerald: {
    background: 'rgba(255, 255, 255, 0.02)',
    border: 'rgba(255, 255, 255, 0.05)',
    hoverBorder: 'rgba(16, 185, 129, 0.3)',
    hoverShadow: '0 8px 32px rgba(16, 185, 129, 0.15)',
    bullet: '#10B981',
    icon: '#34D399',
    glow: 'rgba(16, 185, 129, 0.05)'
  },
  blue: {
    background: 'rgba(255, 255, 255, 0.02)',
    border: 'rgba(255, 255, 255, 0.05)',
    hoverBorder: 'rgba(59, 130, 246, 0.3)',
    hoverShadow: '0 8px 32px rgba(59, 130, 246, 0.15)',
    bullet: '#3B82F6',
    icon: '#60A5FA',
    glow: 'rgba(59, 130, 246, 0.05)'
  },
  purple: {
    background: 'rgba(255, 255, 255, 0.02)',
    border: 'rgba(255, 255, 255, 0.05)',
    hoverBorder: 'rgba(168, 85, 247, 0.3)',
    hoverShadow: '0 8px 32px rgba(168, 85, 247, 0.15)',
    bullet: '#A855F7',
    icon: '#C084FC',
    glow: 'rgba(168, 85, 247, 0.05)'
  }
}

export function FeatureCard({ title, description, icon, features, accentColor, linkTo }: FeatureCardProps) {
  const { isDarkMode } = useTheme()
  const styles = featureCardStyles[accentColor]

  // Theme-aware colors
  const colors = {
    iconBg: isDarkMode ? 'rgba(255, 255, 255, 0.05)' : '#f5f5f7',
    iconBorder: isDarkMode ? 'rgba(255, 255, 255, 0.08)' : '#d2d2d7',
    arrow: isDarkMode ? '#71717A' : '#86868b',
    title: isDarkMode ? '#FAFAFA' : '#1d1d1f',
    description: isDarkMode ? '#A1A1AA' : '#6e6e73',
    featureText: isDarkMode ? '#D4D4D8' : '#1d1d1f',
  }

  return (
    <Link
      to={linkTo}
      style={{
        display: 'block',
        background: isDarkMode ? `linear-gradient(to bottom right, ${styles.background}, ${styles.glow})` : '#ffffff',
        border: `1px solid ${isDarkMode ? styles.border : '#e5e5ea'}`,
        borderRadius: 24,
        padding: 48,
        textDecoration: 'none',
        cursor: 'pointer',
        backdropFilter: 'blur(10px)',
        transform: 'translateY(0)',
        transition: 'all 0.3s ease'
      }}
      onMouseEnter={(e) => {
        if (isDarkMode) {
          e.currentTarget.style.borderColor = styles.hoverBorder
          e.currentTarget.style.boxShadow = styles.hoverShadow
        } else {
          e.currentTarget.style.boxShadow = '0 8px 24px rgba(0,0,0,0.08)'
        }
        e.currentTarget.style.transform = 'translateY(-4px)'
      }}
      onMouseLeave={(e) => {
        if (isDarkMode) {
          e.currentTarget.style.borderColor = styles.border
        }
        e.currentTarget.style.boxShadow = 'none'
        e.currentTarget.style.transform = 'translateY(0)'
      }}
    >
      {/* Icon */}
      <div style={{
        display: 'flex',
        alignItems: 'flex-start',
        justifyContent: 'space-between',
        marginBottom: 32
      }}>
        <div style={{
          padding: 16,
          borderRadius: 16,
          border: `1px solid ${colors.iconBorder}`,
          backgroundColor: colors.iconBg,
          backdropFilter: 'blur(4px)',
          transition: 'all 0.3s ease'
        }}>
          <span style={{ color: styles.icon }}>{icon}</span>
        </div>
        <svg style={{ width: 24, height: 24, color: colors.arrow, transition: 'color 0.3s ease' }} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M5 12h14M12 5l7 7-7 7"/>
        </svg>
      </div>

      {/* Content */}
      <h3 style={{ fontSize: 28, fontWeight: 700, color: colors.title, marginBottom: 12, transition: 'color 0.3s ease' }}>{title}</h3>
      <p style={{ fontSize: 16, color: colors.description, marginBottom: 32, lineHeight: 1.6, transition: 'color 0.3s ease' }}>{description}</p>

      {/* Features */}
      <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
        {features.map((feature, i) => (
          <li key={i} style={{
            display: 'flex',
            alignItems: 'center',
            gap: 12,
            fontSize: 15,
            color: colors.featureText,
            marginBottom: 16,
            transition: 'color 0.3s ease'
          }}>
            <div style={{
              width: 8,
              height: 8,
              borderRadius: '50%',
              backgroundColor: styles.bullet,
              flexShrink: 0
            }} />
            {feature}
          </li>
        ))}
      </ul>
    </Link>
  )
}

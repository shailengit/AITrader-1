import { Link } from 'react-router-dom'
import { Database } from 'lucide-react'
import { FeatureCard, ThemeToggle } from '../components/ui'
import { Activity, BarChart2, Terminal } from 'lucide-react'
import { useTheme } from '../context/ThemeContext'

const tools = [
  {
    id: 'sectors',
    title: 'Sector Rotation Scanner',
    description: 'Analyze sector ETF performance to identify momentum and rotation patterns. Find leading stocks within outperforming sectors.',
    icon: Activity,
    color: 'emerald' as const,
    link: '/sectors',
    features: [
      'Sector acceleration metrics',
      'Momentum leader identification',
      'Bollinger Bands squeeze detection',
      '3M/6M performance spread analysis',
    ],
  },
  {
    id: 'screener',
    title: 'AI Stock Screener',
    description: 'Multi-agent AI screening with technical and fundamental analysis. Find stocks with breakouts, accumulation patterns, and EPS acceleration.',
    icon: BarChart2,
    color: 'blue' as const,
    link: '/screener',
    features: [
      'Volatility contraction detection',
      'OBV hidden accumulation',
      'EPS inflection verification',
      'AI-powered analysis workflow',
    ],
  },
  {
    id: 'quantgen',
    title: 'QuantGen Strategy Builder',
    description: 'AI-powered quantitative strategy generator with VectorBT backtesting. Create, test, and optimize trading strategies.',
    icon: Terminal,
    color: 'purple' as const,
    link: '/quantgen',
    features: [
      'AI code generation',
      'VectorBT backtesting',
      'Walk-forward optimization',
      'Strategy management',
    ],
  },
]

const stats = [
  { label: 'S&P 1500 Coverage', value: '~1,500', suffix: 'stocks' },
  { label: 'Sector ETFs', value: '11', suffix: 'sectors' },
  { label: 'Historical Data', value: 'Daily', suffix: 'OHLCV' },
  { label: 'AI Models', value: 'Agno', suffix: '+ Ollama' },
]

export default function Landing() {
  const { isDarkMode } = useTheme()

  // Theme-aware colors
  const colors = {
    bg: isDarkMode ? '#050505' : '#f5f5f7',
    text: isDarkMode ? '#ffffff' : '#1d1d1f',
    muted: isDarkMode ? '#A1A1AA' : '#6e6e73',
    subtle: isDarkMode ? '#52525B' : '#86868b',
    surface: isDarkMode ? 'rgba(255, 255, 255, 0.05)' : '#ffffff',
    border: isDarkMode ? 'rgba(255, 255, 255, 0.1)' : '#d2d2d7',
    accent: isDarkMode ? '#10B981' : '#0071e3',
    accentText: isDarkMode ? '#000000' : '#fff',
    badgeBg: isDarkMode ? 'rgba(16, 185, 129, 0.15)' : 'rgba(0, 113, 227, 0.1)',
    badgeBorder: isDarkMode ? 'rgba(16, 185, 129, 0.5)' : 'rgba(0, 113, 227, 0.2)',
    badgeText: isDarkMode ? '#6EE7B7' : '#0066cc',
    secondaryBtnBorder: isDarkMode ? 'rgba(255, 255, 255, 0.25)' : '#d2d2d7',
    secondaryBtnText: isDarkMode ? '#ffffff' : '#1d1d1f',
    orb1: isDarkMode ? 'rgba(16, 185, 129, 0.35)' : 'rgba(0, 113, 227, 0.1)',
    orb2: isDarkMode ? 'rgba(59, 130, 246, 0.25)' : 'rgba(0, 113, 227, 0.08)',
    orb3: isDarkMode ? 'rgba(168, 85, 247, 0.25)' : 'rgba(0, 113, 227, 0.06)',
    gradient: isDarkMode
      ? 'linear-gradient(to bottom, rgba(16, 185, 129, 0.15), transparent, transparent)'
      : 'linear-gradient(to bottom, rgba(0, 113, 227, 0.05), transparent, transparent)',
    heroGlow: isDarkMode
      ? 'rgba(16, 185, 129, 0.35)'
      : 'rgba(0, 113, 227, 0.05)',
    heroGlowOpacity: isDarkMode ? 0.8 : 0.2,
  }

  return (
    <div style={{ minHeight: '100vh', backgroundColor: colors.bg, transition: 'background-color 0.3s ease' }}>
      {/* Hero Section */}
      <section style={{ position: 'relative', overflow: 'hidden' }}>
        {/* Background effects */}
        <div style={{
          position: 'absolute',
          inset: 0,
          background: colors.gradient,
          transition: 'background 0.3s ease'
        }} />
        <div style={{
          position: 'absolute',
          top: 0,
          left: '50%',
          transform: 'translateX(-50%)',
          width: 800,
          height: 600,
          background: colors.heroGlow,
          borderRadius: '50%',
          filter: 'blur(100px)',
          opacity: colors.heroGlowOpacity,
          transition: 'background 0.3s ease, opacity 0.3s ease'
        }} />

        {/* Floating orbs */}
        <div style={{
          position: 'absolute',
          top: 80,
          left: '25%',
          width: 256,
          height: 256,
          background: colors.orb1,
          borderRadius: '50%',
          filter: 'blur(100px)',
          transition: 'background 0.3s ease'
        }} />
        <div style={{
          position: 'absolute',
          top: 160,
          right: '25%',
          width: 192,
          height: 192,
          background: colors.orb2,
          borderRadius: '50%',
          filter: 'blur(100px)',
          transition: 'background 0.3s ease'
        }} />
        <div style={{
          position: 'absolute',
          top: 240,
          right: '33%',
          width: 128,
          height: 128,
          background: colors.orb3,
          borderRadius: '50%',
          filter: 'blur(100px)',
          transition: 'background 0.3s ease'
        }} />

        <div style={{
          position: 'relative',
          zIndex: 1,
          maxWidth: 1280,
          margin: '0 auto',
          padding: '48px 24px'
        }}>
          {/* Header with Theme Toggle */}
          <div style={{
            display: 'flex',
            justifyContent: 'flex-end',
            paddingTop: 16,
            marginBottom: 48
          }}>
            <ThemeToggle variant="ghost" size="md" />
          </div>

          {/* Hero Content */}
          <div style={{
            textAlign: 'center',
            paddingTop: 32,
            marginBottom: 100
          }}>
            <div style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 12,
              padding: '14px 28px',
              background: colors.badgeBg,
              borderRadius: 50,
              border: `1px solid ${colors.badgeBorder}`,
              color: colors.badgeText,
              fontSize: 15,
              marginBottom: 48,
              transition: 'background-color 0.3s ease, border-color 0.3s ease, color 0.3s ease'
            }}>
              <Database style={{ width: 20, height: 20 }} />
              <span>PostgreSQL Powered</span>
            </div>

            <h1 style={{
              fontSize: 96,
              fontWeight: 800,
              color: colors.text,
              marginBottom: 24,
              letterSpacing: '-0.05em',
              lineHeight: 1.1,
              transition: 'color 0.3s ease'
            }}>
              TradeCraft
            </h1>

            <p style={{
              fontSize: 24,
              color: colors.muted,
              maxWidth: 720,
              margin: '0 auto 56px',
              lineHeight: 1.6,
              letterSpacing: '-0.01em',
              transition: 'color 0.3s ease'
            }}>
              Leverage cutting-edge AI for smarter stock screening, dynamic sector rotation, and advanced quantitative strategy building.
            </p>

            {/* CTA Buttons */}
            <div style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 24,
              marginBottom: 80
            }}>
              <Link
                to="/sectors"
                style={{
                  background: colors.accent,
                  color: colors.accentText,
                  padding: '18px 42px',
                  borderRadius: 999, // Pill shape
                  fontSize: 18,
                  fontWeight: 600,
                  textDecoration: 'none',
                  boxShadow: isDarkMode
                    ? '0 0 40px rgba(16, 185, 129, 0.4), inset 0 2px 4px rgba(255,255,255,0.2)'
                    : '0 0 30px rgba(0, 113, 227, 0.25)',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 12,
                  transition: 'all 0.3s ease'
                }}
                className="hover-lift"
              >
                Launch Scanner
                <svg style={{ width: 20, height: 20 }} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                  <path d="M5 12h14M12 5l7 7-7 7"/>
                </svg>
              </Link>
              <Link
                to="/sectors"
                style={{
                  background: isDarkMode ? 'rgba(255,255,255,0.03)' : 'transparent',
                  color: colors.secondaryBtnText,
                  padding: '18px 42px',
                  borderRadius: 999, // Pill shape
                  fontSize: 18,
                  fontWeight: 500,
                  textDecoration: 'none',
                  border: `1px solid ${colors.secondaryBtnBorder}`,
                  transition: 'all 0.3s ease'
                }}
                className="hover-lift"
              >
                Explore Features
              </Link>
            </div>

            {/* Dashboard Mockup Image */}
            <div style={{
              position: 'relative',
              maxWidth: 1200,
              margin: '0 auto',
              borderRadius: 24,
              padding: 12,
              background: isDarkMode ? 'rgba(255,255,255,0.02)' : 'rgba(0,0,0,0.02)',
              border: `1px solid ${isDarkMode ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.05)'}`,
              boxShadow: isDarkMode ? '0 30px 60px rgba(0,0,0,0.5), 0 0 100px rgba(16,185,129,0.1)' : '0 30px 60px rgba(0,0,0,0.1)',
              overflow: 'hidden',
              transform: 'perspective(1000px) rotateX(2deg)',
              transformOrigin: 'top center',
              transition: 'all 0.5s ease'
            }}>
              <img 
                src="/dashboard-mockup.png" 
                alt="TradeCraft Dashboard" 
                style={{
                  width: '100%',
                  height: 'auto',
                  borderRadius: 16,
                  display: 'block'
                }}
              />
            </div>
          </div>

          {/* Stats */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(4, 1fr)',
            gap: 24,
            marginBottom: 100
          }}>
            {stats.map((stat) => (
              <div
                key={stat.label}
                style={{
                  background: isDarkMode ? 'rgba(255, 255, 255, 0.02)' : colors.surface,
                  border: `1px solid ${isDarkMode ? 'rgba(255, 255, 255, 0.05)' : colors.border}`,
                  borderRadius: 24,
                  padding: '48px 40px',
                  textAlign: 'center',
                  boxShadow: isDarkMode ? '0 8px 32px rgba(0,0,0,0.2)' : 'none',
                  backdropFilter: 'blur(10px)',
                  transition: 'transform 0.3s ease, border-color 0.3s ease'
                }}
                className="hover-lift"
              >
                <p style={{
                  fontSize: 56,
                  fontWeight: 800,
                  color: colors.text,
                  marginBottom: 8,
                  letterSpacing: '-0.02em',
                  transition: 'color 0.3s ease'
                }}>{stat.value}</p>
                <p style={{
                  fontSize: 14,
                  color: colors.muted,
                  textTransform: 'uppercase',
                  letterSpacing: '0.15em',
                  fontWeight: 600,
                  transition: 'color 0.3s ease'
                }}>{stat.label}</p>
                {stat.suffix && (
                  <span style={{ fontSize: 16, color: colors.subtle, marginLeft: 6, fontWeight: 500, transition: 'color 0.3s ease' }}>
                    {stat.suffix}
                  </span>
                )}
              </div>
            ))}
          </div>

          {/* Section Label */}
          <div style={{ textAlign: 'center', marginBottom: 48 }}>
            <h2 style={{
              fontSize: 14,
              fontWeight: 600,
              textTransform: 'uppercase',
              letterSpacing: '0.15em',
              color: colors.subtle,
              transition: 'color 0.3s ease'
            }}>Platform Tools</h2>
          </div>

          {/* Tool Cards */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(3, 1fr)',
            gap: 48,
            marginBottom: 100
          }}>
            {tools.map((tool) => (
              <FeatureCard
                key={tool.id}
                title={tool.title}
                description={tool.description}
                icon={<tool.icon style={{ width: 32, height: 32 }} />}
                features={tool.features}
                accentColor={tool.color}
                linkTo={tool.link}
              />
            ))}
          </div>

          {/* Footer */}
          <div style={{
            textAlign: 'center',
            padding: '48px 0',
            borderTop: `1px solid ${colors.border}`,
            transition: 'border-color 0.3s ease'
          }}>
            <p style={{ fontSize: 14, color: colors.subtle, transition: 'color 0.3s ease' }}>
              Combined from StockScreener, Sector-Rotation-Scanner, and QuantGen
            </p>
          </div>
        </div>
      </section>
    </div>
  )
}

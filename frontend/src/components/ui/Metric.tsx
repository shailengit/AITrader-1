import { HTMLAttributes, forwardRef } from 'react'

type MetricSize = 'lg' | 'md' | 'sm'

interface MetricProps extends HTMLAttributes<HTMLDivElement> {
  value: string | number
  label?: string
  change?: string
  changeType?: 'positive' | 'negative' | 'neutral'
  size?: MetricSize
  prefix?: string
  suffix?: string
}

const metricSizes: Record<MetricSize, { value: string; label: string }> = {
  lg: { value: 'text-5xl font-bold', label: 'text-sm text-zinc-500 mt-1' },
  md: { value: 'text-2xl font-semibold', label: 'text-xs text-zinc-500 mt-0.5' },
  sm: { value: 'text-lg font-medium', label: 'text-xs text-zinc-500 mt-0' },
}

const changeStyles = {
  positive: 'text-emerald-400',
  negative: 'text-red-400',
  neutral: 'text-zinc-400',
}

export const Metric = forwardRef<HTMLDivElement, MetricProps>(
  ({
    value,
    label,
    change,
    changeType = 'neutral',
    size = 'md',
    prefix,
    suffix,
    className = '',
    ...props
  }, ref) => {
    const sizes = metricSizes[size]

    return (
      <div ref={ref} className={`${className}`} {...props}>
        <div className="flex items-baseline gap-1">
          {prefix && <span className="text-zinc-500">{prefix}</span>}
          <span className={`${sizes.value} text-white tabular-nums`}>{value}</span>
          {suffix && <span className="text-zinc-400">{suffix}</span>}
        </div>
        {label && <p className={sizes.label}>{label}</p>}
        {change && (
          <p className={`text-sm font-medium ${changeStyles[changeType]} mt-1`}>
            {changeType === 'positive' && '+'}{change}
          </p>
        )}
      </div>
    )
  }
)
Metric.displayName = 'Metric'

// Progress Metric with bar
interface ProgressMetricProps extends HTMLAttributes<HTMLDivElement> {
  value: string | number
  label: string
  progress: number // 0-100
  progressColor?: 'emerald' | 'blue' | 'purple' | 'zinc'
  suffix?: string
}

const progressColors = {
  emerald: 'bg-emerald-500',
  blue: 'bg-blue-500',
  purple: 'bg-purple-500',
  zinc: 'bg-zinc-500',
}

const progressTextColors = {
  emerald: 'text-emerald-400',
  blue: 'text-blue-400',
  purple: 'text-purple-400',
  zinc: 'text-zinc-400',
}

export const ProgressMetric = forwardRef<HTMLDivElement, ProgressMetricProps>(
  ({ value, label, progress, progressColor = 'emerald', suffix, className = '', ...props }, ref) => {
    return (
      <div ref={ref} className={`${className}`} {...props}>
        <div className="flex justify-between items-baseline mb-2">
          <span className="text-sm text-zinc-400">{label}</span>
          <span className={`text-lg font-mono ${progressTextColors[progressColor]} tabular-nums`}>{value}{suffix}</span>
        </div>
        <div
          className="w-full bg-zinc-800 h-2 rounded-full overflow-hidden"
          role="progressbar"
          aria-valuenow={progress}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={label}
        >
          <div
            className={`h-full rounded-full ${progressColors[progressColor]}`}
            style={{ width: `${Math.min(100, Math.max(0, progress))}%` }}
          />
        </div>
      </div>
    )
  }
)
ProgressMetric.displayName = 'ProgressMetric'
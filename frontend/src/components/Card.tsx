import { type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

interface CardProps {
  title?: string;
  subtitle?: string;
  children: ReactNode;
  className?: string;
  action?: ReactNode;
  /**
   * Visual emphasis level. `default` is the standard glass surface;
   * `emphasis` adds a subtle cyan inner glow for hero cards.
   */
  variant?: 'default' | 'emphasis';
}

export function Card({
  title,
  subtitle,
  children,
  className = '',
  action,
  variant = 'default',
}: CardProps) {
  const base = variant === 'emphasis' ? 'glass-card-emphasis' : 'glass-card';
  return (
    <section className={`${base} ${className}`} aria-label={title}>
      {(title || action) && (
        <div className="flex items-center justify-between gap-3 px-5 sm:px-6 py-4 border-b border-border-subtle">
          <div className="min-w-0">
            {title && (
              <h2 className="font-display text-[15px] font-semibold text-text-primary tracking-tight leading-tight truncate">
                {title}
              </h2>
            )}
            {subtitle && (
              <p className="text-xs text-text-muted mt-0.5 truncate">{subtitle}</p>
            )}
          </div>
          {action && <div className="shrink-0">{action}</div>}
        </div>
      )}
      <div className="p-5 sm:p-6">{children}</div>
    </section>
  );
}

interface StatCardProps {
  label: string;
  value: string | number;
  icon: ReactNode;
  trend?: string;
  /**
   * Accent color for the icon glow. Defaults to primary (cyan).
   */
  color?: 'primary' | 'green' | 'yellow' | 'red' | 'amber';
}

export function StatCard({ label, value, icon, trend, color = 'primary' }: StatCardProps) {
  const accentMap: Record<string, string> = {
    primary: 'text-primary-400 bg-primary-500/10 ring-primary-400/20',
    green: 'text-energy-green bg-emerald-500/10 ring-emerald-400/20',
    yellow: 'text-energy-yellow bg-yellow-500/10 ring-yellow-400/20',
    red: 'text-energy-red bg-rose-500/10 ring-rose-400/20',
    amber: 'text-accent-400 bg-amber-500/10 ring-amber-400/20',
  };

  return (
    <div
      className="glass-card p-5 group"
      role="status"
      aria-label={`${label}: ${value}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[11px] font-mono font-medium text-text-muted uppercase tracking-[0.12em]">
            {label}
          </p>
          <p className="font-display text-3xl font-semibold text-text-primary mt-2 tabular-nums tracking-tight leading-none">
            {value}
          </p>
          {trend && (
            <p className="text-xs text-text-secondary mt-2 font-mono">{trend}</p>
          )}
        </div>
        <div
          className={`w-10 h-10 rounded-lg flex items-center justify-center shrink-0
            transition-transform duration-200 group-hover:scale-105 ring-1
            ${accentMap[color] || accentMap.primary}`}
          aria-hidden="true"
        >
          {icon}
        </div>
      </div>
    </div>
  );
}

/* Skeleton placeholder with shimmer */
export function CardSkeleton({ lines = 3 }: { lines?: number }) {
  const { t } = useTranslation();
  return (
    <div
      className="glass-card p-6"
      aria-busy="true"
      aria-label={t('common.loading')}
    >
      <div className="h-4 bg-surface-bright rounded w-1/3 mb-4 skeleton-shimmer" />
      {Array.from({ length: lines }).map((_, i) => (
        <div
          key={i}
          className="h-3 bg-surface-bright rounded mb-3 skeleton-shimmer"
          style={{ width: `${80 - i * 15}%`, animationDelay: `${i * 100}ms` }}
        />
      ))}
    </div>
  );
}

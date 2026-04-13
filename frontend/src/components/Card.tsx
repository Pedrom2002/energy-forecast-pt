import { type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

interface CardProps {
  title?: string;
  subtitle?: string;
  children: ReactNode;
  className?: string;
  action?: ReactNode;
}

export function Card({ title, subtitle, children, className = '', action }: CardProps) {
  return (
    <section
      className={`bg-surface rounded-xl border border-border shadow-sm
        hover:shadow-md transition-shadow duration-200 ${className}`}
      aria-label={title}
    >
      {(title || action) && (
        <div className="flex items-center justify-between px-5 sm:px-6 py-4 border-b border-border">
          <div>
            {title && <h2 className="text-sm font-semibold text-text-primary">{title}</h2>}
            {subtitle && <p className="text-xs text-text-muted mt-0.5">{subtitle}</p>}
          </div>
          {action}
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
  color?: string;
}

export function StatCard({ label, value, icon, trend, color = 'primary' }: StatCardProps) {
  const colorMap: Record<string, string> = {
    primary: 'bg-primary-50 text-primary-600',
    green: 'bg-green-50 text-green-600',
    yellow: 'bg-yellow-50 text-yellow-600',
    red: 'bg-red-50 text-red-600',
    blue: 'bg-blue-50 text-blue-600',
  };

  return (
    <div
      className="bg-surface rounded-xl border border-border shadow-sm p-5
        hover:shadow-md hover:border-primary-200 transition-all duration-200
        group"
      role="status"
      aria-label={`${label}: ${value}`}
    >
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs font-medium text-text-muted uppercase tracking-wider">{label}</p>
          <p className="text-2xl font-bold text-text-primary mt-1 tabular-nums">{value}</p>
          {trend && <p className="text-xs text-text-muted mt-1.5">{trend}</p>}
        </div>
        <div
          className={`w-10 h-10 rounded-lg flex items-center justify-center
            transition-transform duration-200 group-hover:scale-105
            ${colorMap[color] || colorMap.primary}`}
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
      className="bg-surface rounded-xl border border-border shadow-sm p-6"
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

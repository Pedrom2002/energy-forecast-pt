import { useEffect, useRef, useState } from 'react';
import { motion } from 'motion/react';
import { useTranslation } from 'react-i18next';
import { useQueryClient } from '@tanstack/react-query';
import { useHealth, useMetricsSummary, useModelInfo, queryKeys } from '../api/hooks';
import { Card, CardSkeleton } from '../components/Card';
import { toast } from '../components/Toast';
import { formatKey, formatUptime, formatNumber } from '../utils/format';
import { useDocumentTitle } from '../hooks/useDocumentTitle';
import { AnimatedNumber } from '../components/motion/AnimatedNumber';
import { BentoCard } from '../components/motion/BentoCard';
import { PORTUGAL_PATH } from '../assets/portugalPath';
import HeroChart from '../components/HeroChart';
import {
  Cpu,
  AlertTriangle,
  CheckCircle,
  RefreshCw,
  Zap,
  Layers,
  Database,
  Radio,
} from 'lucide-react';

interface RegionDot {
  id: string;
  label: string;
  cx: number;
  cy: number;
}

const REGIONS: RegionDot[] = [
  { id: 'norte', label: 'Norte', cx: 6200, cy: 4500 },
  { id: 'centro', label: 'Centro', cx: 6400, cy: 10500 },
  { id: 'lisboa', label: 'Lisboa', cx: 1100, cy: 17200 },
  { id: 'alentejo', label: 'Alentejo', cx: 7400, cy: 19800 },
  { id: 'algarve', label: 'Algarve', cx: 6000, cy: 25600 },
];

function PortugalMap({ ariaLabel }: { ariaLabel: string }) {
  return (
    <svg
      viewBox="0 0 12969 26674"
      className="h-full w-full max-h-[180px]"
      aria-label={ariaLabel}
      role="img"
      preserveAspectRatio="xMidYMid meet"
    >
      <defs>
        <linearGradient id="pt-fill" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#0891b2" stopOpacity="0.55" />
          <stop offset="100%" stopColor="#22d3ee" stopOpacity="0.25" />
        </linearGradient>
      </defs>
      <path
        d={PORTUGAL_PATH}
        fill="url(#pt-fill)"
        stroke="#67e8f9"
        strokeOpacity={0.7}
        strokeWidth={40}
        strokeLinejoin="round"
      />
      {REGIONS.map((r, i) => (
        <g key={r.id}>
          <motion.circle
            cx={r.cx}
            cy={r.cy}
            r={650}
            fill="#22d3ee"
            animate={{ scale: [1, 2.2, 1], opacity: [0.6, 0, 0.6] }}
            transition={{ duration: 2, repeat: Infinity, delay: i * 0.3 }}
            style={{ transformOrigin: `${r.cx}px ${r.cy}px` }}
          />
          <circle cx={r.cx} cy={r.cy} r={240} fill="#22d3ee" stroke="#f0f6fc" strokeWidth={60} />
        </g>
      ))}
    </svg>
  );
}

function useFormatRelative() {
  const { t } = useTranslation();
  return (from: Date | null, now: Date): string => {
    if (!from) return '—';
    const diff = Math.max(0, Math.floor((now.getTime() - from.getTime()) / 1000));
    if (diff < 5) return t('common.justNow');
    if (diff < 60) return t('common.secondsAgo', { count: diff });
    if (diff < 3600) return t('common.minutesAgo', { count: Math.floor(diff / 60) });
    return t('common.hoursAgo', { count: Math.floor(diff / 3600) });
  };
}

export default function Dashboard() {
  const { t } = useTranslation();
  useDocumentTitle(t('dashboard.title'));
  const formatRelative = useFormatRelative();

  const queryClient = useQueryClient();
  const healthQ = useHealth();
  const modelInfoQ = useModelInfo();
  const metricsQ = useMetricsSummary();

  const health = healthQ.data ?? null;
  const modelInfo = modelInfoQ.data ?? null;
  const metrics = metricsQ.data ?? null;
  const loading = healthQ.isLoading || modelInfoQ.isLoading || metricsQ.isLoading;
  const error = healthQ.error
    ? healthQ.error.message || t('dashboard.connectApiError')
    : null;
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [now, setNow] = useState<Date>(new Date());
  const isInitial = useRef(true);

  useEffect(() => {
    if (healthQ.dataUpdatedAt > 0) {
      setLastUpdated(new Date(healthQ.dataUpdatedAt));
      if (!isInitial.current) toast.success(t('dashboard.dataUpdated'));
      isInitial.current = false;
    }
  }, [healthQ.dataUpdatedAt, t]);

  const load = async () => {
    await Promise.allSettled([
      queryClient.invalidateQueries({ queryKey: queryKeys.health }),
      queryClient.invalidateQueries({ queryKey: queryKeys.modelInfo }),
      queryClient.invalidateQueries({ queryKey: queryKeys.metricsSummary }),
    ]);
  };

  useEffect(() => {
    const tick = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(tick);
  }, []);

  if (loading) {
    return (
      <div className="space-y-6" aria-busy="true">
        <div className="h-28 glass-card skeleton-shimmer" />
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 stagger-children">
          {[1, 2, 3].map((i) => <CardSkeleton key={i} lines={2} />)}
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 stagger-children">
          <CardSkeleton lines={4} />
          <CardSkeleton lines={4} />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] animate-fade-in-up">
        <div className="glass-card p-8 sm:p-10 text-center max-w-md">
          <div
            className="w-14 h-14 rounded-xl bg-rose-500/10 ring-1 ring-rose-500/30
              flex items-center justify-center mx-auto mb-5"
          >
            <AlertTriangle className="w-7 h-7 text-energy-red" aria-hidden="true" />
          </div>
          <h1 className="font-display text-xl font-semibold text-text-primary tracking-tight">
            {t('dashboard.apiUnavailable')}
          </h1>
          <p className="text-sm text-text-secondary mt-2">{error}</p>
          <p className="text-xs text-text-muted mt-3">
            {t('dashboard.ensureApiRunning')}{' '}
            <code
              className="font-mono bg-surface-dim border border-border px-2 py-0.5 rounded
                text-xs text-primary-300"
            >
              localhost:8000
            </code>
          </p>
          <button
            type="button"
            onClick={() => load()}
            className="mt-6 inline-flex items-center gap-2 text-sm font-medium
              bg-primary-500 hover:bg-primary-400 text-[#05080f] px-5 min-h-[44px] rounded-lg
              transition-colors cursor-pointer shadow-[0_0_18px_rgba(34,211,238,0.35)]
              focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-300 focus-visible:ring-offset-2
              focus-visible:ring-offset-[#05080f] active:scale-[0.98]"
          >
            <RefreshCw className="w-4 h-4" aria-hidden="true" />
            {t('common.retry')}
          </button>
        </div>
      </div>
    );
  }

  const uptime = health?.uptime_seconds ? formatUptime(health.uptime_seconds) : '—';
  const modelsLoadedMap = health?.models_loaded ?? {};
  const totalModels = Object.keys(modelsLoadedMap).length;

  const isHealthy = health?.status === 'healthy';
  const statusTone = isHealthy
    ? 'bg-energy-green'
    : health?.status
      ? 'bg-energy-yellow'
      : 'bg-energy-red';
  const statusLabel = isHealthy
    ? t('dashboard.statusHealthy')
    : health?.status
      ? t('dashboard.statusDegraded')
      : t('dashboard.statusDown');

  return (
    <div className="space-y-8">
      {/* ─── Hero band ─── */}
      <section className="relative overflow-hidden rounded-2xl border border-border bg-grid px-5 sm:px-8 py-6 sm:py-8">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0
            bg-[radial-gradient(ellipse_80%_50%_at_20%_0%,rgba(34,211,238,0.12),transparent_60%),radial-gradient(ellipse_60%_40%_at_90%_30%,rgba(245,158,11,0.06),transparent_60%)]"
        />
        <div className="relative flex flex-col md:flex-row md:items-center md:justify-between gap-5">
          <div className="min-w-0">
            <div className="flex items-center gap-2 mb-3">
              <span
                className="inline-flex items-center gap-1.5 rounded-full border border-primary-400/25 bg-primary-500/10
                  px-2.5 py-1 text-[10px] font-mono font-semibold uppercase tracking-[0.14em] text-primary-300"
              >
                <Radio className="w-3 h-3" aria-hidden="true" />
                {t('common.live')}
              </span>
              <span className="flex items-center gap-1.5">
                <span className="relative flex items-center justify-center">
                  <span className={`absolute inline-flex h-2.5 w-2.5 rounded-full ${statusTone} opacity-70 animate-ping`} />
                  <span className={`relative inline-flex h-1.5 w-1.5 rounded-full ${statusTone}`} />
                </span>
                <span className="text-[11px] font-mono font-medium uppercase tracking-wider text-text-secondary">
                  {statusLabel}
                </span>
              </span>
            </div>
            <h1 className="font-display text-3xl sm:text-4xl md:text-5xl font-semibold text-text-primary tracking-tight leading-[1.05]">
              {t('dashboard.title')}{' '}
              <span className="text-gradient-signal">PT</span>
            </h1>
            <p className="mt-3 text-sm sm:text-base text-text-secondary max-w-2xl leading-relaxed">
              {t('dashboard.subtitle')}
            </p>
          </div>

          <div className="flex flex-col items-start md:items-end gap-2 shrink-0">
            <button
              type="button"
              onClick={() => load()}
              className="min-w-[44px] min-h-[44px] inline-flex items-center justify-center gap-2 text-sm font-medium
                text-text-secondary hover:text-text-primary hover:bg-white/[0.04]
                border border-border hover:border-border-strong
                rounded-lg px-4 cursor-pointer transition-colors
                focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-400"
              aria-label={t('dashboard.updateData')}
            >
              <RefreshCw className="w-4 h-4" aria-hidden="true" />
              <span className="hidden sm:inline">{t('common.refresh')}</span>
            </button>
            <p className="text-[11px] text-text-muted font-mono tabular-nums">
              {t('common.updated', { when: formatRelative(lastUpdated, now) })}
            </p>
          </div>
        </div>
      </section>

      {/* ─── Signature hero chart ─── */}
      <section className="glass-card-emphasis p-4 md:p-6 overflow-hidden">
        <div className="mb-4 flex items-baseline justify-between gap-4 flex-wrap">
          <div>
            <p className="text-[10px] font-mono font-semibold uppercase tracking-[0.14em] text-primary-300">
              {t('dashboard.heroTitle')}
            </p>
            <p className="text-sm text-text-secondary mt-1">
              {t('dashboard.heroSubtitle')}
            </p>
          </div>
          <span
            className="inline-flex items-center gap-1.5 rounded-md border border-border bg-surface-dim
              px-2 py-1 text-[10px] font-mono text-text-muted uppercase tracking-wider"
          >
            <span className="h-1.5 w-1.5 rounded-full bg-primary-400 animate-pulse" />
            {t('dashboard.splitConformal')}
          </span>
        </div>
        <HeroChart />
      </section>

      {/* Coverage alert */}
      {health?.coverage_alert && (
        <div
          className="flex items-start gap-3 rounded-xl border border-amber-500/25 bg-amber-500/[0.04] p-4"
          role="alert"
        >
          <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" aria-hidden="true" />
          <div>
            <p className="text-sm font-medium text-amber-200">{t('dashboard.coverageAlertTitle')}</p>
            <p className="text-xs text-amber-200/70 mt-1">{t('dashboard.coverageAlertBody')}</p>
          </div>
        </div>
      )}

      {/* ─── Bento KPIs ─── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 lg:gap-5 auto-rows-[minmax(150px,auto)]">
        <BentoCard size="sm" className="flex flex-col justify-between">
          <div className="flex items-start justify-between">
            <p className="text-[10px] font-mono font-medium uppercase tracking-[0.12em] text-text-muted">
              {t('dashboard.modelsLoaded')}
            </p>
            <div className="w-8 h-8 rounded-lg bg-primary-500/10 ring-1 ring-primary-400/20 flex items-center justify-center">
              <Layers className="h-4 w-4 text-primary-400" aria-hidden="true" />
            </div>
          </div>
          <div>
            <AnimatedNumber
              value={(typeof health?.total_models === 'number' ? health.total_models : totalModels) || 0}
              format={(n) => Math.round(n).toString()}
              className="font-display text-4xl md:text-5xl font-semibold tracking-tight leading-none text-text-primary"
            />
            <p className="mt-2 text-xs font-mono text-text-muted tracking-wider">no_lags · with_lags</p>
          </div>
        </BentoCard>

        <BentoCard size="sm" className="flex flex-col items-center justify-between" gradient>
          <p className="w-full text-[10px] font-mono font-medium uppercase tracking-[0.12em] text-text-muted">
            {t('dashboard.coverage')}
          </p>
          <div className="flex flex-1 items-center justify-center py-2">
            <PortugalMap ariaLabel={t('dashboard.mapLabel')} />
          </div>
          <div className="w-full text-center">
            <p className="font-display text-3xl font-semibold tracking-tight leading-none text-text-primary">
              <AnimatedNumber value={5} format={(n) => Math.round(n).toString()} />{' '}
              <span className="text-sm font-normal text-text-secondary font-sans">{t('dashboard.regions')}</span>
            </p>
          </div>
        </BentoCard>

        <BentoCard size="sm" className="flex flex-col justify-between">
          <div className="flex items-start justify-between">
            <p className="text-[10px] font-mono font-medium uppercase tracking-[0.12em] text-text-muted">
              {t('dashboard.samples')}
            </p>
            <div className="w-8 h-8 rounded-lg bg-amber-500/10 ring-1 ring-amber-400/20 flex items-center justify-center">
              <Database className="h-4 w-4 text-accent-400" aria-hidden="true" />
            </div>
          </div>
          <div>
            <p className="font-display text-4xl md:text-5xl font-semibold tracking-tight leading-none text-text-primary tabular-nums">
              {formatNumber(40075, 0)}
            </p>
            <p className="mt-2 text-xs font-mono text-text-muted tracking-wider">e-Redes · Open-Meteo</p>
          </div>
        </BentoCard>
      </div>

      {/* ─── Operational state ─── */}
      <section className="space-y-4">
        <div className="flex items-center gap-3">
          <p className="text-[10px] font-mono font-semibold uppercase tracking-[0.14em] text-text-muted">
            {t('dashboard.operationalState')}
          </p>
          <div className="flex-1 hairline" aria-hidden="true" />
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 stagger-children">
          <Card title={t('dashboard.modelsState')} subtitle={t('dashboard.modelsStateSubtitle')}>
            <div className="mb-4 flex items-center justify-between text-[11px] font-mono text-text-muted uppercase tracking-wider">
              <span>
                {t('dashboard.uptime')}:{' '}
                <span className="text-text-primary">{uptime}</span>
              </span>
              <span>v{health?.version || '?'}</span>
            </div>
            <div className="space-y-1">
              {health?.models_loaded &&
                Object.entries(health.models_loaded).map(([name, loaded]) => (
                  <div
                    key={name}
                    className="flex items-center justify-between py-3 px-3 rounded-lg
                      hover:bg-white/[0.03] transition-colors border-b border-border-subtle last:border-0"
                  >
                    <div className="flex items-center gap-2.5">
                      <Cpu className="w-4 h-4 text-text-muted" aria-hidden="true" />
                      <span className="text-sm font-mono font-medium text-text-primary">{name}</span>
                    </div>
                    <span
                      className={`inline-flex items-center gap-1.5 text-[11px] font-mono font-medium px-2.5 py-1 rounded-full uppercase tracking-wider
                        ${loaded
                          ? 'bg-emerald-500/10 text-energy-green ring-1 ring-emerald-400/20'
                          : 'bg-rose-500/10 text-energy-red ring-1 ring-rose-400/20'
                        }`}
                    >
                      {loaded ? (
                        <><CheckCircle className="w-3 h-3" aria-hidden="true" /> {t('dashboard.modelLoaded')}</>
                      ) : (
                        <><AlertTriangle className="w-3 h-3" aria-hidden="true" /> {t('dashboard.modelMissing')}</>
                      )}
                    </span>
                  </div>
                ))}
            </div>
          </Card>

          <Card title={t('dashboard.modelInfo')} subtitle={t('dashboard.modelInfoSubtitle')}>
            {modelInfo ? (
              <div className="space-y-0.5 font-mono text-xs">
                {Object.entries(modelInfo).slice(0, 12).map(([key, value]) => (
                  <div
                    key={key}
                    className="flex justify-between gap-4 py-2 px-3 rounded-lg
                      hover:bg-white/[0.03] transition-colors border-b border-border-subtle/60 last:border-0"
                  >
                    <span className="text-text-secondary truncate uppercase tracking-wider">{formatKey(key)}</span>
                    <span className="text-text-primary truncate max-w-[220px] tabular-nums">
                      {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <LocalEmptyState icon={<Zap className="w-9 h-9" aria-hidden="true" />} message={t('dashboard.modelInfoEmpty')} hint={t('dashboard.modelInfoHint')} />
            )}
          </Card>
        </div>

        {metrics && (
          <Card title={t('dashboard.opMetrics')} subtitle={t('dashboard.opMetricsSubtitle')}>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3 stagger-children">
              {Object.entries(metrics).map(([key, value]) => (
                <div
                  key={key}
                  className="rounded-lg border border-border-subtle bg-surface-dim p-3.5
                    hover:border-border-strong transition-colors"
                >
                  <p className="text-[10px] font-mono uppercase tracking-[0.12em] text-text-muted truncate">
                    {formatKey(key)}
                  </p>
                  <p className="text-sm font-mono font-semibold text-text-primary mt-1.5 truncate tabular-nums">
                    {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                  </p>
                </div>
              ))}
            </div>
          </Card>
        )}
      </section>
    </div>
  );
}

function LocalEmptyState({ icon, message, hint }: { icon: React.ReactNode; message: string; hint?: string }) {
  return (
    <div className="text-center py-8">
      <div
        className="w-14 h-14 rounded-xl bg-surface-dim ring-1 ring-border
          flex items-center justify-center mx-auto mb-3 text-text-muted"
      >
        {icon}
      </div>
      <p className="text-sm font-medium text-text-secondary">{message}</p>
      {hint && <p className="text-xs text-text-muted mt-1.5 max-w-xs mx-auto">{hint}</p>}
    </div>
  );
}

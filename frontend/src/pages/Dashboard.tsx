import { useEffect, useRef, useState } from 'react';
import { motion } from 'motion/react';
import { useTranslation } from 'react-i18next';
import { api, type HealthResponse } from '../api/client';
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
} from 'lucide-react';

const POLL_INTERVAL_MS = 30_000;

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
          <stop offset="0%" stopColor="var(--color-primary-400, #fbbf24)" />
          <stop offset="100%" stopColor="var(--color-primary-600, #d97706)" />
        </linearGradient>
      </defs>
      <path
        d={PORTUGAL_PATH}
        fill="url(#pt-fill)"
        stroke="#b45309"
        strokeOpacity={0.45}
        strokeWidth={40}
        strokeLinejoin="round"
      />
      {REGIONS.map((r, i) => (
        <g key={r.id}>
          <motion.circle
            cx={r.cx}
            cy={r.cy}
            r={650}
            className="fill-white/70"
            animate={{ scale: [1, 1.9, 1], opacity: [0.55, 0, 0.55] }}
            transition={{ duration: 2, repeat: Infinity, delay: i * 0.3 }}
            style={{ transformOrigin: `${r.cx}px ${r.cy}px` }}
          />
          <circle
            cx={r.cx}
            cy={r.cy}
            r={240}
            className="fill-white stroke-primary-900"
            strokeWidth={80}
          />
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

  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [modelInfo, setModelInfo] = useState<Record<string, unknown> | null>(null);
  const [metrics, setMetrics] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [now, setNow] = useState<Date>(new Date());
  const isInitial = useRef(true);

  const load = async (silent = false) => {
    if (!silent) setLoading(true);
    setError(null);
    try {
      const [h, m, met] = await Promise.allSettled([
        api.health(),
        api.modelInfo(),
        api.metricsSummary(),
      ]);
      if (h.status === 'fulfilled') setHealth(h.value);
      if (m.status === 'fulfilled') setModelInfo(m.value);
      if (met.status === 'fulfilled') setMetrics(met.value);
      if (h.status === 'rejected') {
        setError(h.reason?.message || t('dashboard.connectApiError'));
      } else {
        setLastUpdated(new Date());
        if (!silent && !isInitial.current) toast.success(t('dashboard.dataUpdated'));
      }
    } finally {
      if (!silent) setLoading(false);
      isInitial.current = false;
    }
  };

  useEffect(() => {
    load();
    const poll = setInterval(() => load(true), POLL_INTERVAL_MS);
    const tick = setInterval(() => setNow(new Date()), 1000);
    return () => {
      clearInterval(poll);
      clearInterval(tick);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (loading) {
    return (
      <div className="space-y-6" aria-busy="true">
        <div className="h-28 bg-surface-bright rounded-2xl skeleton-shimmer" />
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 stagger-children">
          {[1, 2, 3, 4].map((i) => <CardSkeleton key={i} lines={2} />)}
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
        <div className="bg-surface border border-border rounded-2xl p-8 sm:p-10 text-center max-w-md shadow-lg">
          <div className="w-16 h-16 rounded-2xl bg-red-50 flex items-center justify-center mx-auto mb-4">
            <AlertTriangle className="w-8 h-8 text-red-500" aria-hidden="true" />
          </div>
          <h1 className="text-xl font-bold text-text-primary">{t('dashboard.apiUnavailable')}</h1>
          <p className="text-sm text-text-secondary mt-2">{error}</p>
          <p className="text-xs text-text-muted mt-3">
            {t('dashboard.ensureApiRunning')}{' '}
            <code className="bg-surface-bright px-2 py-0.5 rounded-md text-xs font-mono text-primary-600">localhost:8000</code>
          </p>
          <button
            type="button"
            onClick={() => load()}
            className="mt-6 inline-flex items-center gap-2 text-sm font-medium bg-primary-600 hover:bg-primary-700
              text-white px-5 min-h-[44px] rounded-lg transition-colors shadow-sm cursor-pointer
              focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2
              active:scale-[0.98]"
          >
            <RefreshCw className="w-4 h-4" aria-hidden="true" />
            {t('common.retry')}
          </button>
          <div className="flex justify-center gap-4 mt-3">
            <a href="/predict" className="text-xs text-text-muted hover:text-primary-600 underline transition-colors">{t('dashboard.goToPredict')}</a>
            <a href="/monitoring" className="text-xs text-text-muted hover:text-primary-600 underline transition-colors">{t('dashboard.seeMonitoring')}</a>
          </div>
        </div>
      </div>
    );
  }

  const uptime = health?.uptime_seconds ? formatUptime(health.uptime_seconds) : '—';
  const modelsLoadedMap = health?.models_loaded ?? {};
  const totalModels = Object.keys(modelsLoadedMap).length;

  const isHealthy = health?.status === 'healthy';
  const statusDot = isHealthy
    ? 'bg-green-500'
    : health?.status
      ? 'bg-amber-500'
      : 'bg-red-500';
  const statusLabel = isHealthy
    ? t('dashboard.statusHealthy')
    : health?.status
      ? t('dashboard.statusDegraded')
      : t('dashboard.statusDown');

  return (
    <div className="space-y-8">
      {/* Compact hero */}
      <section className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
        <div className="min-w-0">
          <h1 className="text-3xl md:text-4xl font-bold tracking-tight text-text-primary leading-tight">
            {t('dashboard.title')}
          </h1>
          <p className="mt-2 text-sm md:text-base text-text-secondary max-w-2xl">
            {t('dashboard.subtitle')}
          </p>
          <div className="mt-3 flex items-center gap-3">
            <span className="relative flex items-center justify-center">
              <span className={`absolute inline-flex h-3 w-3 rounded-full ${statusDot} opacity-75 animate-pulse-glow`} />
              <span className={`relative inline-flex h-2.5 w-2.5 rounded-full ${statusDot}`} />
            </span>
            <span className="text-sm font-medium text-text-primary">{statusLabel}</span>
            <span className="inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider
              px-2 py-0.5 rounded-full bg-primary-100 text-primary-700
              dark:bg-primary-900/40 dark:text-primary-300">
              <span className="w-1.5 h-1.5 rounded-full bg-primary-500 animate-pulse" />
              {t('common.live')}
            </span>
          </div>
        </div>

        <div className="flex flex-col items-start md:items-end gap-2 shrink-0">
          <button
            type="button"
            onClick={() => load()}
            className="min-w-[44px] min-h-[44px] inline-flex items-center justify-center gap-2 text-sm font-medium
              text-text-secondary hover:text-text-primary bg-transparent hover:bg-surface-bright
              border border-border hover:border-primary-300 dark:hover:border-primary-700
              rounded-lg px-4 cursor-pointer transition-colors
              focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
            aria-label={t('dashboard.updateData')}
          >
            <RefreshCw className="w-4 h-4" aria-hidden="true" />
            <span className="hidden sm:inline">{t('common.refresh')}</span>
          </button>
          <p className="text-xs text-text-muted tabular-nums">
            {t('common.updated', { when: formatRelative(lastUpdated, now) })}
          </p>
        </div>
      </section>

      {/* Hero live forecast chart — the signature moment */}
      <section
        className="relative overflow-hidden rounded-2xl border border-border
          bg-gradient-to-br from-primary-50/40 via-surface to-surface
          dark:from-primary-950/30 dark:via-surface dark:to-surface p-4 md:p-6"
      >
        <div className="mb-3 flex items-baseline justify-between gap-4">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-wider text-primary-600 dark:text-primary-400">
              {t('dashboard.heroTitle')}
            </p>
            <p className="text-sm text-text-secondary">
              {t('dashboard.heroSubtitle')}
            </p>
          </div>
          <span className="hidden sm:inline-flex items-center gap-1.5 text-[11px] text-text-muted">
            <span className="h-2 w-2 rounded-full bg-primary-500 animate-pulse" />
            {t('dashboard.splitConformal')}
          </span>
        </div>
        <HeroChart />
      </section>


      {/* Coverage alert */}
      {health?.coverage_alert && (
        <div className="flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 dark:bg-amber-900/20 dark:border-amber-800/50 p-4">
          <AlertTriangle className="w-5 h-5 text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" aria-hidden="true" />
          <div>
            <p className="text-sm font-medium text-amber-900 dark:text-amber-200">{t('dashboard.coverageAlertTitle')}</p>
            <p className="text-xs text-amber-800 dark:text-amber-300/80 mt-1">
              {t('dashboard.coverageAlertBody')}
            </p>
          </div>
        </div>
      )}

      {/* Bento grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 lg:gap-6 auto-rows-[minmax(140px,auto)]">
        {/* Models active (live) */}
        <BentoCard size="sm" className="flex flex-col justify-between">
          <div className="flex items-start justify-between">
            <p className="text-xs font-medium uppercase tracking-wide text-text-secondary">
              {t('dashboard.modelsLoaded')}
            </p>
            <Layers className="h-4 w-4 text-primary-500" aria-hidden="true" />
          </div>
          <div>
            <div className="flex items-baseline gap-2">
              <AnimatedNumber
                value={(typeof health?.total_models === 'number' ? health.total_models : totalModels) || 0}
                format={(n) => Math.round(n).toString()}
                className="text-3xl font-bold md:text-4xl"
              />
            </div>
            <p className="mt-1 text-xs text-text-secondary">no_lags · with_lags</p>
          </div>
        </BentoCard>

        {/* Portugal map */}
        <BentoCard size="md" className="flex flex-col items-center justify-between">
          <p className="w-full text-xs font-medium uppercase tracking-wide text-text-secondary">
            {t('dashboard.coverage')}
          </p>
          <div className="flex flex-1 items-center justify-center py-4">
            <PortugalMap ariaLabel={t('dashboard.mapLabel')} />
          </div>
          <div className="w-full text-center">
            <p className="text-2xl font-bold">
              <AnimatedNumber value={5} format={(n) => Math.round(n).toString()} />{' '}
              <span className="text-sm font-medium text-text-secondary">{t('dashboard.regions')}</span>
            </p>
          </div>
        </BentoCard>

        {/* 6. Samples */}
        <BentoCard size="sm" className="flex flex-col justify-between">
          <div className="flex items-start justify-between">
            <p className="text-xs font-medium uppercase tracking-wide text-text-secondary">
              {t('dashboard.samples')}
            </p>
            <Database className="h-4 w-4 text-primary-500" aria-hidden="true" />
          </div>
          <div>
            <p className="text-3xl font-bold md:text-4xl tabular-nums">
              {formatNumber(40075, 0)}
            </p>
            <p className="mt-1 text-xs text-text-secondary">e-Redes + Open-Meteo</p>
          </div>
        </BentoCard>
      </div>

      {/* Live operational section */}
      <section className="space-y-4">
        <p className="text-xs font-medium uppercase tracking-[0.15em] text-text-secondary">
          {t('dashboard.operationalState')}
        </p>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 stagger-children">
          <Card title={t('dashboard.modelsState')} subtitle={t('dashboard.modelsStateSubtitle')}>
            <div className="mb-3 flex items-center justify-between text-xs text-text-muted">
              <span>{t('dashboard.uptime')}: <span className="font-mono text-text-primary">{uptime}</span></span>
              <span>v{health?.version || '?'}</span>
            </div>
            <div className="space-y-1">
              {health?.models_loaded &&
                Object.entries(health.models_loaded).map(([name, loaded]) => (
                  <div
                    key={name}
                    className="flex items-center justify-between py-3 px-2 rounded-lg hover:bg-surface-dim transition-colors border-b border-border/50 last:border-0"
                  >
                    <div className="flex items-center gap-2.5">
                      <Cpu className="w-4 h-4 text-text-muted" aria-hidden="true" />
                      <span className="text-sm font-medium text-text-primary">{name}</span>
                    </div>
                    <span
                      className={`inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full ${
                        loaded
                          ? 'bg-primary-50 text-primary-700 dark:bg-primary-900/30 dark:text-primary-300'
                          : 'bg-red-50 text-red-700'
                      }`}
                    >
                      {loaded ? (
                        <><CheckCircle className="w-3.5 h-3.5" aria-hidden="true" /> {t('dashboard.modelLoaded')}</>
                      ) : (
                        <><AlertTriangle className="w-3.5 h-3.5" aria-hidden="true" /> {t('dashboard.modelMissing')}</>
                      )}
                    </span>
                  </div>
                ))}
            </div>
          </Card>

          <Card title={t('dashboard.modelInfo')} subtitle={t('dashboard.modelInfoSubtitle')}>
            {modelInfo ? (
              <div className="space-y-0.5">
                {Object.entries(modelInfo).slice(0, 12).map(([key, value]) => (
                  <div key={key} className="flex justify-between py-2 px-2 rounded-lg hover:bg-surface-dim transition-colors border-b border-border/30 last:border-0 gap-4">
                    <span className="text-sm text-text-secondary truncate">{formatKey(key)}</span>
                    <span className="text-text-primary font-mono text-xs truncate max-w-[200px] tabular-nums font-medium">
                      {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <LocalEmptyState icon={<Zap className="w-10 h-10" />} message={t('dashboard.modelInfoEmpty')} hint={t('dashboard.modelInfoHint')} />
            )}
          </Card>
        </div>

        {metrics && (
          <Card title={t('dashboard.opMetrics')} subtitle={t('dashboard.opMetricsSubtitle')}>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3 stagger-children">
              {Object.entries(metrics).map(([key, value]) => (
                <div key={key} className="p-3.5 bg-surface-dim rounded-lg hover:bg-surface-bright transition-colors">
                  <p className="text-xs text-text-muted truncate">{formatKey(key)}</p>
                  <p className="text-sm font-semibold text-text-primary mt-1 truncate tabular-nums">
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
      <div className="w-14 h-14 rounded-2xl bg-surface-dim flex items-center justify-center mx-auto mb-3 text-text-muted">
        {icon}
      </div>
      <p className="text-sm font-medium text-text-secondary">{message}</p>
      {hint && <p className="text-xs text-text-muted mt-1.5 max-w-xs mx-auto">{hint}</p>}
    </div>
  );
}

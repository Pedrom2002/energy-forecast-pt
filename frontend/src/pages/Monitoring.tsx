import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { api } from '../api/client';
import { formatLocale } from '../i18n';
import { Card, CardSkeleton } from '../components/Card';
import { toast } from '../components/Toast';
import { formatKey, formatNumber, formatPercent } from '../utils/format';
import { useDocumentTitle } from '../hooks/useDocumentTitle';
import { AnimatedNumber } from '../components/motion/AnimatedNumber';
import { BentoCard } from '../components/motion/BentoCard';
import { FadeInView } from '../components/motion/FadeInView';
import {
  Activity,
  AlertTriangle,
  CheckCircle,
  RefreshCw,
  Shield,
  Info,
  XCircle,
  Zap,
  ChevronDown,
  Sparkles,
} from 'lucide-react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts';

// ----- Helpers ---------------------------------------------------------------

type AnyRecord = Record<string, unknown>;

function isFiniteNumber(v: unknown): v is number {
  return typeof v === 'number' && Number.isFinite(v);
}

function getNumber(obj: AnyRecord | null, ...keys: string[]): number | null {
  if (!obj) return null;
  for (const k of keys) {
    const v = obj[k];
    if (isFiniteNumber(v)) return v;
  }
  return null;
}

interface FeatureStats {
  mean: number;
  std: number;
  min?: number;
  max?: number;
  p1?: number;
  p99?: number;
  [k: string]: number | undefined;
}

/** Defensive extraction of feature stats. Accepts
 *   - { feature_stats: { f: { mean, std, ... } } }
 *   - { f: { mean, std, ... } }  (flat)
 *   - skips non-object / non-stat entries.
 */
function extractFeatureStats(drift: AnyRecord | null): Record<string, FeatureStats> {
  if (!drift) return {};
  const source =
    (drift.feature_stats && typeof drift.feature_stats === 'object'
      ? (drift.feature_stats as AnyRecord)
      : drift);
  const out: Record<string, FeatureStats> = {};
  for (const [k, v] of Object.entries(source)) {
    if (!v || typeof v !== 'object' || Array.isArray(v)) continue;
    const rec = v as AnyRecord;
    if (isFiniteNumber(rec.mean) && isFiniteNumber(rec.std)) {
      const stats: FeatureStats = { mean: rec.mean, std: rec.std };
      for (const s of ['min', 'max', 'p1', 'p99', 'p50', 'median'] as const) {
        if (isFiniteNumber(rec[s])) stats[s] = rec[s] as number;
      }
      out[k] = stats;
    }
  }
  return out;
}

function featureRange(s: FeatureStats): number {
  if (isFiniteNumber(s.p99) && isFiniteNumber(s.p1)) return s.p99 - s.p1;
  if (isFiniteNumber(s.max) && isFiniteNumber(s.min)) return s.max - s.min;
  return Math.abs(s.std);
}

// ----- Component -------------------------------------------------------------

interface DriftCheckEntry {
  z?: number;
  z_score?: number;
  zscore?: number;
  value?: number;
  mean?: number;
  std?: number;
  [k: string]: unknown;
}

export default function Monitoring() {
  const { t } = useTranslation();
  useDocumentTitle(t('monitoring.title'));
  const [coverage, setCoverage] = useState<AnyRecord | null>(null);
  const [drift, setDrift] = useState<AnyRecord | null>(null);
  const [metrics, setMetrics] = useState<AnyRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [expandedFeature, setExpandedFeature] = useState<string | null>(null);

  // Simulator state
  const [simLoading, setSimLoading] = useState(false);
  const [simResult, setSimResult] = useState<AnyRecord | null>(null);
  const [simError, setSimError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [cov, dr, met] = await Promise.allSettled([
        api.modelCoverage(),
        api.modelDrift(),
        api.metricsSummary(),
      ]);
      if (cov.status === 'fulfilled') setCoverage(cov.value as AnyRecord);
      if (dr.status === 'fulfilled') setDrift(dr.value as AnyRecord);
      if (met.status === 'fulfilled') setMetrics(met.value as AnyRecord);
      if (cov.status === 'rejected' && dr.status === 'rejected') {
        setError(t('monitoring.errorLoad'));
      } else {
        setLastUpdated(new Date());
        toast.success(t('monitoring.toastUpdated'));
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Derived values
  const featureStats = useMemo(() => extractFeatureStats(drift), [drift]);
  const featureList = useMemo(() => Object.entries(featureStats), [featureStats]);

  const topFeatures = useMemo(() => {
    return [...featureList]
      .sort((a, b) => featureRange(b[1]) - featureRange(a[1]))
      .slice(0, 12)
      .map(([name, s]) => ({ name, range: featureRange(s), std: s.std }));
  }, [featureList]);

  const empiricalRaw = getNumber(coverage, 'empirical_coverage', 'coverage', 'empirical');
  const nominalRaw =
    getNumber(coverage, 'nominal_coverage', 'target_coverage', 'nominal') ?? 0.9;
  // Normalise: API may give 0..1 or 0..100.
  const empirical = empiricalRaw != null ? (empiricalRaw > 1 ? empiricalRaw / 100 : empiricalRaw) : null;
  const nominal = nominalRaw > 1 ? nominalRaw / 100 : nominalRaw;

  const nObs = getNumber(coverage, 'n_observations', 'n', 'observations', 'count') ?? 0;
  const windowSize = getNumber(coverage, 'window_size', 'window') ?? 168;
  const alertThresholdRaw = getNumber(coverage, 'alert_threshold');
  const alertThreshold =
    alertThresholdRaw != null ? (alertThresholdRaw > 1 ? alertThresholdRaw / 100 : alertThresholdRaw) : 0.8;

  const empiricalPct = empirical != null ? empirical * 100 : null;
  const nominalPct = nominal * 100;
  const alertPct = alertThreshold * 100;
  const deviation = empirical != null ? empirical - nominal : null;

  const coverageStatus: 'ok' | 'warn' | 'bad' | 'none' =
    empiricalPct == null
      ? 'none'
      : empiricalPct >= nominalPct
        ? 'ok'
        : empiricalPct >= alertPct
          ? 'warn'
          : 'bad';

  const driftAlert = coverage?.alert === true || coverageStatus === 'bad';

  const lastUpdatedLabel = lastUpdated
    ? lastUpdated.toLocaleTimeString(formatLocale(), { hour: '2-digit', minute: '2-digit', second: '2-digit' })
    : '—';

  // Filter truly-useful metrics (numeric scalars only)
  const usefulMetrics = useMemo(() => {
    if (!metrics) return [] as [string, number | string][];
    const out: [string, number | string][] = [];
    for (const [k, v] of Object.entries(metrics)) {
      if (isFiniteNumber(v)) out.push([k, v]);
      else if (typeof v === 'string' && v.length < 40) out.push([k, v]);
    }
    return out.slice(0, 4);
  }, [metrics]);

  // Drift simulator
  const runSimulation = async () => {
    const entries = Object.entries(featureStats);
    if (entries.length === 0) return;
    // Pick up to 20 features; perturb within ±1.5 sigma mostly, some features ±3 sigma
    const features: Record<string, number> = {};
    entries.slice(0, 20).forEach(([name, s], i) => {
      const magnitude = i % 7 === 0 ? 3 : Math.random() * 1.5;
      const sign = Math.random() < 0.5 ? -1 : 1;
      features[name] = s.mean + sign * magnitude * Math.abs(s.std || 1);
    });
    setSimLoading(true);
    setSimError(null);
    setSimResult(null);
    try {
      const res = await api.driftCheck(features);
      setSimResult(res as AnyRecord);
    } catch (err) {
      setSimError(err instanceof Error ? err.message : t('monitoring.simError'));
    } finally {
      setSimLoading(false);
    }
  };

  // Parse sim response defensively into [name, z][]
  const simEntries: [string, number][] = useMemo(() => {
    if (!simResult) return [];
    const src =
      (simResult.feature_checks && typeof simResult.feature_checks === 'object'
        ? (simResult.feature_checks as AnyRecord)
        : simResult.z_scores && typeof simResult.z_scores === 'object'
          ? (simResult.z_scores as AnyRecord)
          : simResult);
    const out: [string, number][] = [];
    for (const [k, v] of Object.entries(src)) {
      if (isFiniteNumber(v)) {
        out.push([k, v]);
      } else if (v && typeof v === 'object') {
        const rec = v as DriftCheckEntry;
        const z = rec.z ?? rec.z_score ?? rec.zscore;
        if (isFiniteNumber(z)) out.push([k, z]);
      }
    }
    return out.sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]));
  }, [simResult]);

  // ---- Rendering ----

  if (loading) {
    return (
      <div className="space-y-6" aria-busy="true">
        <div className="h-20 bg-surface-bright rounded-2xl skeleton-shimmer" />
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 stagger-children">
          {[1, 2, 3].map((i) => <CardSkeleton key={i} lines={2} />)}
        </div>
        <CardSkeleton lines={5} />
        <CardSkeleton lines={6} />
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Hero */}
      <section className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
        <div className="min-w-0">
          <h1 className="text-3xl md:text-4xl font-bold tracking-tight text-text-primary leading-tight">
            {t('monitoring.title')}
          </h1>
          <p className="mt-2 text-sm md:text-base text-text-secondary max-w-2xl">
            {t('monitoring.subtitle')}
          </p>
        </div>
        <div className="flex flex-col items-start md:items-end gap-2 shrink-0">
          <button
            type="button"
            onClick={load}
            className="min-w-[44px] min-h-[44px] inline-flex items-center justify-center gap-2 text-sm font-medium
              text-text-secondary hover:text-text-primary bg-transparent hover:bg-surface-bright
              border border-border hover:border-primary-300 dark:hover:border-primary-700
              rounded-lg px-4 cursor-pointer transition-colors
              focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
            aria-label={t('monitoring.refreshAria')}
          >
            <RefreshCw className="w-4 h-4" aria-hidden="true" />
            <span className="hidden sm:inline">{t('common.refresh')}</span>
          </button>
          <p className="text-xs text-text-muted tabular-nums">
            {t('monitoring.lastCheck', { when: lastUpdatedLabel })}
          </p>
        </div>
      </section>

      {error && (
        <div
          className="flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 dark:bg-amber-900/20 dark:border-amber-800/50 p-4 animate-fade-in-up"
          role="alert"
        >
          <AlertTriangle className="w-5 h-5 text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" aria-hidden="true" />
          <div className="flex-1">
            <p className="text-sm font-medium text-amber-900 dark:text-amber-200">{t('monitoring.limitedData')}</p>
            <p className="text-xs text-amber-800 dark:text-amber-300/80 mt-1">{error}</p>
            <p className="text-xs text-amber-800/80 dark:text-amber-300/70 mt-2">
              {t('monitoring.apiHint')}{' '}
              <code className="bg-amber-100/60 dark:bg-amber-900/40 px-1.5 py-0.5 rounded text-[11px] font-mono">
                localhost:8000
              </code>
              {' '}{t('monitoring.andModel')}
            </p>
          </div>
        </div>
      )}

      {/* KPI strip */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 lg:gap-6 stagger-children">
        <BentoCard size="sm" className="flex flex-col justify-between">
          <div className="flex items-start justify-between">
            <p className="text-xs font-medium uppercase tracking-wide text-text-secondary">
              {t('monitoring.empiricalCoverage')}
            </p>
            {coverageStatus === 'ok' && <CheckCircle className="w-4 h-4 text-energy-green" aria-hidden="true" />}
            {coverageStatus === 'warn' && <AlertTriangle className="w-4 h-4 text-energy-yellow" aria-hidden="true" />}
            {coverageStatus === 'bad' && <XCircle className="w-4 h-4 text-energy-red" aria-hidden="true" />}
            {coverageStatus === 'none' && <Shield className="w-4 h-4 text-text-muted" aria-hidden="true" />}
          </div>
          <div>
            <div className="flex items-baseline gap-2">
              {empiricalPct != null ? (
                <AnimatedNumber
                  value={empiricalPct}
                  format={(n) => `${n.toFixed(1)}%`}
                  className={`text-3xl font-bold md:text-4xl tabular-nums ${
                    coverageStatus === 'ok'
                      ? 'text-energy-green'
                      : coverageStatus === 'warn'
                        ? 'text-energy-yellow'
                        : coverageStatus === 'bad'
                          ? 'text-energy-red'
                          : 'text-text-primary'
                  }`}
                />
              ) : (
                <span className="text-3xl font-bold md:text-4xl text-text-muted">—</span>
              )}
            </div>
            <p className="mt-1 text-xs text-text-secondary">
              {t('monitoring.target', { value: formatPercent(nominalPct, 0) })} · {t('monitoring.window', { hours: Math.round(windowSize) })}
            </p>
          </div>
        </BentoCard>

        <BentoCard size="sm" className="flex flex-col justify-between">
          <div className="flex items-start justify-between">
            <p className="text-xs font-medium uppercase tracking-wide text-text-secondary">
              {t('monitoring.observations')}
            </p>
            <Activity className="w-4 h-4 text-primary-500" aria-hidden="true" />
          </div>
          <div>
            <AnimatedNumber
              value={nObs}
              format={(n) => formatNumber(Math.round(n), 0)}
              className="text-3xl font-bold md:text-4xl tabular-nums"
            />
            <p className="mt-1 text-xs text-text-secondary">{t('monitoring.observationsSubtitle')}</p>
          </div>
        </BentoCard>

        <BentoCard size="sm" className="flex flex-col justify-between">
          <div className="flex items-start justify-between">
            <p className="text-xs font-medium uppercase tracking-wide text-text-secondary">
              {t('monitoring.driftState')}
            </p>
            <Sparkles className="w-4 h-4 text-primary-500" aria-hidden="true" />
          </div>
          <div>
            <span
              className={`inline-flex items-center gap-1.5 text-sm font-semibold px-3 py-1.5 rounded-full ${
                driftAlert
                  ? 'bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-300'
                  : 'bg-primary-50 text-primary-700 dark:bg-primary-900/30 dark:text-primary-300'
              }`}
            >
              <span className={`w-2 h-2 rounded-full ${driftAlert ? 'bg-red-500' : 'bg-green-500'} animate-pulse`} />
              {driftAlert ? t('monitoring.driftDetected') : t('monitoring.stable')}
            </span>
            <p className="mt-2 text-xs text-text-secondary">
              {t('monitoring.lastCheck', { when: lastUpdatedLabel })}
            </p>
          </div>
        </BentoCard>
      </div>

      {/* Coverage section */}
      <FadeInView delay={0.05}>
        <Card
          title={t('monitoring.coverageTitle')}
          subtitle={t('monitoring.coverageSubtitle', { hours: Math.round(windowSize) })}
        >
          {empiricalPct != null ? (
            <div className="space-y-5">
              <div className="flex items-start gap-2 px-3 py-2.5 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800/50 rounded-lg text-xs text-amber-800 dark:text-amber-300 leading-relaxed">
                <Info className="w-4 h-4 shrink-0 mt-0.5" aria-hidden="true" />
                <p>
                  <strong>{t('monitoring.demoLabel')}</strong>{' '}
                  {t('monitoring.demoCoverageBody', { endpoint: 'POST /model/coverage/record' })}
                </p>
              </div>
              <p className="text-xs text-text-secondary leading-relaxed">
                {t('monitoring.coverageExplain', { nominal: formatPercent(nominalPct, 0), alert: formatPercent(alertPct, 0) })}
              </p>

              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-text-primary">{t('monitoring.empiricalCoverageLine')}</span>
                  <span
                    className={`flex items-center gap-1.5 text-base font-semibold tabular-nums ${
                      coverageStatus === 'ok'
                        ? 'text-energy-green'
                        : coverageStatus === 'warn'
                          ? 'text-energy-yellow'
                          : 'text-energy-red'
                    }`}
                  >
                    {coverageStatus === 'ok' ? (
                      <CheckCircle className="w-4 h-4" aria-hidden="true" />
                    ) : coverageStatus === 'warn' ? (
                      <AlertTriangle className="w-4 h-4" aria-hidden="true" />
                    ) : (
                      <XCircle className="w-4 h-4" aria-hidden="true" />
                    )}
                    {empiricalPct.toFixed(1)}%
                  </span>
                </div>

                <div
                  className="relative h-5 bg-surface-bright rounded-full overflow-hidden"
                  role="progressbar"
                  aria-valuenow={+empiricalPct.toFixed(1)}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-label={t('monitoring.coverageAria', { value: empiricalPct.toFixed(1) })}
                >
                  <div
                    className={`h-full rounded-full transition-all duration-700 ease-out ${
                      coverageStatus === 'ok'
                        ? 'bg-energy-green'
                        : coverageStatus === 'warn'
                          ? 'bg-energy-yellow'
                          : 'bg-energy-red'
                    }`}
                    style={{ width: `${Math.min(100, empiricalPct)}%` }}
                  />
                  {/* Alert threshold marker */}
                  <div
                    className="absolute top-0 bottom-0 w-[2px] bg-energy-yellow/80"
                    style={{ left: `${alertPct}%` }}
                    aria-hidden="true"
                  />
                  {/* Nominal target marker */}
                  <div
                    className="absolute top-0 bottom-0 w-[2px] bg-energy-green"
                    style={{ left: `${nominalPct}%` }}
                    aria-hidden="true"
                  />
                </div>

                <div className="flex justify-between text-[11px] text-text-muted tabular-nums">
                  <span>0%</span>
                  <span className="text-energy-yellow font-medium">{t('monitoring.alertLabel', { value: alertPct.toFixed(0) })}</span>
                  <span className="text-energy-green font-medium">{t('monitoring.targetLabel', { value: nominalPct.toFixed(0) })}</span>
                  <span>100%</span>
                </div>
              </div>

              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 pt-2">
                <NumStat label={t('monitoring.statTarget')} value={formatPercent(nominalPct, 1)} />
                <NumStat label={t('monitoring.statActual')} value={formatPercent(empiricalPct, 1)} />
                <NumStat
                  label={t('monitoring.statDeviation')}
                  value={deviation != null ? `${deviation >= 0 ? '+' : ''}${(deviation * 100).toFixed(2)}pp` : '—'}
                  tone={deviation != null && Math.abs(deviation) > 0.1 ? 'bad' : 'ok'}
                />
                <NumStat label={t('monitoring.statWindow')} value={`${Math.round(windowSize)}h`} />
              </div>
            </div>
          ) : (
            <EmptyState
              icon={<Shield className="w-8 h-8" />}
              title={t('monitoring.noCoverageTitle')}
              hint={t('monitoring.noCoverageHint', { endpoint: 'POST /model/coverage/record' })}
            />
          )}
        </Card>
      </FadeInView>

      {/* Operational metrics (only if useful) */}
      {usefulMetrics.length >= 2 && (
        <FadeInView delay={0.15}>
          <Card title={t('monitoring.opMetricsTitle')} subtitle={t('monitoring.opMetricsSubtitle')}>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 stagger-children">
              {usefulMetrics.map(([key, value]) => (
                <div key={key} className="p-3.5 bg-surface-dim rounded-lg hover:bg-surface-bright transition-colors">
                  <p className="text-xs text-text-muted truncate">{formatKey(key)}</p>
                  <p className="text-base font-semibold text-text-primary mt-1 truncate tabular-nums">
                    {typeof value === 'number' ? formatNumber(value, value < 10 ? 2 : 0) : String(value)}
                  </p>
                </div>
              ))}
            </div>
          </Card>
        </FadeInView>
      )}
    </div>
  );
}

// ----- Small subcomponents ---------------------------------------------------

function NumStat({
  label,
  value,
  tone = 'ok',
}: {
  label: string;
  value: string;
  tone?: 'ok' | 'bad';
}) {
  return (
    <div className="p-3 bg-surface-dim rounded-lg">
      <p className="text-[10px] text-text-muted uppercase tracking-wider">{label}</p>
      <p
        className={`text-sm font-semibold tabular-nums mt-1 ${
          tone === 'bad' ? 'text-energy-red' : 'text-text-primary'
        }`}
      >
        {value}
      </p>
    </div>
  );
}

function EmptyState({
  icon,
  title,
  hint,
}: {
  icon: React.ReactNode;
  title: string;
  hint?: React.ReactNode;
}) {
  return (
    <div className="text-center py-10">
      <div className="w-14 h-14 rounded-2xl bg-surface-dim flex items-center justify-center mx-auto mb-3 text-text-muted">
        {icon}
      </div>
      <p className="text-sm font-medium text-text-secondary">{title}</p>
      {hint && <p className="text-xs text-text-muted mt-1.5 max-w-sm mx-auto">{hint}</p>}
    </div>
  );
}

import { useEffect, useMemo, useState } from 'react';
import { api } from '../api/client';
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
  useDocumentTitle('Monitorização');
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
        setError('Não foi possível obter dados de monitorização. Verifique a ligação à API.');
      } else {
        setLastUpdated(new Date());
        toast.success('Dados de monitorização atualizados');
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
    ? lastUpdated.toLocaleTimeString('pt-PT', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
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
      setSimError(err instanceof Error ? err.message : 'Erro ao executar simulação');
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
            Monitorização
          </h1>
          <p className="mt-2 text-sm md:text-base text-text-secondary max-w-2xl">
            Saúde do modelo em produção · cobertura conformal e drift de features
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
            aria-label="Atualizar dados de monitorização"
          >
            <RefreshCw className="w-4 h-4" aria-hidden="true" />
            <span className="hidden sm:inline">Atualizar</span>
          </button>
          <p className="text-xs text-text-muted tabular-nums">
            última verificação: {lastUpdatedLabel}
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
            <p className="text-sm font-medium text-amber-900 dark:text-amber-200">Dados limitados</p>
            <p className="text-xs text-amber-800 dark:text-amber-300/80 mt-1">{error}</p>
            <p className="text-xs text-amber-800/80 dark:text-amber-300/70 mt-2">
              Verifique se a API está disponível em{' '}
              <code className="bg-amber-100/60 dark:bg-amber-900/40 px-1.5 py-0.5 rounded text-[11px] font-mono">
                localhost:8000
              </code>
              {' '}e se o modelo tem observações registadas.
            </p>
          </div>
        </div>
      )}

      {/* KPI strip */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 lg:gap-6 stagger-children">
        <BentoCard size="sm" className="flex flex-col justify-between">
          <div className="flex items-start justify-between">
            <p className="text-xs font-medium uppercase tracking-wide text-text-secondary">
              Cobertura empírica
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
              alvo {formatPercent(nominalPct, 0)} · janela {Math.round(windowSize)}h
            </p>
          </div>
        </BentoCard>

        <BentoCard size="sm" className="flex flex-col justify-between">
          <div className="flex items-start justify-between">
            <p className="text-xs font-medium uppercase tracking-wide text-text-secondary">
              Observações
            </p>
            <Activity className="w-4 h-4 text-primary-500" aria-hidden="true" />
          </div>
          <div>
            <AnimatedNumber
              value={nObs}
              format={(n) => formatNumber(Math.round(n), 0)}
              className="text-3xl font-bold md:text-4xl tabular-nums"
            />
            <p className="mt-1 text-xs text-text-secondary">registadas na janela</p>
          </div>
        </BentoCard>

        <BentoCard size="sm" className="flex flex-col justify-between">
          <div className="flex items-start justify-between">
            <p className="text-xs font-medium uppercase tracking-wide text-text-secondary">
              Estado de drift
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
              {driftAlert ? 'Drift detectado' : 'Estável'}
            </span>
            <p className="mt-2 text-xs text-text-secondary">
              última verificação: <span className="tabular-nums">{lastUpdatedLabel}</span>
            </p>
          </div>
        </BentoCard>
      </div>

      {/* Coverage section */}
      <FadeInView delay={0.05}>
        <Card
          title="Calibração Conformal · cobertura dos IC 90%"
          subtitle={`Janela deslizante de ${Math.round(windowSize)} observações`}
        >
          {empiricalPct != null ? (
            <div className="space-y-5">
              <div className="flex items-start gap-2 px-3 py-2.5 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800/50 rounded-lg text-xs text-amber-800 dark:text-amber-300 leading-relaxed">
                <Info className="w-4 h-4 shrink-0 mt-0.5" aria-hidden="true" />
                <p>
                  <strong>Demo:</strong> 168 observações sintéticas semeadas no arranque (~92% cobertura) para que esta página tenha sempre dados visíveis.
                  Em produção, esta janela seria preenchida via <code className="font-mono px-1 py-0.5 bg-amber-100/60 dark:bg-amber-900/40 rounded">POST /model/coverage/record</code> à medida que chegam observações reais.
                </p>
              </div>
              <p className="text-xs text-text-secondary leading-relaxed">
                O modelo deve cobrir {formatPercent(nominalPct, 0)} dos casos reais.
                A linha verde marca o alvo, a amarela o limite de alerta ({formatPercent(alertPct, 0)}).
              </p>

              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-text-primary">Cobertura empírica</span>
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
                  aria-label={`Cobertura empírica: ${empiricalPct.toFixed(1)}%`}
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
                  <span className="text-energy-yellow font-medium">{alertPct.toFixed(0)}% alerta</span>
                  <span className="text-energy-green font-medium">{nominalPct.toFixed(0)}% alvo</span>
                  <span>100%</span>
                </div>
              </div>

              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 pt-2">
                <NumStat label="Alvo" value={formatPercent(nominalPct, 1)} />
                <NumStat label="Actual" value={formatPercent(empiricalPct, 1)} />
                <NumStat
                  label="Desvio"
                  value={deviation != null ? `${deviation >= 0 ? '+' : ''}${(deviation * 100).toFixed(2)}pp` : '—'}
                  tone={deviation != null && Math.abs(deviation) > 0.1 ? 'bad' : 'ok'}
                />
                <NumStat label="Janela" value={`${Math.round(windowSize)}h`} />
              </div>
            </div>
          ) : (
            <EmptyState
              icon={<Shield className="w-8 h-8" />}
              title="Sem dados de cobertura"
              hint={
                <>
                  Registe observações via{' '}
                  <code className="bg-surface-bright px-1.5 py-0.5 rounded text-xs font-mono">
                    POST /model/coverage/record
                  </code>{' '}
                  para iniciar o tracking.
                </>
              }
            />
          )}
        </Card>
      </FadeInView>

      {/* Drift section */}
      <FadeInView delay={0.1}>
        <Card
          title="Distribuição de Features · baseline de treino"
          subtitle={`Estatísticas de ${featureList.length} features para detecção de drift`}
        >
          {featureList.length > 0 ? (
            <div className="space-y-5">
              <div className="flex items-start gap-2 p-3 bg-primary-50 dark:bg-primary-900/20 rounded-lg text-xs text-primary-800 dark:text-primary-200">
                <Info className="w-4 h-4 shrink-0 mt-0.5" aria-hidden="true" />
                <p>
                  Envie features para{' '}
                  <code className="bg-primary-100 dark:bg-primary-900/40 px-1 rounded font-mono">
                    POST /model/drift/check
                  </code>{' '}
                  para comparar com este baseline. Z-score |z| ≥ 3 indica drift significativo.
                </p>
              </div>

              {/* Chart */}
              <div className="h-[360px] w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={topFeatures} layout="vertical" margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
                    <CartesianGrid horizontal={false} stroke="var(--color-border, #e5e7eb)" strokeDasharray="3 3" />
                    <XAxis
                      type="number"
                      tick={{ fontSize: 11, fill: 'var(--color-text-secondary)' }}
                      axisLine={{ stroke: 'var(--color-border, #e5e7eb)' }}
                      tickLine={false}
                    />
                    <YAxis
                      type="category"
                      dataKey="name"
                      width={160}
                      tick={{ fontSize: 11, fill: 'var(--color-text-secondary)' }}
                      axisLine={{ stroke: 'var(--color-border, #e5e7eb)' }}
                      tickLine={false}
                    />
                    <Tooltip
                      cursor={{ fill: 'var(--color-surface-bright, #f5f5f4)', opacity: 0.5 }}
                      contentStyle={{
                        background: 'var(--color-surface, #fff)',
                        border: '1px solid var(--color-border, #e5e7eb)',
                        borderRadius: 8,
                        fontSize: 12,
                      }}
                      formatter={(v: number) => [v.toFixed(3), 'Amplitude (p99−p1)']}
                    />
                    <Bar dataKey="range" radius={[0, 6, 6, 0]} onClick={(d: { name?: string }) => d?.name && setExpandedFeature(d.name === expandedFeature ? null : d.name)}>
                      {topFeatures.map((f) => (
                        <Cell
                          key={f.name}
                          fill={expandedFeature === f.name ? 'var(--color-primary-700, #b45309)' : 'var(--color-primary-500, #f59e0b)'}
                          cursor="pointer"
                        />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>

              {/* Expanded feature detail */}
              {expandedFeature && featureStats[expandedFeature] && (
                <div className="p-4 rounded-xl border border-primary-200 dark:border-primary-800 bg-primary-50/50 dark:bg-primary-900/20 animate-fade-in-up">
                  <div className="flex items-center justify-between mb-3">
                    <p className="text-sm font-semibold text-text-primary">{expandedFeature}</p>
                    <button
                      type="button"
                      onClick={() => setExpandedFeature(null)}
                      className="text-xs text-text-muted hover:text-text-primary cursor-pointer"
                    >
                      fechar
                    </button>
                  </div>
                  <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
                    {(['mean', 'std', 'min', 'p1', 'p99', 'max'] as const).map((stat) => {
                      const v = featureStats[expandedFeature][stat];
                      return (
                        <div key={stat} className="text-center p-2 bg-surface rounded-lg">
                          <p className="text-[10px] text-text-muted uppercase tracking-wider">{stat}</p>
                          <p className="text-xs font-mono text-text-primary tabular-nums mt-0.5">
                            {isFiniteNumber(v) ? v.toFixed(3) : '—'}
                          </p>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Feature list — click-to-expand alternate */}
              <div className="space-y-1">
                {topFeatures.map((f) => {
                  const expanded = expandedFeature === f.name;
                  return (
                    <button
                      type="button"
                      key={f.name}
                      onClick={() => setExpandedFeature(expanded ? null : f.name)}
                      className="w-full flex items-center justify-between py-2 px-3 rounded-lg hover:bg-surface-dim transition-colors text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 cursor-pointer"
                    >
                      <span className="text-sm text-text-primary font-medium truncate flex-1">{f.name}</span>
                      <span className="text-xs text-text-muted font-mono tabular-nums mr-3">
                        σ={f.std.toFixed(2)} · Δ={f.range.toFixed(2)}
                      </span>
                      <ChevronDown
                        className={`w-4 h-4 text-text-muted transition-transform ${expanded ? 'rotate-180' : ''}`}
                        aria-hidden="true"
                      />
                    </button>
                  );
                })}
              </div>

              {/* Simulator */}
              <div className="pt-4 border-t border-border/50">
                <div className="flex items-center justify-between gap-3 flex-wrap">
                  <div>
                    <p className="text-sm font-semibold text-text-primary">Simular drift</p>
                    <p className="text-xs text-text-secondary mt-0.5">
                      Gera perturbações sintéticas em torno do baseline e envia para{' '}
                      <code className="font-mono text-[11px]">/model/drift/check</code>.
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={runSimulation}
                    disabled={simLoading}
                    className="min-h-[44px] inline-flex items-center gap-2 text-sm font-medium text-white bg-primary-600 hover:bg-primary-700 disabled:opacity-60 disabled:cursor-not-allowed px-4 rounded-lg cursor-pointer transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
                  >
                    <Zap className={`w-4 h-4 ${simLoading ? 'animate-pulse' : ''}`} aria-hidden="true" />
                    {simLoading ? 'A simular…' : 'Executar simulação'}
                  </button>
                </div>

                {simError && (
                  <p className="mt-3 text-xs text-energy-red">{simError}</p>
                )}

                {simEntries.length > 0 && (
                  <div className="mt-4 grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2">
                    {simEntries.slice(0, 16).map(([name, z]) => {
                      const high = Math.abs(z) >= 3;
                      const mid = Math.abs(z) >= 2;
                      return (
                        <div
                          key={name}
                          className={`p-2.5 rounded-lg border ${
                            high
                              ? 'border-red-300 bg-red-50 dark:bg-red-900/20 dark:border-red-800'
                              : mid
                                ? 'border-amber-300 bg-amber-50 dark:bg-amber-900/20 dark:border-amber-800'
                                : 'border-border bg-surface-dim'
                          }`}
                        >
                          <p className="text-[11px] text-text-secondary truncate">{name}</p>
                          <p
                            className={`text-sm font-mono font-semibold tabular-nums mt-0.5 ${
                              high ? 'text-energy-red' : mid ? 'text-energy-yellow' : 'text-text-primary'
                            }`}
                          >
                            z = {z.toFixed(2)}
                          </p>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
          ) : (
            <EmptyState
              icon={<Activity className="w-8 h-8" />}
              title="Baseline não disponível"
              hint={
                <>
                  O modelo precisa de ter{' '}
                  <code className="bg-surface-bright px-1.5 py-0.5 rounded text-xs font-mono">feature_stats</code>{' '}
                  nos metadados.
                </>
              }
            />
          )}
        </Card>
      </FadeInView>

      {/* Operational metrics (only if useful) */}
      {usefulMetrics.length >= 2 && (
        <FadeInView delay={0.15}>
          <Card title="Métricas operacionais · API" subtitle="Resumo de tráfego e latências">
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

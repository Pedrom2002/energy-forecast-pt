import { useEffect, useRef, useState } from 'react';
import { motion } from 'motion/react';
import { api, type HealthResponse } from '../api/client';
import { Card, CardSkeleton } from '../components/Card';
import { toast } from '../components/Toast';
import { formatKey, formatUptime, formatNumber } from '../utils/format';
import { useDocumentTitle } from '../hooks/useDocumentTitle';
import { AnimatedNumber } from '../components/motion/AnimatedNumber';
import { BentoCard } from '../components/motion/BentoCard';
import { PORTUGAL_PATH } from '../assets/portugalPath';
import { Sparkline } from '../components/Sparkline';
import HeroChart from '../components/HeroChart';
import {
  Activity,
  Cpu,
  AlertTriangle,
  CheckCircle,
  RefreshCw,
  Zap,
  Layers,
  TrendingUp,
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

function PortugalMap() {
  return (
    <svg
      viewBox="0 0 12969 26674"
      className="h-full w-full max-h-[180px]"
      aria-label="Mapa de Portugal continental com 5 regiões"
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

function formatRelative(from: Date | null, now: Date): string {
  if (!from) return '—';
  const diff = Math.max(0, Math.floor((now.getTime() - from.getTime()) / 1000));
  if (diff < 5) return 'agora mesmo';
  if (diff < 60) return `há ${diff}s`;
  if (diff < 3600) return `há ${Math.floor(diff / 60)}m`;
  return `há ${Math.floor(diff / 3600)}h`;
}

export default function Dashboard() {
  useDocumentTitle('Dashboard');

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
        setError(h.reason?.message || 'Erro ao conectar a API');
      } else {
        setLastUpdated(new Date());
        if (!silent && !isInitial.current) toast.success('Dados atualizados');
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
          <h1 className="text-xl font-bold text-text-primary">API Indisponível</h1>
          <p className="text-sm text-text-secondary mt-2">{error}</p>
          <p className="text-xs text-text-muted mt-3">
            Certifique-se que a API esta a correr em{' '}
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
            Tentar novamente
          </button>
          <div className="flex justify-center gap-4 mt-3">
            <a href="/predict" className="text-xs text-text-muted hover:text-primary-600 underline transition-colors">Ir para Previsão</a>
            <a href="/monitoring" className="text-xs text-text-muted hover:text-primary-600 underline transition-colors">Ver Monitoring</a>
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
    ? 'Todos os sistemas operacionais'
    : health?.status
      ? 'Desempenho degradado'
      : 'Sem resposta';

  return (
    <div className="space-y-8">
      {/* Compact hero */}
      <section className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
        <div className="min-w-0">
          <h1 className="text-3xl md:text-4xl font-bold tracking-tight text-text-primary leading-tight">
            Dashboard
          </h1>
          <p className="mt-2 text-sm md:text-base text-text-secondary max-w-2xl">
            Energy Forecast Portugal — MAPE 1.44% · RMSE 22.9 MW · 2.6× baseline
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
              Live
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
            aria-label="Atualizar dados"
          >
            <RefreshCw className="w-4 h-4" aria-hidden="true" />
            <span className="hidden sm:inline">Atualizar</span>
          </button>
          <p className="text-xs text-text-muted tabular-nums">
            actualizado {formatRelative(lastUpdated, now)}
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
              Previsão em tempo real · Lisboa
            </p>
            <p className="text-sm text-text-secondary">
              Próximas 24 horas · intervalo de confiança a 90%
            </p>
          </div>
          <span className="hidden sm:inline-flex items-center gap-1.5 text-[11px] text-text-muted">
            <span className="h-2 w-2 rounded-full bg-primary-500 animate-pulse" />
            split conformal
          </span>
        </div>
        <HeroChart />
      </section>

      {/* Coverage alert */}
      {health?.coverage_alert && (
        <div className="flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 dark:bg-amber-900/20 dark:border-amber-800/50 p-4">
          <AlertTriangle className="w-5 h-5 text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" aria-hidden="true" />
          <div>
            <p className="text-sm font-medium text-amber-900 dark:text-amber-200">Alerta de cobertura do IC 90%</p>
            <p className="text-xs text-amber-800 dark:text-amber-300/80 mt-1">
              A cobertura empírica afastou-se do valor nominal. Verifique a calibração conformal.
            </p>
          </div>
        </div>
      )}

      {/* Bento grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 lg:gap-6 auto-rows-[minmax(140px,auto)]">
        {/* 1. MAPE big */}
        <BentoCard size="xl" gradient className="flex flex-col justify-between">
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-text-secondary">
              Precisão
            </p>
            <h3 className="mt-2 text-lg font-semibold">MAPE</h3>
          </div>
          <div className="flex items-baseline gap-2">
            <AnimatedNumber
              value={1.44}
              format={(n) => n.toFixed(2)}
              className="text-6xl font-bold text-primary-500 md:text-8xl"
            />
            <span className="text-3xl font-bold text-primary-500 md:text-5xl">%</span>
          </div>
          <div>
            <Sparkline data={[1.38, 1.52, 1.41, 1.47, 1.42]} height={40} color="primary" filled />
            <p className="mt-1 mb-3 text-xs text-text-muted">CV 5-fold</p>
            <p className="mb-3 text-sm text-text-secondary">
              Mean Absolute Percentage Error
            </p>
            <span className="inline-flex items-center rounded-full bg-primary-100 px-3 py-1 text-xs font-semibold text-primary-700 dark:bg-primary-900/40 dark:text-primary-300">
              2.6× melhor que persistência
            </span>
          </div>
        </BentoCard>

        {/* 2. RMSE */}
        <BentoCard size="sm" className="flex flex-col justify-between">
          <div className="flex items-start justify-between">
            <p className="text-xs font-medium uppercase tracking-wide text-text-secondary">
              RMSE
            </p>
            <Activity className="h-4 w-4 text-primary-500" aria-hidden="true" />
          </div>
          <div>
            <div className="flex items-baseline gap-1">
              <AnimatedNumber
                value={22.9}
                format={(n) => n.toFixed(1)}
                className="text-3xl font-bold md:text-4xl"
              />
              <span className="text-lg font-semibold text-text-secondary">MW</span>
            </div>
            <Sparkline data={[24.1, 22.8, 23.5, 22.1, 22.9]} height={28} color="primary" filled className="mt-1" />
          </div>
        </BentoCard>

        {/* 3. Models active (live) */}
        <BentoCard size="sm" className="flex flex-col justify-between">
          <div className="flex items-start justify-between">
            <p className="text-xs font-medium uppercase tracking-wide text-text-secondary">
              Modelos
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
            <p className="mt-1 text-xs text-text-secondary">de 2 ativos</p>
          </div>
        </BentoCard>

        {/* 4. R² */}
        <BentoCard size="lg" className="flex flex-col justify-between">
          <div className="flex items-start justify-between">
            <p className="text-xs font-medium uppercase tracking-wide text-text-secondary">
              Coeficiente R²
            </p>
            <TrendingUp className="h-4 w-4 text-primary-500" aria-hidden="true" />
          </div>
          <div className="flex items-end gap-3">
            <AnimatedNumber
              value={0.998}
              format={(n) => n.toFixed(3)}
              className="text-4xl font-bold md:text-5xl"
            />
            <div className="flex-1 min-w-0">
              <Sparkline data={[0.987, 0.992, 0.995, 0.996, 0.998]} height={40} color="primary" filled />
              <p className="text-xs text-text-muted mt-0.5">v4 → v8</p>
            </div>
          </div>
          <div
            className="h-2 w-full overflow-hidden rounded-full bg-surface-subtle"
            role="progressbar"
            aria-valuenow={99.8}
            aria-valuemin={0}
            aria-valuemax={100}
          >
            <motion.div
              className="h-full rounded-full bg-gradient-to-r from-primary-500 to-accent"
              initial={{ width: 0 }}
              whileInView={{ width: '99.8%' }}
              viewport={{ once: true, margin: '-40px' }}
              transition={{ duration: 1.2, ease: [0.22, 1, 0.36, 1] }}
            />
          </div>
        </BentoCard>

        {/* 5. Portugal map */}
        <BentoCard size="md" className="flex flex-col items-center justify-between">
          <p className="w-full text-xs font-medium uppercase tracking-wide text-text-secondary">
            Cobertura
          </p>
          <div className="flex flex-1 items-center justify-center py-4">
            <PortugalMap />
          </div>
          <div className="w-full text-center">
            <p className="text-2xl font-bold">
              <AnimatedNumber value={5} format={(n) => Math.round(n).toString()} />{' '}
              <span className="text-sm font-medium text-text-secondary">regiões</span>
            </p>
          </div>
        </BentoCard>

        {/* 6. Samples */}
        <BentoCard size="sm" className="flex flex-col justify-between">
          <div className="flex items-start justify-between">
            <p className="text-xs font-medium uppercase tracking-wide text-text-secondary">
              Amostras
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
          Estado operacional
        </p>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 stagger-children">
          <Card title="Estado dos Modelos" subtitle="Modelos carregados na API">
            <div className="mb-3 flex items-center justify-between text-xs text-text-muted">
              <span>Uptime: <span className="font-mono text-text-primary">{uptime}</span></span>
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
                        <><CheckCircle className="w-3.5 h-3.5" aria-hidden="true" /> Carregado</>
                      ) : (
                        <><AlertTriangle className="w-3.5 h-3.5" aria-hidden="true" /> Ausente</>
                      )}
                    </span>
                  </div>
                ))}
            </div>
          </Card>

          <Card title="Informação do Modelo" subtitle="Métricas de treino e metadados">
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
              <LocalEmptyState icon={<Zap className="w-10 h-10" />} message="Informação não disponível" hint="Verifique se a API esta a retornar /model/info" />
            )}
          </Card>
        </div>

        {metrics && (
          <Card title="Métricas Operacionais" subtitle="Resumo do estado operacional">
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

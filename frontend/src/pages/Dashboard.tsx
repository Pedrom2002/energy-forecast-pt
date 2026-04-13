import { useEffect, useRef, useState } from 'react';
import { api, type HealthResponse } from '../api/client';
import { Card, StatCard, CardSkeleton } from '../components/Card';
import { toast } from '../components/Toast';
import { formatKey, formatUptime } from '../utils/format';
import { useDocumentTitle } from '../hooks/useDocumentTitle';
import {
  Activity,
  Clock,
  Cpu,
  Shield,
  AlertTriangle,
  CheckCircle,
  RefreshCw,
  Zap,
  Target,
  TrendingUp,
} from 'lucide-react';

const POLL_INTERVAL_MS = 30_000;

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
        <div className="h-40 bg-surface-bright rounded-2xl skeleton-shimmer" />
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
  const modelsLoaded = health?.models_loaded
    ? Object.values(health.models_loaded).filter(Boolean).length
    : 0;
  const totalModels = health?.models_loaded
    ? Object.keys(health.models_loaded).length
    : 0;

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
    <div className="space-y-6">
      {/* Hero */}
      <section
        className="relative overflow-hidden rounded-2xl border border-primary-100 dark:border-primary-900/40
          bg-gradient-to-br from-primary-50 via-white to-primary-50/30
          dark:from-primary-950/40 dark:via-surface-bright dark:to-primary-900/20
          p-6 md:p-8 shadow-sm animate-fade-in-up"
      >
        {/* soft radial glow */}
        <div
          aria-hidden="true"
          className="pointer-events-none absolute -top-24 -left-24 h-72 w-72 rounded-full
            bg-[radial-gradient(closest-side,theme(colors.primary.300/35),transparent)]
            dark:bg-[radial-gradient(closest-side,theme(colors.primary.500/20),transparent)] blur-2xl"
        />

        <div className="relative flex flex-col gap-6 md:flex-row md:items-start md:justify-between">
          <div className="min-w-0">
            <h1 className="text-4xl md:text-5xl font-bold tracking-tight text-text-primary leading-[1.05]">
              Dashboard
            </h1>
            <p className="mt-3 text-base text-text-secondary max-w-xl">
              Monitorização em tempo real da API e previsões energéticas.
            </p>

            {/* metric pills (desktop inline under subtitle on md, hidden in right block on lg+) */}
            <div className="mt-5 md:hidden -mx-1 px-1 overflow-x-auto">
              <div className="flex items-center gap-2 w-max">
                <MetricPill icon={<Target className="w-4 h-4" />} label="MAPE 1.44%" />
                <MetricPill icon={<Activity className="w-4 h-4" />} label="RMSE 22.9 MW" />
                <MetricPill icon={<TrendingUp className="w-4 h-4" />} label="2.6× baseline" />
              </div>
            </div>
          </div>

          <div className="flex flex-col items-start md:items-end gap-4 shrink-0">
            <button
              type="button"
              onClick={() => load()}
              className="min-w-[44px] min-h-[44px] inline-flex items-center justify-center gap-2 text-sm font-medium
                text-primary-700 dark:text-primary-300 bg-white/70 dark:bg-surface-subtle
                hover:bg-white dark:hover:bg-surface border border-primary-200 dark:border-primary-800/50
                backdrop-blur-sm rounded-lg px-4 cursor-pointer transition-colors
                focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500"
              aria-label="Atualizar dados"
            >
              <RefreshCw className="w-4 h-4" aria-hidden="true" />
              <span className="hidden sm:inline">Atualizar</span>
            </button>
            <p className="text-xs text-text-muted tabular-nums">
              actualizado {formatRelative(lastUpdated, now)}
            </p>

            {/* metric pills (desktop, right-aligned) */}
            <div className="hidden md:flex items-center gap-2 flex-wrap justify-end">
              <MetricPill icon={<Target className="w-4 h-4" />} label="MAPE 1.44%" />
              <MetricPill icon={<Activity className="w-4 h-4" />} label="RMSE 22.9 MW" />
              <MetricPill icon={<TrendingUp className="w-4 h-4" />} label="2.6× baseline" />
            </div>
          </div>
        </div>
      </section>

      {/* Status indicator */}
      <div className="flex items-center gap-3">
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

      {/* Stat cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 stagger-children">
        <StatCard
          label="Estado da API"
          value={isHealthy ? 'Saudável' : 'Degradado'}
          icon={<Activity className="w-5 h-5" />}
          color={isHealthy ? 'green' : 'red'}
          trend={`v${health?.version || '?'}`}
        />
        <StatCard
          label="Tempo em funcionamento"
          value={uptime}
          icon={<Clock className="w-5 h-5" />}
          color="primary"
        />
        <StatCard
          label="Modelos activos"
          value={`${modelsLoaded}/${totalModels}`}
          icon={<Cpu className="w-5 h-5" />}
          color={modelsLoaded === totalModels ? 'primary' : 'yellow'}
          trend={modelsLoaded === totalModels ? 'Todos carregados' : 'Alguns em falta'}
        />
        <StatCard
          label="Cobertura do IC 90%"
          value={health?.coverage_alert ? 'Alerta' : 'Normal'}
          icon={<Shield className="w-5 h-5" />}
          color={health?.coverage_alert ? 'red' : 'primary'}
          trend="Intervalo de confiança 90%"
        />
      </div>

      {/* Model detail + Metrics */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 stagger-children">
        <Card title="Estado dos Modelos" subtitle="Modelos carregados na API">
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

      {/* Operational Metrics */}
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
    </div>
  );
}

function MetricPill({ icon, label }: { icon: React.ReactNode; label: string }) {
  return (
    <span
      className="inline-flex items-center gap-2 rounded-full border border-primary-200
        bg-white/60 dark:bg-surface-subtle dark:border-primary-800/50
        px-4 py-2 text-sm font-medium text-text-primary backdrop-blur-sm whitespace-nowrap"
    >
      <span className="text-primary-600 dark:text-primary-400" aria-hidden="true">{icon}</span>
      {label}
    </span>
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

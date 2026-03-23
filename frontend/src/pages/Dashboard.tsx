import { useEffect, useState } from 'react';
import { api, type HealthResponse } from '../api/client';
import { Card, StatCard, CardSkeleton } from '../components/Card';
import { toast } from '../components/Toast';
import { formatKey, formatUptime } from '../utils/format';
import { Activity, Clock, Cpu, Shield, AlertTriangle, CheckCircle, RefreshCw, Zap } from 'lucide-react';

export default function Dashboard() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [modelInfo, setModelInfo] = useState<Record<string, unknown> | null>(null);
  const [metrics, setMetrics] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
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
      if (h.status === 'rejected') setError(h.reason?.message || 'Erro ao conectar a API');
      else toast.success('Dados atualizados');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  if (loading) {
    return (
      <div className="space-y-6" aria-busy="true">
        <div>
          <div className="h-7 bg-surface-bright rounded w-40 mb-2 skeleton-shimmer" />
          <div className="h-4 bg-surface-bright rounded w-72 skeleton-shimmer" />
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 stagger-children">
          {[1,2,3,4].map(i => <CardSkeleton key={i} lines={2} />)}
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
          <h1 className="text-xl font-bold text-text-primary">API Indisponivel</h1>
          <p className="text-sm text-text-secondary mt-2">{error}</p>
          <p className="text-xs text-text-muted mt-3">
            Certifique-se que a API esta a correr em{' '}
            <code className="bg-surface-bright px-2 py-0.5 rounded-md text-xs font-mono text-primary-600">localhost:8000</code>
          </p>
          <button
            type="button"
            onClick={load}
            className="mt-6 inline-flex items-center gap-2 text-sm font-medium bg-primary-600 hover:bg-primary-700
              text-white px-5 min-h-[44px] rounded-lg transition-colors shadow-sm cursor-pointer
              focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2
              active:scale-[0.98]"
          >
            <RefreshCw className="w-4 h-4" aria-hidden="true" />
            Tentar novamente
          </button>
          <div className="flex justify-center gap-4 mt-3">
            <a href="/predict" className="text-xs text-text-muted hover:text-primary-600 underline transition-colors">Ir para Previsao</a>
            <a href="/monitoring" className="text-xs text-text-muted hover:text-primary-600 underline transition-colors">Ver Monitoring</a>
          </div>
        </div>
      </div>
    );
  }

  const uptime = health?.uptime_seconds
    ? formatUptime(health.uptime_seconds)
    : '—';

  const modelsLoaded = health?.models_loaded
    ? Object.values(health.models_loaded).filter(Boolean).length
    : 0;

  const totalModels = health?.models_loaded
    ? Object.keys(health.models_loaded).length
    : 0;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-text-primary tracking-tight">Dashboard</h1>
          <p className="text-sm text-text-secondary mt-1">
            Monitoramento em tempo real da API de previsao de energia
          </p>
        </div>
        <button
          type="button"
          onClick={load}
          className="min-w-[44px] min-h-[44px] flex items-center justify-center gap-2 text-sm font-medium text-primary-600
            hover:text-primary-800 hover:bg-primary-50 cursor-pointer rounded-lg px-3
            focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 transition-colors"
          aria-label="Atualizar dados"
        >
          <RefreshCw className="w-4 h-4" aria-hidden="true" />
          <span className="hidden sm:inline">Atualizar</span>
        </button>
      </div>

      {/* Stat cards with stagger */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 stagger-children">
        <StatCard
          label="Status"
          value={health?.status === 'healthy' ? 'Saudavel' : 'Degradado'}
          icon={<Activity className="w-5 h-5" />}
          color={health?.status === 'healthy' ? 'green' : 'red'}
          trend={`v${health?.version || '?'}`}
        />
        <StatCard
          label="Uptime"
          value={uptime}
          icon={<Clock className="w-5 h-5" />}
          color="blue"
        />
        <StatCard
          label="Modelos"
          value={`${modelsLoaded}/${totalModels}`}
          icon={<Cpu className="w-5 h-5" />}
          color={modelsLoaded === totalModels ? 'green' : 'yellow'}
          trend={modelsLoaded === totalModels ? 'Todos carregados' : 'Alguns em falta'}
        />
        <StatCard
          label="Cobertura CI"
          value={health?.coverage_alert ? 'Alerta' : 'Normal'}
          icon={<Shield className="w-5 h-5" />}
          color={health?.coverage_alert ? 'red' : 'green'}
          trend="Intervalo de confianca 90%"
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
                        ? 'bg-green-50 text-green-700'
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

        <Card title="Informacao do Modelo" subtitle="Metricas de treino e metadados">
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
            <EmptyState icon={<Zap className="w-10 h-10" />} message="Informacao nao disponivel" hint="Verifique se a API esta a retornar /model/info" />
          )}
        </Card>
      </div>

      {/* Operational Metrics */}
      {metrics && (
        <Card title="Metricas Operacionais" subtitle="Resumo do estado operacional">
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

/* Empty state component for consistency */
function EmptyState({ icon, message, hint }: { icon: React.ReactNode; message: string; hint?: string }) {
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


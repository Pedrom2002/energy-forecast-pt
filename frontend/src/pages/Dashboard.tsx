import { useEffect, useState } from 'react';
import { api, type HealthResponse } from '../api/client';
import { Card, StatCard } from '../components/Card';
import { Activity, Clock, Cpu, Shield, AlertTriangle, CheckCircle } from 'lucide-react';

export default function Dashboard() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [modelInfo, setModelInfo] = useState<Record<string, unknown> | null>(null);
  const [metrics, setMetrics] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
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
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin w-8 h-8 border-4 border-primary-200 border-t-primary-600 rounded-full" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-xl p-6 text-center">
        <AlertTriangle className="w-10 h-10 text-red-500 mx-auto mb-3" />
        <h2 className="text-lg font-semibold text-red-800">API Indisponivel</h2>
        <p className="text-sm text-red-600 mt-1">{error}</p>
        <p className="text-xs text-red-400 mt-2">
          Certifique-se que a API esta a correr em <code className="bg-red-100 px-1 rounded">localhost:8000</code>
        </p>
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
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-text-primary">Dashboard</h1>
        <p className="text-sm text-text-secondary mt-1">
          Monitoramento em tempo real da API de previsao de energia
        </p>
      </div>

      {/* Stat cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
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
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card title="Estado dos Modelos" subtitle="Modelos carregados na API">
          <div className="space-y-3">
            {health?.models_loaded &&
              Object.entries(health.models_loaded).map(([name, loaded]) => (
                <div key={name} className="flex items-center justify-between py-2 border-b border-border last:border-0">
                  <div className="flex items-center gap-2">
                    <Cpu className="w-4 h-4 text-text-muted" />
                    <span className="text-sm font-medium text-text-primary">{name}</span>
                  </div>
                  <span
                    className={`inline-flex items-center gap-1 text-xs font-medium px-2 py-1 rounded-full ${
                      loaded
                        ? 'bg-green-50 text-green-700'
                        : 'bg-red-50 text-red-700'
                    }`}
                  >
                    {loaded ? (
                      <><CheckCircle className="w-3 h-3" /> Carregado</>
                    ) : (
                      <><AlertTriangle className="w-3 h-3" /> Ausente</>
                    )}
                  </span>
                </div>
              ))}
          </div>
        </Card>

        <Card title="Informacao do Modelo" subtitle="Metricas de treino e metadados">
          {modelInfo ? (
            <div className="space-y-2 text-sm">
              {Object.entries(modelInfo).slice(0, 12).map(([key, value]) => (
                <div key={key} className="flex justify-between py-1.5 border-b border-border/50 last:border-0">
                  <span className="text-text-secondary truncate mr-4">{formatKey(key)}</span>
                  <span className="text-text-primary font-mono text-xs truncate max-w-[200px]">
                    {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-text-muted">Informacao nao disponivel</p>
          )}
        </Card>
      </div>

      {/* Operational Metrics */}
      {metrics && (
        <Card title="Metricas Operacionais" subtitle="Resumo do estado operacional">
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            {Object.entries(metrics).map(([key, value]) => (
              <div key={key} className="p-3 bg-surface-dim rounded-lg">
                <p className="text-xs text-text-muted truncate">{formatKey(key)}</p>
                <p className="text-sm font-semibold text-text-primary mt-1 truncate">
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

function formatUptime(seconds: number): string {
  if (seconds < 60) return `${Math.floor(seconds)}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
  return `${Math.floor(seconds / 86400)}d ${Math.floor((seconds % 86400) / 3600)}h`;
}

function formatKey(key: string): string {
  return key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

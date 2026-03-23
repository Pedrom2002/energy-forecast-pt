import { useEffect, useState } from 'react';
import { api } from '../api/client';
import { Card } from '../components/Card';
import { Activity, AlertTriangle, CheckCircle, RefreshCw, Shield } from 'lucide-react';

export default function Monitoring() {
  const [coverage, setCoverage] = useState<Record<string, unknown> | null>(null);
  const [drift, setDrift] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [cov, dr] = await Promise.allSettled([
        api.modelCoverage(),
        api.modelDrift(),
      ]);
      if (cov.status === 'fulfilled') setCoverage(cov.value);
      if (dr.status === 'fulfilled') setDrift(dr.value);
      if (cov.status === 'rejected' && dr.status === 'rejected') {
        setError('Nao foi possivel obter dados de monitoramento');
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin w-8 h-8 border-4 border-primary-200 border-t-primary-600 rounded-full" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-text-primary">Monitoramento do Modelo</h1>
          <p className="text-sm text-text-secondary mt-1">
            Cobertura dos intervalos de confianca e detecao de drift
          </p>
        </div>
        <button
          onClick={load}
          className="flex items-center gap-2 text-sm text-primary-600 hover:text-primary-800 transition"
        >
          <RefreshCw className="w-4 h-4" />
          Atualizar
        </button>
      </div>

      {error && (
        <div className="bg-yellow-50 border border-yellow-200 rounded-xl p-4">
          <p className="text-sm text-yellow-700">{error}</p>
        </div>
      )}

      {/* Coverage Section */}
      <Card title="Cobertura dos Intervalos de Confianca" subtitle="Janela deslizante de 168 observacoes (1 semana)">
        {coverage ? (
          <div className="space-y-4">
            {Object.entries(coverage).map(([key, value]) => {
              if (typeof value === 'number' && key.toLowerCase().includes('coverage')) {
                const pct = (value * 100);
                const isOk = pct >= 80;
                return (
                  <div key={key} className="space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-sm text-text-secondary">{formatKey(key)}</span>
                      <span className={`flex items-center gap-1 text-sm font-semibold ${isOk ? 'text-green-600' : 'text-red-600'}`}>
                        {isOk ? <CheckCircle className="w-4 h-4" /> : <AlertTriangle className="w-4 h-4" />}
                        {pct.toFixed(1)}%
                      </span>
                    </div>
                    <div className="h-3 bg-gray-100 rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full transition-all ${isOk ? 'bg-green-500' : 'bg-red-500'}`}
                        style={{ width: `${Math.min(100, pct)}%` }}
                      />
                    </div>
                    <div className="flex justify-between text-[10px] text-text-muted">
                      <span>0%</span>
                      <span className="text-yellow-600">80% (limiar alerta)</span>
                      <span className="text-green-600">90% (alvo)</span>
                      <span>100%</span>
                    </div>
                  </div>
                );
              }
              return (
                <div key={key} className="flex justify-between py-2 border-b border-border/50 last:border-0">
                  <span className="text-sm text-text-secondary">{formatKey(key)}</span>
                  <span className="text-sm font-mono text-text-primary">
                    {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                  </span>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="text-center py-8">
            <Shield className="w-10 h-10 text-text-muted mx-auto mb-2" />
            <p className="text-sm text-text-muted">
              Sem dados de cobertura. Registe observacoes para comecar o tracking.
            </p>
          </div>
        )}
      </Card>

      {/* Drift Section */}
      <Card title="Baseline de Distribuicao de Features" subtitle="Estatisticas de treino para detecao de drift">
        {drift ? (
          <div className="overflow-x-auto">
            {typeof drift === 'object' && !Array.isArray(drift) ? (
              <div className="space-y-3">
                {Object.entries(drift).slice(0, 20).map(([key, value]) => (
                  <div key={key} className="p-3 bg-surface-dim rounded-lg">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-sm font-medium text-text-primary">{key}</span>
                      {typeof value === 'object' && value !== null && 'mean' in (value as Record<string, unknown>) && (
                        <span className="text-xs text-text-muted font-mono">
                          μ = {Number((value as Record<string, number>).mean).toFixed(2)}
                          {' | '}
                          σ = {Number((value as Record<string, number>).std).toFixed(2)}
                        </span>
                      )}
                    </div>
                    {typeof value === 'object' && value !== null && (
                      <div className="grid grid-cols-4 gap-2 mt-2">
                        {Object.entries(value as Record<string, unknown>).map(([stat, val]) => (
                          <div key={stat} className="text-center">
                            <p className="text-[10px] text-text-muted uppercase">{stat}</p>
                            <p className="text-xs font-mono text-text-primary">
                              {typeof val === 'number' ? val.toFixed(3) : String(val)}
                            </p>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <pre className="text-xs font-mono text-text-secondary whitespace-pre-wrap">
                {JSON.stringify(drift, null, 2)}
              </pre>
            )}
          </div>
        ) : (
          <div className="text-center py-8">
            <Activity className="w-10 h-10 text-text-muted mx-auto mb-2" />
            <p className="text-sm text-text-muted">
              Baseline de drift nao disponivel. O modelo precisa de ter feature_stats nos metadados.
            </p>
          </div>
        )}
      </Card>
    </div>
  );
}

function formatKey(key: string): string {
  return key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

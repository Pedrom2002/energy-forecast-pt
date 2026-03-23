import { useEffect, useState } from 'react';
import { api } from '../api/client';
import { Card, CardSkeleton } from '../components/Card';
import { toast } from '../components/Toast';
import { formatKey } from '../utils/format';
import { Activity, AlertTriangle, CheckCircle, RefreshCw, Shield, Info } from 'lucide-react';

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
      } else {
        toast.success('Dados de monitoramento atualizados');
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  if (loading) {
    return (
      <div className="space-y-6 stagger-children" aria-busy="true">
        <div className="h-7 bg-surface-bright rounded w-60 skeleton-shimmer" />
        <CardSkeleton lines={4} />
        <CardSkeleton lines={6} />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-text-primary tracking-tight">Monitoramento do Modelo</h1>
          <p className="text-sm text-text-secondary mt-1">
            Cobertura dos intervalos de confianca e detecao de drift
          </p>
        </div>
        <button
          type="button"
          onClick={load}
          className="min-w-[44px] min-h-[44px] flex items-center justify-center gap-2 text-sm font-medium text-primary-600
            hover:text-primary-800 hover:bg-primary-50 cursor-pointer rounded-lg px-3
            focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 transition-colors"
          aria-label="Atualizar dados de monitoramento"
        >
          <RefreshCw className="w-4 h-4" aria-hidden="true" />
          <span className="hidden sm:inline">Atualizar</span>
        </button>
      </div>

      {error && (
        <div className="bg-yellow-50 border border-yellow-200 rounded-xl p-4 flex items-start gap-3 animate-fade-in-up" role="alert">
          <AlertTriangle className="w-5 h-5 text-yellow-600 shrink-0 mt-0.5" aria-hidden="true" />
          <div>
            <p className="text-sm font-medium text-yellow-800">Dados limitados</p>
            <p className="text-sm text-yellow-600 mt-0.5">{error}</p>
          </div>
        </div>
      )}

      {/* Coverage Section */}
      <Card title="Cobertura dos Intervalos de Confianca" subtitle="Janela deslizante de 168 observacoes (1 semana)">
        {coverage ? (
          <div className="space-y-5">
            {Object.entries(coverage).map(([key, value]) => {
              if (typeof value === 'number' && key.toLowerCase().includes('coverage')) {
                const pct = value * 100;
                const isOk = pct >= 80;
                const isTarget = pct >= 90;
                return (
                  <div key={key} className="space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium text-text-primary">{formatKey(key)}</span>
                      <span className={`flex items-center gap-1.5 text-sm font-semibold ${isTarget ? 'text-energy-green' : isOk ? 'text-energy-yellow' : 'text-energy-red'}`}>
                        {isTarget ? (
                          <CheckCircle className="w-4 h-4" aria-hidden="true" />
                        ) : (
                          <AlertTriangle className="w-4 h-4" aria-hidden="true" />
                        )}
                        <span className="tabular-nums">{pct.toFixed(1)}%</span>
                      </span>
                    </div>

                    <div
                      className="relative h-3 bg-surface-bright rounded-full overflow-hidden"
                      role="progressbar"
                      aria-valuenow={+pct.toFixed(1)}
                      aria-valuemin={0}
                      aria-valuemax={100}
                      aria-label={`Cobertura: ${pct.toFixed(1)}%`}
                    >
                      <div
                        className={`h-full rounded-full transition-all duration-500 ${isTarget ? 'bg-energy-green' : isOk ? 'bg-energy-yellow' : 'bg-energy-red'}`}
                        style={{ width: `${Math.min(100, pct)}%` }}
                      />
                    </div>

                    <div className="flex justify-between text-[11px] text-text-muted tabular-nums">
                      <span>0%</span>
                      <span className="text-energy-yellow font-medium">80% (alerta)</span>
                      <span className="text-energy-green font-medium">90% (alvo)</span>
                      <span>100%</span>
                    </div>
                  </div>
                );
              }
              return (
                <div key={key} className="flex justify-between py-2.5 px-2 rounded-lg hover:bg-surface-dim transition-colors border-b border-border/50 last:border-0 gap-4">
                  <span className="text-sm text-text-secondary">{formatKey(key)}</span>
                  <span className="text-sm font-mono text-text-primary tabular-nums">
                    {typeof value === 'object' ? JSON.stringify(value) : String(value)}
                  </span>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="text-center py-10">
            <div className="w-14 h-14 rounded-2xl bg-surface-dim flex items-center justify-center mx-auto mb-3">
              <Shield className="w-8 h-8 text-text-muted" aria-hidden="true" />
            </div>
            <p className="text-sm font-medium text-text-secondary">Sem dados de cobertura</p>
            <p className="text-xs text-text-muted mt-1.5 max-w-sm mx-auto">
              Registe observacoes via <code className="bg-surface-bright px-1.5 py-0.5 rounded text-xs font-mono">POST /model/coverage/record</code> para iniciar o tracking.
            </p>
          </div>
        )}
      </Card>

      {/* Drift Section */}
      <Card title="Baseline de Distribuicao de Features" subtitle="Estatisticas de treino para detecao de drift">
        {drift ? (
          <div className="space-y-3">
            <div className="flex items-start gap-2 p-3 bg-primary-50 rounded-lg text-xs text-primary-700 mb-4">
              <Info className="w-4 h-4 shrink-0 mt-0.5" aria-hidden="true" />
              <p>Use <code className="bg-primary-100 px-1 rounded font-mono">POST /model/drift/check</code> para comparar features live com este baseline. Z-score |z| &ge; 3 indica drift significativo.</p>
            </div>

            {Object.entries(drift).slice(0, 20).map(([key, value]) => (
              <details key={key} className="group p-3 bg-surface-dim rounded-lg hover:bg-surface-bright transition-colors">
                <summary className="flex items-center justify-between cursor-pointer list-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 rounded">
                  <span className="text-sm font-medium text-text-primary">{key}</span>
                  {typeof value === 'object' && value !== null && 'mean' in (value as Record<string, unknown>) && (
                    <span className="text-xs text-text-muted font-mono tabular-nums">
                      mu = {Number((value as Record<string, number>).mean).toFixed(2)}
                      {' | '}
                      sigma = {Number((value as Record<string, number>).std).toFixed(2)}
                    </span>
                  )}
                </summary>
                {typeof value === 'object' && value !== null && (
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-3 pt-3 border-t border-border/50">
                    {Object.entries(value as Record<string, unknown>).map(([stat, val]) => (
                      <div key={stat} className="text-center p-2 bg-surface rounded-lg">
                        <p className="text-[10px] text-text-muted uppercase tracking-wider">{stat}</p>
                        <p className="text-xs font-mono text-text-primary tabular-nums mt-0.5">
                          {typeof val === 'number' ? val.toFixed(3) : String(val)}
                        </p>
                      </div>
                    ))}
                  </div>
                )}
              </details>
            ))}
          </div>
        ) : (
          <div className="text-center py-10">
            <div className="w-14 h-14 rounded-2xl bg-surface-dim flex items-center justify-center mx-auto mb-3">
              <Activity className="w-8 h-8 text-text-muted" aria-hidden="true" />
            </div>
            <p className="text-sm font-medium text-text-secondary">Baseline nao disponivel</p>
            <p className="text-xs text-text-muted mt-1.5 max-w-sm mx-auto">
              O modelo precisa de ter <code className="bg-surface-bright px-1.5 py-0.5 rounded text-xs font-mono">feature_stats</code> nos metadados.
            </p>
          </div>
        )}
      </Card>
    </div>
  );
}


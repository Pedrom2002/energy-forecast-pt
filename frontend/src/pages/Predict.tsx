import { useState } from 'react';
import { api, type EnergyData, type PredictionResponse } from '../api/client';
import { Card } from '../components/Card';
import { toast } from '../components/Toast';
import { formatMW, formatDateTime } from '../utils/format';
import WeatherForm from '../components/WeatherForm';
import { Zap, ArrowRight, TrendingUp, TrendingDown, Shield } from 'lucide-react';

function getDefaultTimestamp(): string {
  const now = new Date();
  now.setMinutes(0, 0, 0);
  return now.toISOString().slice(0, 19);
}

export default function Predict() {
  const [data, setData] = useState<EnergyData>({
    timestamp: getDefaultTimestamp(),
    region: 'Lisboa',
    temperature: 18.5,
    humidity: 65.0,
    wind_speed: 12.3,
    precipitation: 0.0,
    cloud_cover: 40.0,
    pressure: 1015.0,
  });
  const [result, setResult] = useState<PredictionResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handlePredict = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.predict(data);
      setResult(res);
      toast.success(`Previsao: ${formatMW(res.predicted_consumption_mw)} para ${res.region}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro desconhecido');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text-primary tracking-tight">Previsao Individual</h1>
        <p className="text-sm text-text-secondary mt-1">
          Obtenha uma previsao de consumo energetico para um momento e regiao especificos
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* Form */}
        <Card title="Parametros" subtitle="Dados meteorologicos e temporais" className="lg:col-span-2">
          <WeatherForm data={data} onChange={setData} idPrefix="pred" />
          <button
            type="button"
            onClick={handlePredict}
            disabled={loading}
            className="mt-6 w-full flex items-center justify-center gap-2 bg-primary-600 hover:bg-primary-700 disabled:bg-primary-300 disabled:cursor-not-allowed
              text-white font-medium min-h-[44px] px-4 rounded-lg transition-all duration-200 shadow-sm cursor-pointer
              focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2
              active:scale-[0.97]"
            aria-busy={loading}
          >
            {loading ? (
              <div className="animate-spin w-5 h-5 border-2 border-white/30 border-t-white rounded-full" role="status">
                <span className="sr-only">A processar...</span>
              </div>
            ) : (
              <>
                <Zap className="w-4 h-4" aria-hidden="true" />
                Prever Consumo
                <ArrowRight className="w-4 h-4" aria-hidden="true" />
              </>
            )}
          </button>
        </Card>

        {/* Result */}
        <div className="lg:col-span-3 space-y-4">
          {error && (
            <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-xl p-4 animate-fade-in-up" role="alert">
              <p className="text-sm text-red-700 dark:text-red-200 font-medium">Erro: {error}</p>
              <p className="text-xs text-red-500 dark:text-red-400 mt-1">Verifique os parametros e tente novamente.</p>
            </div>
          )}

          {result && (
            <div className="space-y-4 stagger-children">
              {/* Main prediction */}
              <div className="bg-gradient-to-br from-primary-600 to-primary-800 rounded-xl p-6 text-white shadow-lg" aria-live="polite">
                <div className="flex items-center gap-2 text-primary-200 text-sm mb-2">
                  <Zap className="w-4 h-4" aria-hidden="true" />
                  Consumo Previsto
                </div>
                <p className="text-4xl font-bold tabular-nums">
                  {formatMW(result.predicted_consumption_mw)}
                </p>
                <p className="mt-3 text-sm text-primary-200">
                  {result.region} &middot; {formatDateTime(result.timestamp)}
                </p>
              </div>

              {/* CI */}
              <Card title="Intervalo de Confianca" subtitle={`${(result.confidence_level * 100).toFixed(0)}% - Metodo: ${result.ci_method}`}>
                <div className="flex items-center gap-3 sm:gap-4">
                  <div className="flex-1 text-center p-3 sm:p-4 bg-blue-50 rounded-lg hover:bg-blue-100/60 transition-colors">
                    <TrendingDown className="w-5 h-5 text-blue-500 mx-auto mb-1" aria-hidden="true" />
                    <p className="text-xs text-text-muted">Limite Inferior</p>
                    <p className="text-base sm:text-lg font-bold text-blue-700 tabular-nums">
                      {result.confidence_interval_lower.toFixed(1)} MW
                    </p>
                    {result.ci_lower_clipped && (
                      <span className="inline-flex items-center gap-1 text-[10px] text-yellow-700 bg-yellow-50 px-1.5 py-0.5 rounded mt-1">
                        <Shield className="w-2.5 h-2.5" aria-hidden="true" /> clipped
                      </span>
                    )}
                  </div>
                  <div className="flex-1 text-center p-3 sm:p-4 bg-primary-50 rounded-lg border-2 border-primary-200">
                    <Zap className="w-5 h-5 text-primary-600 mx-auto mb-1" aria-hidden="true" />
                    <p className="text-xs text-text-muted">Previsao</p>
                    <p className="text-lg sm:text-xl font-bold text-primary-700 tabular-nums">
                      {result.predicted_consumption_mw.toFixed(1)} MW
                    </p>
                  </div>
                  <div className="flex-1 text-center p-3 sm:p-4 bg-blue-50 rounded-lg hover:bg-blue-100/60 transition-colors">
                    <TrendingUp className="w-5 h-5 text-blue-500 mx-auto mb-1" aria-hidden="true" />
                    <p className="text-xs text-text-muted">Limite Superior</p>
                    <p className="text-base sm:text-lg font-bold text-blue-700 tabular-nums">
                      {result.confidence_interval_upper.toFixed(1)} MW
                    </p>
                  </div>
                </div>

                {/* CI bar visualization */}
                <div className="mt-4" role="img" aria-label={`Intervalo de confianca de ${result.confidence_interval_lower.toFixed(0)} a ${result.confidence_interval_upper.toFixed(0)} MW`}>
                  <div className="relative h-3 bg-surface-bright rounded-full overflow-hidden">
                    {(() => {
                      const range = result.confidence_interval_upper - result.confidence_interval_lower;
                      const predPos = range > 0
                        ? ((result.predicted_consumption_mw - result.confidence_interval_lower) / range) * 100
                        : 50;
                      return (
                        <>
                          <div className="absolute inset-0 bg-gradient-to-r from-blue-200 via-primary-300 to-blue-200 rounded-full" />
                          <div
                            className="absolute top-0 bottom-0 w-1 bg-primary-700 rounded-full transition-all duration-300"
                            style={{ left: `${Math.max(0, Math.min(100, predPos))}%` }}
                          />
                        </>
                      );
                    })()}
                  </div>
                  <div className="flex justify-between text-[11px] text-text-muted mt-1 tabular-nums">
                    <span>{result.confidence_interval_lower.toFixed(0)} MW</span>
                    <span>{result.confidence_interval_upper.toFixed(0)} MW</span>
                  </div>
                </div>
              </Card>

              {/* Model info */}
              <div className="flex gap-3 sm:gap-4">
                <div className="flex-1 bg-surface border border-border rounded-xl p-4 hover:shadow-md transition-shadow">
                  <div className="flex items-center gap-2 text-xs text-text-muted mb-1">
                    <Shield className="w-3.5 h-3.5" aria-hidden="true" />
                    Metodo CI
                  </div>
                  <p className="text-sm font-semibold text-text-primary">
                    {result.ci_method === 'conformal' ? 'Conformal Prediction' : 'Gaussian Z x RMSE'}
                  </p>
                </div>
                <div className="flex-1 bg-surface border border-border rounded-xl p-4 hover:shadow-md transition-shadow">
                  <div className="flex items-center gap-2 text-xs text-text-muted mb-1">
                    <Zap className="w-3.5 h-3.5" aria-hidden="true" />
                    Modelo
                  </div>
                  <p className="text-sm font-semibold text-text-primary">{result.model_name}</p>
                </div>
              </div>
            </div>
          )}

          {!result && !error && (
            <div className="bg-surface border border-border rounded-xl p-12 text-center">
              <div className="w-16 h-16 rounded-2xl bg-primary-50 flex items-center justify-center mx-auto mb-4">
                <Zap className="w-8 h-8 text-primary-300" aria-hidden="true" />
              </div>
              <p className="text-sm font-medium text-text-secondary">Pronto para prever</p>
              <p className="text-xs text-text-muted mt-1.5 max-w-xs mx-auto">
                Preencha os parametros meteorologicos e clique em "Prever Consumo" para obter a estimativa
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

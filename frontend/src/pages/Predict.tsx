import { useState } from 'react';
import { api, type EnergyData, type PredictionResponse } from '../api/client';
import { Card } from '../components/Card';
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
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro desconhecido');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text-primary">Previsao Individual</h1>
        <p className="text-sm text-text-secondary mt-1">
          Obtenha uma previsao de consumo energetico para um momento e regiao especificos
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* Form */}
        <Card title="Parametros" subtitle="Dados meteorologicos e temporais" className="lg:col-span-2">
          <WeatherForm data={data} onChange={setData} />
          <button
            onClick={handlePredict}
            disabled={loading}
            className="mt-6 w-full flex items-center justify-center gap-2 bg-primary-600 hover:bg-primary-700 disabled:bg-primary-300 text-white font-medium py-2.5 px-4 rounded-lg transition shadow-sm"
          >
            {loading ? (
              <div className="animate-spin w-4 h-4 border-2 border-white/30 border-t-white rounded-full" />
            ) : (
              <>
                <Zap className="w-4 h-4" />
                Prever Consumo
                <ArrowRight className="w-4 h-4" />
              </>
            )}
          </button>
        </Card>

        {/* Result */}
        <div className="lg:col-span-3 space-y-4">
          {error && (
            <div className="bg-red-50 border border-red-200 rounded-xl p-4">
              <p className="text-sm text-red-700">{error}</p>
            </div>
          )}

          {result && (
            <>
              {/* Main prediction */}
              <div className="bg-gradient-to-br from-primary-600 to-primary-800 rounded-xl p-6 text-white shadow-lg">
                <div className="flex items-center gap-2 text-primary-200 text-sm mb-2">
                  <Zap className="w-4 h-4" />
                  Consumo Previsto
                </div>
                <div className="text-4xl font-bold">
                  {result.predicted_consumption_mw.toFixed(1)}
                  <span className="text-lg font-normal text-primary-200 ml-2">MW</span>
                </div>
                <div className="mt-3 text-sm text-primary-200">
                  {result.region} &middot; {new Date(result.timestamp).toLocaleString('pt-PT')}
                </div>
              </div>

              {/* CI */}
              <Card title="Intervalo de Confianca" subtitle={`${(result.confidence_level * 100).toFixed(0)}% - Metodo: ${result.ci_method}`}>
                <div className="flex items-center gap-4">
                  <div className="flex-1 text-center p-4 bg-blue-50 rounded-lg">
                    <TrendingDown className="w-5 h-5 text-blue-500 mx-auto mb-1" />
                    <p className="text-xs text-text-muted">Limite Inferior</p>
                    <p className="text-lg font-bold text-blue-700">
                      {result.confidence_interval_lower.toFixed(1)} MW
                    </p>
                    {result.ci_lower_clipped && (
                      <span className="text-[10px] text-yellow-600 bg-yellow-50 px-1.5 py-0.5 rounded">clipped</span>
                    )}
                  </div>
                  <div className="flex-1 text-center p-4 bg-primary-50 rounded-lg border-2 border-primary-200">
                    <Zap className="w-5 h-5 text-primary-600 mx-auto mb-1" />
                    <p className="text-xs text-text-muted">Previsao</p>
                    <p className="text-xl font-bold text-primary-700">
                      {result.predicted_consumption_mw.toFixed(1)} MW
                    </p>
                  </div>
                  <div className="flex-1 text-center p-4 bg-blue-50 rounded-lg">
                    <TrendingUp className="w-5 h-5 text-blue-500 mx-auto mb-1" />
                    <p className="text-xs text-text-muted">Limite Superior</p>
                    <p className="text-lg font-bold text-blue-700">
                      {result.confidence_interval_upper.toFixed(1)} MW
                    </p>
                  </div>
                </div>

                {/* CI bar visualization */}
                <div className="mt-4">
                  <div className="relative h-3 bg-gray-100 rounded-full overflow-hidden">
                    {(() => {
                      const range = result.confidence_interval_upper - result.confidence_interval_lower;
                      const predPos = range > 0
                        ? ((result.predicted_consumption_mw - result.confidence_interval_lower) / range) * 100
                        : 50;
                      return (
                        <>
                          <div className="absolute inset-0 bg-gradient-to-r from-blue-200 via-primary-300 to-blue-200 rounded-full" />
                          <div
                            className="absolute top-0 bottom-0 w-1 bg-primary-700 rounded-full"
                            style={{ left: `${predPos}%` }}
                          />
                        </>
                      );
                    })()}
                  </div>
                  <div className="flex justify-between text-[10px] text-text-muted mt-1">
                    <span>{result.confidence_interval_lower.toFixed(0)} MW</span>
                    <span>{result.confidence_interval_upper.toFixed(0)} MW</span>
                  </div>
                </div>
              </Card>

              {/* Model info */}
              <div className="flex gap-4">
                <div className="flex-1 bg-white border border-border rounded-xl p-4">
                  <div className="flex items-center gap-2 text-xs text-text-muted mb-1">
                    <Shield className="w-3.5 h-3.5" />
                    Metodo CI
                  </div>
                  <p className="text-sm font-semibold text-text-primary">
                    {result.ci_method === 'conformal' ? 'Conformal Prediction' : 'Gaussian Z×RMSE'}
                  </p>
                </div>
                <div className="flex-1 bg-white border border-border rounded-xl p-4">
                  <div className="flex items-center gap-2 text-xs text-text-muted mb-1">
                    <Zap className="w-3.5 h-3.5" />
                    Modelo
                  </div>
                  <p className="text-sm font-semibold text-text-primary">{result.model_name}</p>
                </div>
              </div>
            </>
          )}

          {!result && !error && (
            <div className="bg-white border border-border rounded-xl p-12 text-center">
              <Zap className="w-12 h-12 text-primary-200 mx-auto mb-3" />
              <p className="text-text-muted">Preencha os parametros e clique em "Prever Consumo"</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

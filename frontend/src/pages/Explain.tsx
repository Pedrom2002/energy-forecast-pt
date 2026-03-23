import { useState } from 'react';
import { api, type EnergyData, type ExplanationResponse } from '../api/client';
import { Card } from '../components/Card';
import WeatherForm from '../components/WeatherForm';
import { Brain, Zap, ArrowRight } from 'lucide-react';
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

function getDefaultTimestamp(): string {
  const now = new Date();
  now.setMinutes(0, 0, 0);
  return now.toISOString().slice(0, 19);
}

const COLORS = [
  '#3b82f6', '#2563eb', '#1d4ed8', '#1e40af', '#1e3a8a',
  '#60a5fa', '#93c5fd', '#bfdbfe', '#dbeafe', '#eff6ff',
];

export default function Explain() {
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
  const [topN, setTopN] = useState(10);
  const [result, setResult] = useState<ExplanationResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleExplain = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.predictExplain(data, topN);
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro desconhecido');
    } finally {
      setLoading(false);
    }
  };

  const chartData = result?.top_features.map((f) => ({
    name: f.feature.length > 20 ? f.feature.slice(0, 18) + '...' : f.feature,
    fullName: f.feature,
    importance: +(f.importance * 100).toFixed(2),
    value: f.value,
    rank: f.rank,
  })) || [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text-primary">Explicabilidade</h1>
        <p className="text-sm text-text-secondary mt-1">
          Entenda quais features mais influenciam a previsao do modelo
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* Form */}
        <Card title="Parametros" className="lg:col-span-2">
          <WeatherForm data={data} onChange={setData} />
          <div className="mt-4">
            <label className="block text-xs font-medium text-text-secondary mb-1.5">
              Top N Features
            </label>
            <input
              type="number"
              value={topN}
              onChange={(e) => setTopN(Math.min(30, Math.max(3, parseInt(e.target.value) || 5)))}
              min={3}
              max={30}
              className="block w-full rounded-lg border border-border bg-white px-3 py-2 text-sm shadow-sm focus:border-primary-500 focus:ring-2 focus:ring-primary-200 focus:outline-none transition"
            />
          </div>
          <button
            onClick={handleExplain}
            disabled={loading}
            className="mt-6 w-full flex items-center justify-center gap-2 bg-primary-600 hover:bg-primary-700 disabled:bg-primary-300 text-white font-medium py-2.5 px-4 rounded-lg transition shadow-sm"
          >
            {loading ? (
              <div className="animate-spin w-4 h-4 border-2 border-white/30 border-t-white rounded-full" />
            ) : (
              <>
                <Brain className="w-4 h-4" />
                Explicar Previsao
                <ArrowRight className="w-4 h-4" />
              </>
            )}
          </button>
        </Card>

        {/* Results */}
        <div className="lg:col-span-3 space-y-4">
          {error && (
            <div className="bg-red-50 border border-red-200 rounded-xl p-4">
              <p className="text-sm text-red-700">{error}</p>
            </div>
          )}

          {result && (
            <>
              {/* Prediction summary */}
              <div className="bg-gradient-to-br from-purple-600 to-primary-800 rounded-xl p-5 text-white shadow-lg">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-sm text-purple-200 flex items-center gap-1">
                      <Zap className="w-4 h-4" /> Previsao
                    </p>
                    <p className="text-3xl font-bold mt-1">
                      {result.prediction.predicted_consumption_mw.toFixed(1)}
                      <span className="text-lg font-normal text-purple-200 ml-2">MW</span>
                    </p>
                  </div>
                  <div className="text-right text-sm text-purple-200">
                    <p>Metodo: {result.explanation_method}</p>
                    <p>{result.total_features} features totais</p>
                    <p>Top {result.top_features.length} mostradas</p>
                  </div>
                </div>
              </div>

              {/* Chart */}
              <Card title="Importancia das Features" subtitle={`Metodo: ${result.explanation_method}`}>
                <div className="h-[350px]">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart
                      data={chartData}
                      layout="vertical"
                      margin={{ top: 5, right: 30, left: 100, bottom: 5 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" horizontal={false} />
                      <XAxis
                        type="number"
                        tick={{ fontSize: 10, fill: '#94a3b8' }}
                        label={{ value: 'Importancia (%)', position: 'insideBottom', offset: -5, style: { fontSize: 11, fill: '#94a3b8' } }}
                      />
                      <YAxis
                        type="category"
                        dataKey="name"
                        tick={{ fontSize: 11, fill: '#475569' }}
                        width={95}
                      />
                      <Tooltip
                        content={({ active, payload }) => {
                          if (!active || !payload?.length) return null;
                          const d = payload[0].payload;
                          return (
                            <div className="bg-white border border-border rounded-lg p-3 shadow-lg text-xs">
                              <p className="font-semibold text-text-primary">{d.fullName}</p>
                              <p className="text-text-secondary mt-1">
                                Importancia: <span className="font-mono">{d.importance.toFixed(2)}%</span>
                              </p>
                              <p className="text-text-secondary">
                                Valor: <span className="font-mono">{d.value.toFixed(4)}</span>
                              </p>
                              <p className="text-text-muted">Rank: #{d.rank}</p>
                            </div>
                          );
                        }}
                      />
                      <Bar dataKey="importance" radius={[0, 4, 4, 0]}>
                        {chartData.map((_, idx) => (
                          <Cell key={idx} fill={COLORS[idx % COLORS.length]} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </Card>

              {/* Feature table */}
              <Card title="Detalhes das Features">
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-border">
                        <th className="text-left py-2 px-3 text-xs font-medium text-text-muted">#</th>
                        <th className="text-left py-2 px-3 text-xs font-medium text-text-muted">Feature</th>
                        <th className="text-right py-2 px-3 text-xs font-medium text-text-muted">Importancia</th>
                        <th className="text-right py-2 px-3 text-xs font-medium text-text-muted">Valor</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.top_features.map((f) => (
                        <tr key={f.rank} className="border-b border-border/50 hover:bg-surface-dim transition">
                          <td className="py-2 px-3 text-text-muted">{f.rank}</td>
                          <td className="py-2 px-3 font-mono text-xs text-text-primary">{f.feature}</td>
                          <td className="py-2 px-3 text-right">
                            <div className="flex items-center justify-end gap-2">
                              <div className="w-16 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                                <div
                                  className="h-full bg-primary-500 rounded-full"
                                  style={{ width: `${f.importance * 100}%` }}
                                />
                              </div>
                              <span className="font-mono text-xs text-text-primary w-12 text-right">
                                {(f.importance * 100).toFixed(1)}%
                              </span>
                            </div>
                          </td>
                          <td className="py-2 px-3 text-right font-mono text-xs text-text-secondary">
                            {f.value.toFixed(4)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Card>
            </>
          )}

          {!result && !error && (
            <div className="bg-white border border-border rounded-xl p-12 text-center">
              <Brain className="w-12 h-12 text-primary-200 mx-auto mb-3" />
              <p className="text-text-muted">Preencha os parametros e clique em "Explicar Previsao"</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

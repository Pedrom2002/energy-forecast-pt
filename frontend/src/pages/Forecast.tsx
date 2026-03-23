import { useState } from 'react';
import { api, type EnergyData, type PredictionResponse, REGIONS, type Region } from '../api/client';
import { Card } from '../components/Card';
import { TrendingUp, Play } from 'lucide-react';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts';

function generateHistory(region: Region, hours: number) {
  const records = [];
  const now = new Date();
  now.setMinutes(0, 0, 0);
  for (let i = hours; i > 0; i--) {
    const d = new Date(now.getTime() - i * 3600000);
    const hour = d.getHours();
    const baseConsumption = 1500 + 500 * Math.sin(((hour - 3) / 24) * Math.PI * 2);
    records.push({
      timestamp: d.toISOString().slice(0, 19),
      region,
      temperature: 15 + 8 * Math.sin(((hour - 6) / 24) * Math.PI * 2) + (Math.random() - 0.5) * 2,
      humidity: 65 + 15 * Math.cos(((hour - 14) / 24) * Math.PI * 2),
      wind_speed: 10 + Math.random() * 8,
      precipitation: Math.random() < 0.1 ? Math.random() * 3 : 0,
      cloud_cover: 40 + Math.random() * 30,
      pressure: 1010 + Math.random() * 8,
      consumption_mw: baseConsumption + (Math.random() - 0.5) * 200,
    });
  }
  return records;
}

function generateForecastItems(region: Region, hours: number): EnergyData[] {
  const items: EnergyData[] = [];
  const now = new Date();
  now.setMinutes(0, 0, 0);
  for (let i = 1; i <= hours; i++) {
    const d = new Date(now.getTime() + i * 3600000);
    const hour = d.getHours();
    items.push({
      timestamp: d.toISOString().slice(0, 19),
      region,
      temperature: 15 + 8 * Math.sin(((hour - 6) / 24) * Math.PI * 2) + (Math.random() - 0.5) * 3,
      humidity: 65 + 15 * Math.cos(((hour - 14) / 24) * Math.PI * 2),
      wind_speed: 10 + Math.random() * 10,
      precipitation: Math.random() < 0.15 ? Math.random() * 5 : 0,
      cloud_cover: 40 + Math.random() * 30,
      pressure: 1010 + Math.random() * 10,
    });
  }
  return items;
}

export default function Forecast() {
  const [region, setRegion] = useState<Region>('Lisboa');
  const [historyHours, setHistoryHours] = useState(72);
  const [forecastHours, setForecastHours] = useState(24);
  const [results, setResults] = useState<PredictionResponse[]>([]);
  const [historyData, setHistoryData] = useState<{ timestamp: string; consumption_mw: number }[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [modelName, setModelName] = useState('');

  const handleForecast = async () => {
    setLoading(true);
    setError(null);
    try {
      const history = generateHistory(region, historyHours);
      const forecast = generateForecastItems(region, forecastHours);
      const res = await api.predictSequential(history, forecast);
      setResults(res.predictions);
      setHistoryData(history.map((h) => ({ timestamp: h.timestamp, consumption_mw: h.consumption_mw })));
      setModelName(res.model_name);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro desconhecido');
    } finally {
      setLoading(false);
    }
  };

  const chartData = [
    ...historyData.map((h) => ({
      time: new Date(h.timestamp).toLocaleString('pt-PT', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }),
      actual: h.consumption_mw,
      predicted: null as number | null,
      ciUpper: null as number | null,
      ciLower: null as number | null,
    })),
    ...results.map((r) => ({
      time: new Date(r.timestamp).toLocaleString('pt-PT', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }),
      actual: null as number | null,
      predicted: r.predicted_consumption_mw,
      ciUpper: r.confidence_interval_upper,
      ciLower: r.confidence_interval_lower,
    })),
  ];

  const nowLabel = historyData.length > 0
    ? new Date(historyData[historyData.length - 1].timestamp).toLocaleString('pt-PT', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
    : '';

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text-primary">Forecast Sequencial</h1>
        <p className="text-sm text-text-secondary mt-1">
          Previsao lag-aware autoregressiva com historico e intervalos de confianca
        </p>
      </div>

      <Card title="Configuracao">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div>
            <label className="block text-xs font-medium text-text-secondary mb-1.5">Regiao</label>
            <select
              value={region}
              onChange={(e) => setRegion(e.target.value as Region)}
              className="block w-full rounded-lg border border-border bg-white px-3 py-2.5 text-sm shadow-sm focus:border-primary-500 focus:ring-2 focus:ring-primary-200 focus:outline-none transition"
            >
              {REGIONS.map((r) => (
                <option key={r} value={r}>{r}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-text-secondary mb-1.5">Historico (horas)</label>
            <input
              type="number"
              value={historyHours}
              onChange={(e) => setHistoryHours(Math.max(48, parseInt(e.target.value) || 48))}
              min={48}
              max={336}
              className="block w-full rounded-lg border border-border bg-white px-3 py-2.5 text-sm shadow-sm focus:border-primary-500 focus:ring-2 focus:ring-primary-200 focus:outline-none transition"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-text-secondary mb-1.5">Previsao (horas)</label>
            <input
              type="number"
              value={forecastHours}
              onChange={(e) => setForecastHours(Math.min(168, Math.max(1, parseInt(e.target.value) || 1)))}
              min={1}
              max={168}
              className="block w-full rounded-lg border border-border bg-white px-3 py-2.5 text-sm shadow-sm focus:border-primary-500 focus:ring-2 focus:ring-primary-200 focus:outline-none transition"
            />
          </div>
          <div className="flex items-end">
            <button
              onClick={handleForecast}
              disabled={loading}
              className="w-full flex items-center justify-center gap-2 bg-primary-600 hover:bg-primary-700 disabled:bg-primary-300 text-white font-medium py-2.5 px-4 rounded-lg transition shadow-sm"
            >
              {loading ? (
                <div className="animate-spin w-4 h-4 border-2 border-white/30 border-t-white rounded-full" />
              ) : (
                <>
                  <Play className="w-4 h-4" />
                  Executar Forecast
                </>
              )}
            </button>
          </div>
        </div>
        <p className="text-xs text-text-muted mt-3">
          Dados meteorologicos simulados para demonstracao. Em producao, integre com dados reais.
        </p>
      </Card>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4">
          <p className="text-sm text-red-700">{error}</p>
        </div>
      )}

      {chartData.length > 0 && (
        <Card
          title="Grafico de Previsao"
          subtitle={`Modelo: ${modelName} | Regiao: ${region}`}
        >
          <div className="h-[400px]">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData} margin={{ top: 10, right: 30, left: 10, bottom: 0 }}>
                <defs>
                  <linearGradient id="ciGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.15} />
                    <stop offset="95%" stopColor="#3b82f6" stopOpacity={0.02} />
                  </linearGradient>
                  <linearGradient id="actualGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#22c55e" stopOpacity={0.2} />
                    <stop offset="95%" stopColor="#22c55e" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis
                  dataKey="time"
                  tick={{ fontSize: 10, fill: '#94a3b8' }}
                  interval="preserveStartEnd"
                  tickCount={8}
                />
                <YAxis
                  tick={{ fontSize: 10, fill: '#94a3b8' }}
                  label={{ value: 'MW', angle: -90, position: 'insideLeft', style: { fontSize: 11, fill: '#94a3b8' } }}
                />
                <Tooltip
                  contentStyle={{
                    borderRadius: '8px',
                    border: '1px solid #e2e8f0',
                    fontSize: '12px',
                    boxShadow: '0 4px 6px -1px rgba(0,0,0,.1)',
                  }}
                />
                {nowLabel && (
                  <ReferenceLine x={nowLabel} stroke="#94a3b8" strokeDasharray="4 4" label={{ value: 'Agora', fill: '#64748b', fontSize: 10 }} />
                )}
                <Area
                  type="monotone"
                  dataKey="ciUpper"
                  stroke="none"
                  fill="url(#ciGrad)"
                  name="CI Superior"
                />
                <Area
                  type="monotone"
                  dataKey="ciLower"
                  stroke="none"
                  fill="transparent"
                  name="CI Inferior"
                />
                <Area
                  type="monotone"
                  dataKey="actual"
                  stroke="#22c55e"
                  fill="url(#actualGrad)"
                  strokeWidth={2}
                  name="Consumo Real"
                  dot={false}
                  connectNulls={false}
                />
                <Area
                  type="monotone"
                  dataKey="predicted"
                  stroke="#3b82f6"
                  fill="none"
                  strokeWidth={2}
                  strokeDasharray="5 3"
                  name="Previsao"
                  dot={false}
                  connectNulls={false}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
          <div className="flex items-center justify-center gap-6 mt-4 text-xs text-text-muted">
            <span className="flex items-center gap-1.5">
              <span className="w-3 h-0.5 bg-green-500 rounded" /> Consumo Real
            </span>
            <span className="flex items-center gap-1.5">
              <span className="w-3 h-0.5 bg-blue-500 rounded border-dashed" style={{ borderTop: '2px dashed #3b82f6', height: 0 }} /> Previsao
            </span>
            <span className="flex items-center gap-1.5">
              <span className="w-3 h-3 bg-blue-100 rounded" /> IC 90%
            </span>
          </div>
        </Card>
      )}

      {chartData.length === 0 && !error && (
        <div className="bg-white border border-border rounded-xl p-12 text-center">
          <TrendingUp className="w-12 h-12 text-primary-200 mx-auto mb-3" />
          <p className="text-text-muted">Configure os parametros e execute o forecast sequencial</p>
        </div>
      )}
    </div>
  );
}

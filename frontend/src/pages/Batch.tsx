import { useState } from 'react';
import { api, type EnergyData, type PredictionResponse, REGIONS, type Region } from '../api/client';
import { Card } from '../components/Card';
import { Layers, Play, Download, MapPin } from 'lucide-react';

function generateBatchItems(region: Region, startDate: string, hours: number): EnergyData[] {
  const items: EnergyData[] = [];
  const start = new Date(startDate);
  for (let i = 0; i < hours; i++) {
    const d = new Date(start.getTime() + i * 3600000);
    const hour = d.getHours();
    items.push({
      timestamp: d.toISOString().slice(0, 19),
      region,
      temperature: 15 + 8 * Math.sin(((hour - 6) / 24) * Math.PI * 2) + (Math.random() - 0.5) * 3,
      humidity: 65 + 15 * Math.cos(((hour - 14) / 24) * Math.PI * 2) + (Math.random() - 0.5) * 10,
      wind_speed: 10 + Math.random() * 10,
      precipitation: Math.random() < 0.15 ? Math.random() * 5 : 0,
      cloud_cover: 40 + Math.random() * 30,
      pressure: 1010 + Math.random() * 10,
    });
  }
  return items;
}

export default function Batch() {
  const [region, setRegion] = useState<Region>('Lisboa');
  const [startDate, setStartDate] = useState(() => {
    const d = new Date();
    d.setHours(0, 0, 0, 0);
    return d.toISOString().slice(0, 16);
  });
  const [hours, setHours] = useState(24);
  const [results, setResults] = useState<PredictionResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleBatch = async () => {
    setLoading(true);
    setError(null);
    try {
      const items = generateBatchItems(region, startDate, hours);
      const res = await api.predictBatch(items);
      setResults(res.predictions);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro desconhecido');
    } finally {
      setLoading(false);
    }
  };

  const handleExportCSV = () => {
    if (!results.length) return;
    const header = 'timestamp,region,predicted_mw,ci_lower,ci_upper,model,ci_method\n';
    const rows = results.map(r =>
      `${r.timestamp},${r.region},${r.predicted_consumption_mw.toFixed(2)},${r.confidence_interval_lower.toFixed(2)},${r.confidence_interval_upper.toFixed(2)},${r.model_name},${r.ci_method}`
    ).join('\n');
    const blob = new Blob([header + rows], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `batch_predictions_${region}_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text-primary">Previsao em Lote</h1>
        <p className="text-sm text-text-secondary mt-1">
          Gere previsoes para multiplas horas de uma so vez (ate 1000 itens)
        </p>
      </div>

      <Card title="Configuracao do Lote">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div>
            <label className="flex items-center gap-1.5 text-xs font-medium text-text-secondary mb-1.5">
              <MapPin className="w-3.5 h-3.5" /> Regiao
            </label>
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
            <label className="block text-xs font-medium text-text-secondary mb-1.5">Data Inicio</label>
            <input
              type="datetime-local"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="block w-full rounded-lg border border-border bg-white px-3 py-2.5 text-sm shadow-sm focus:border-primary-500 focus:ring-2 focus:ring-primary-200 focus:outline-none transition"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-text-secondary mb-1.5">Horas</label>
            <input
              type="number"
              value={hours}
              onChange={(e) => setHours(Math.min(168, Math.max(1, parseInt(e.target.value) || 1)))}
              min={1}
              max={168}
              className="block w-full rounded-lg border border-border bg-white px-3 py-2.5 text-sm shadow-sm focus:border-primary-500 focus:ring-2 focus:ring-primary-200 focus:outline-none transition"
            />
          </div>
          <div className="flex items-end">
            <button
              onClick={handleBatch}
              disabled={loading}
              className="w-full flex items-center justify-center gap-2 bg-primary-600 hover:bg-primary-700 disabled:bg-primary-300 text-white font-medium py-2.5 px-4 rounded-lg transition shadow-sm"
            >
              {loading ? (
                <div className="animate-spin w-4 h-4 border-2 border-white/30 border-t-white rounded-full" />
              ) : (
                <>
                  <Play className="w-4 h-4" />
                  Executar
                </>
              )}
            </button>
          </div>
        </div>
      </Card>

      {error && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4">
          <p className="text-sm text-red-700">{error}</p>
        </div>
      )}

      {results.length > 0 && (
        <Card
          title={`Resultados (${results.length} previsoes)`}
          action={
            <button
              onClick={handleExportCSV}
              className="flex items-center gap-1.5 text-xs font-medium text-primary-600 hover:text-primary-800 transition"
            >
              <Download className="w-3.5 h-3.5" />
              Exportar CSV
            </button>
          }
        >
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border">
                  <th className="text-left py-2 px-3 text-xs font-medium text-text-muted">Hora</th>
                  <th className="text-right py-2 px-3 text-xs font-medium text-text-muted">Previsao (MW)</th>
                  <th className="text-right py-2 px-3 text-xs font-medium text-text-muted">CI Inferior</th>
                  <th className="text-right py-2 px-3 text-xs font-medium text-text-muted">CI Superior</th>
                  <th className="text-right py-2 px-3 text-xs font-medium text-text-muted">Amplitude</th>
                  <th className="text-center py-2 px-3 text-xs font-medium text-text-muted">Metodo</th>
                </tr>
              </thead>
              <tbody>
                {results.map((r, i) => {
                  const range = r.confidence_interval_upper - r.confidence_interval_lower;
                  return (
                    <tr key={i} className="border-b border-border/50 hover:bg-surface-dim transition">
                      <td className="py-2 px-3 text-text-secondary font-mono text-xs">
                        {new Date(r.timestamp).toLocaleString('pt-PT', { hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit' })}
                      </td>
                      <td className="py-2 px-3 text-right font-semibold text-text-primary">
                        {r.predicted_consumption_mw.toFixed(1)}
                      </td>
                      <td className="py-2 px-3 text-right text-blue-600 font-mono text-xs">
                        {r.confidence_interval_lower.toFixed(1)}
                      </td>
                      <td className="py-2 px-3 text-right text-blue-600 font-mono text-xs">
                        {r.confidence_interval_upper.toFixed(1)}
                      </td>
                      <td className="py-2 px-3 text-right text-text-muted font-mono text-xs">
                        ±{(range / 2).toFixed(1)}
                      </td>
                      <td className="py-2 px-3 text-center">
                        <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${
                          r.ci_method === 'conformal'
                            ? 'bg-green-50 text-green-700'
                            : 'bg-yellow-50 text-yellow-700'
                        }`}>
                          {r.ci_method === 'conformal' ? 'Conformal' : 'Gaussian'}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {!results.length && !error && (
        <div className="bg-white border border-border rounded-xl p-12 text-center">
          <Layers className="w-12 h-12 text-primary-200 mx-auto mb-3" />
          <p className="text-text-muted">Configure os parametros acima e execute o lote</p>
        </div>
      )}
    </div>
  );
}

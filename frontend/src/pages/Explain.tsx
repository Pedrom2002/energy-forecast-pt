import { useState } from 'react';
import { api, type EnergyData, type ExplanationResponse } from '../api/client';
import { Card, CardSkeleton } from '../components/Card';
import { toast } from '../components/Toast';
import { formatMW, formatPercent, exportCSV } from '../utils/format';
import WeatherForm from '../components/WeatherForm';
import { Brain, Zap, ArrowRight, AlertTriangle, Download } from 'lucide-react';
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

const CHART_COLORS = [
  '#1e40af', '#2563eb', '#3b82f6', '#60a5fa', '#93c5fd',
  '#1d4ed8', '#1e3a8a', '#2563eb', '#3b82f6', '#60a5fa',
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
  const [submitting, setSubmitting] = useState(false);

  const handleExplain = async () => {
    if (submitting) return;
    setSubmitting(true);
    setLoading(true);
    setError(null);
    try {
      const res = await api.predictExplain(data, topN);
      setResult(res);
      toast.success(`Explicacao gerada: ${res.top_features.length} features analisadas`);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Erro desconhecido';
      setError(msg);
      toast.error('Falha ao gerar explicacao');
    } finally {
      setLoading(false);
      setTimeout(() => setSubmitting(false), 1000);
    }
  };

  const handleExportCSV = () => {
    if (!result) return;
    exportCSV(
      `explain_${data.region}_${new Date().toISOString().slice(0, 10)}.csv`,
      ['rank', 'feature', 'importance_pct', 'value'],
      result.top_features.map((f) => [
        String(f.rank), f.feature,
        (f.importance * 100).toFixed(4),
        f.value.toFixed(6),
      ]),
    );
    toast.success('CSV exportado com sucesso');
  };

  const chartData = result?.top_features.map((f) => ({
    name: f.feature.length > 22 ? f.feature.slice(0, 20) + '...' : f.feature,
    fullName: f.feature,
    importance: +(f.importance * 100).toFixed(2),
    value: f.value,
    rank: f.rank,
  })) || [];

  // Sort columns
  const [sortCol, setSortCol] = useState<'rank' | 'importance' | 'value'>('rank');
  const [sortAsc, setSortAsc] = useState(true);

  const sortedFeatures = result ? [...result.top_features].sort((a, b) => {
    const diff = sortCol === 'rank' ? a.rank - b.rank
      : sortCol === 'importance' ? a.importance - b.importance
      : a.value - b.value;
    return sortAsc ? diff : -diff;
  }) : [];

  const handleSort = (col: typeof sortCol) => {
    if (sortCol === col) setSortAsc(!sortAsc);
    else { setSortCol(col); setSortAsc(col === 'rank'); }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text-primary tracking-tight">Explicabilidade</h1>
        <p className="text-sm text-text-secondary mt-1">
          Entenda quais features mais influenciam a previsao do modelo
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        <Card title="Parametros" className="lg:col-span-2">
          <WeatherForm data={data} onChange={setData} idPrefix="exp" />
          <div className="mt-4">
            <label htmlFor="exp-topn" className="block text-xs font-medium text-text-secondary mb-1.5">
              Top N Features
            </label>
            <input
              id="exp-topn"
              type="number"
              value={topN}
              onChange={(e) => setTopN(Math.min(30, Math.max(3, parseInt(e.target.value) || 5)))}
              min={3}
              max={30}
              aria-describedby="exp-topn-help"
              className="block w-full rounded-lg border border-border bg-surface px-3 min-h-[44px] text-sm shadow-xs tabular-nums
                focus-visible:border-primary-500 focus-visible:ring-2 focus-visible:ring-primary-200 focus-visible:outline-none transition"
            />
            <p id="exp-topn-help" className="text-[11px] text-text-muted mt-1">3 a 30 features</p>
          </div>
          <button
            type="button"
            onClick={handleExplain}
            disabled={loading || submitting}
            className="mt-6 w-full flex items-center justify-center gap-2 bg-primary-600 hover:bg-primary-700 disabled:bg-primary-300 disabled:cursor-not-allowed
              text-white font-medium min-h-[44px] px-4 rounded-lg transition-all duration-200 shadow-sm cursor-pointer
              focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2
              active:scale-[0.97]"
            aria-busy={loading}
          >
            {loading ? (
              <div className="animate-spin w-5 h-5 border-2 border-white/30 border-t-white rounded-full" role="status">
                <span className="sr-only">A analisar features...</span>
              </div>
            ) : (
              <>
                <Brain className="w-4 h-4" aria-hidden="true" />
                Explicar Previsao
                <ArrowRight className="w-4 h-4" aria-hidden="true" />
              </>
            )}
          </button>
        </Card>

        <div className="lg:col-span-3 space-y-4">
          {error && (
            <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-xl p-4 flex items-start gap-3 animate-fade-in-up" role="alert">
              <AlertTriangle className="w-5 h-5 text-red-500 shrink-0 mt-0.5" aria-hidden="true" />
              <div className="flex-1">
                <p className="text-sm font-medium text-red-800 dark:text-red-200">Erro na explicacao</p>
                <p className="text-sm text-red-600 dark:text-red-300 mt-0.5">{error}</p>
                <div className="flex gap-3 mt-3">
                  <button type="button" onClick={handleExplain} className="text-xs font-medium text-red-700 hover:text-red-900 underline cursor-pointer">
                    Tentar novamente
                  </button>
                  <a href="/monitoring" className="text-xs font-medium text-red-700 hover:text-red-900 underline">
                    Ver estado da API
                  </a>
                </div>
              </div>
            </div>
          )}

          {loading && (
            <div className="space-y-4 stagger-children" aria-busy="true">
              <CardSkeleton lines={2} />
              <CardSkeleton lines={6} />
            </div>
          )}

          {result && !loading && (
            <div className="space-y-4 stagger-children">
              <div className="bg-gradient-to-br from-purple-700 to-primary-800 rounded-xl p-6 text-white shadow-lg" aria-live="polite">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                  <div>
                    <p className="text-sm text-purple-200 flex items-center gap-1.5">
                      <Zap className="w-4 h-4" aria-hidden="true" /> Previsao
                    </p>
                    <p className="text-3xl font-bold mt-1 tabular-nums">
                      {formatMW(result.prediction.predicted_consumption_mw)}
                    </p>
                  </div>
                  <div className="text-sm text-purple-200 space-y-0.5">
                    <p>Metodo: <span className="text-white font-medium">{result.explanation_method}</span></p>
                    <p><span className="text-white font-medium tabular-nums">{result.total_features}</span> features totais</p>
                    <p>Top <span className="text-white font-medium tabular-nums">{result.top_features.length}</span> mostradas</p>
                  </div>
                </div>
              </div>

              <Card title="Importancia das Features" subtitle={`Metodo: ${result.explanation_method}`}>
                <p className="sr-only">
                  Grafico de barras mostrando as {chartData.length} features mais importantes.
                  A feature mais importante e {chartData[0]?.fullName} com {chartData[0]?.importance}% de importancia.
                </p>
                <div className="h-[320px] sm:h-[380px]" role="img" aria-label="Importancia das features do modelo">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={chartData} layout="vertical" margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" horizontal={false} />
                      <XAxis
                        type="number"
                        tick={{ fontSize: 10, fill: 'var(--color-text-muted)' }}
                        label={{ value: 'Importancia (%)', position: 'insideBottom', offset: -5, style: { fontSize: 11, fill: 'var(--color-text-muted)' } }}
                      />
                      <YAxis
                        type="category"
                        dataKey="name"
                        tick={{ fontSize: 11, fill: 'var(--color-text-secondary)' }}
                        width={typeof window !== 'undefined' && window.innerWidth < 640 ? 80 : 110}
                      />
                      <Tooltip
                        content={({ active, payload }) => {
                          if (!active || !payload?.length) return null;
                          const d = payload[0].payload;
                          return (
                            <div className="bg-surface border border-border rounded-lg p-3 shadow-lg text-xs">
                              <p className="font-semibold text-text-primary">{d.fullName}</p>
                              <p className="text-text-secondary mt-1">
                                Importancia: <span className="font-mono tabular-nums">{formatPercent(d.importance, 2)}</span>
                              </p>
                              <p className="text-text-secondary">
                                Valor: <span className="font-mono tabular-nums">{d.value.toFixed(4)}</span>
                              </p>
                              <p className="text-text-muted">Rank: #{d.rank}</p>
                            </div>
                          );
                        }}
                      />
                      <Bar dataKey="importance" radius={[0, 4, 4, 0]} maxBarSize={24}>
                        {chartData.map((_, idx) => (
                          <Cell key={idx} fill={CHART_COLORS[idx % CHART_COLORS.length]} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </Card>

              {/* Sortable feature table */}
              <Card
                title="Detalhes das Features"
                action={
                  <button
                    type="button"
                    onClick={handleExportCSV}
                    className="flex items-center gap-1.5 text-xs font-medium text-primary-600 hover:text-primary-800 hover:bg-primary-50 cursor-pointer
                      min-h-[36px] px-2 rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 transition-colors"
                    aria-label="Exportar features como CSV"
                  >
                    <Download className="w-3.5 h-3.5" aria-hidden="true" />
                    CSV
                  </button>
                }
              >
                <div className="overflow-x-auto -mx-5 sm:-mx-6 px-5 sm:px-6">
                  <table className="w-full text-sm" aria-label="Detalhes das features mais importantes">
                    <thead>
                      <tr className="border-b border-border">
                        <SortableHeader label="#" column="rank" current={sortCol} asc={sortAsc} onSort={handleSort} className="w-10 text-left" />
                        <th scope="col" className="text-left py-3 px-3 text-xs font-medium text-text-muted">Feature</th>
                        <SortableHeader label="Importancia" column="importance" current={sortCol} asc={sortAsc} onSort={handleSort} className="text-right" />
                        <SortableHeader label="Valor" column="value" current={sortCol} asc={sortAsc} onSort={handleSort} className="text-right hidden sm:table-cell" />
                      </tr>
                    </thead>
                    <tbody>
                      {sortedFeatures.map((f) => (
                        <tr key={f.rank} className="border-b border-border/50 hover:bg-surface-dim transition-colors">
                          <td className="py-2.5 px-3 text-text-muted tabular-nums">{f.rank}</td>
                          <td className="py-2.5 px-3 font-mono text-xs text-text-primary break-all">{f.feature}</td>
                          <td className="py-2.5 px-3 text-right">
                            <div className="flex items-center justify-end gap-2">
                              <div className="w-16 h-2 bg-surface-bright rounded-full overflow-hidden" role="progressbar" aria-valuenow={+(f.importance * 100).toFixed(1)} aria-valuemin={0} aria-valuemax={100}>
                                <div className="h-full bg-primary-500 rounded-full transition-all duration-300" style={{ width: `${Math.min(100, f.importance * 100)}%` }} />
                              </div>
                              <span className="font-mono text-xs text-text-primary w-14 text-right tabular-nums">
                                {formatPercent(f.importance * 100)}
                              </span>
                            </div>
                          </td>
                          <td className="py-2.5 px-3 text-right font-mono text-xs text-text-secondary tabular-nums hidden sm:table-cell">
                            {f.value.toFixed(4)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Card>
            </div>
          )}

          {!result && !error && !loading && (
            <div className="bg-surface border border-border rounded-xl p-12 text-center">
              <div className="w-16 h-16 rounded-2xl bg-purple-50 flex items-center justify-center mx-auto mb-4">
                <Brain className="w-8 h-8 text-purple-300" aria-hidden="true" />
              </div>
              <p className="text-sm font-medium text-text-secondary">Pronto para analisar</p>
              <p className="text-xs text-text-muted mt-1.5 max-w-xs mx-auto">
                Preencha os parametros e clique em "Explicar Previsao" para ver a importancia de cada feature
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/** Sortable table header — rule: sortable-table with aria-sort */
function SortableHeader({ label, column, current, asc, onSort, className = '' }: {
  label: string; column: string; current: string; asc: boolean; onSort: (col: never) => void; className?: string;
}) {
  const isActive = current === column;
  return (
    <th
      scope="col"
      className={`py-3 px-3 text-xs font-medium text-text-muted ${className}`}
      aria-sort={isActive ? (asc ? 'ascending' : 'descending') : 'none'}
    >
      <button
        type="button"
        onClick={() => onSort(column as never)}
        className="flex items-center gap-1 cursor-pointer hover:text-text-primary transition"
      >
        {label}
        {isActive && <span className="text-[10px]">{asc ? '↑' : '↓'}</span>}
      </button>
    </th>
  );
}

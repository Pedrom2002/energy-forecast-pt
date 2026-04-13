import { useState } from 'react';
import { api, type EnergyData, type PredictionResponse, REGIONS, type Region } from '../api/client';
import { Card } from '../components/Card';
import { ChartSkeleton } from '../components/ChartSkeleton';
import { toast } from '../components/Toast';
import { EmptyState } from '../components/EmptyState';
import { ForecastIllustration } from '../components/illustrations/ForecastIllustration';
import { useDocumentTitle } from '../hooks/useDocumentTitle';
import { formatMW, formatNumber, formatDateShort, exportCSV } from '../utils/format';
import { Play, AlertTriangle, Info, Download, HelpCircle } from 'lucide-react';
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
      temperature: +(15 + 8 * Math.sin(((hour - 6) / 24) * Math.PI * 2) + (Math.random() - 0.5) * 2).toFixed(1),
      humidity: +(65 + 15 * Math.cos(((hour - 14) / 24) * Math.PI * 2)).toFixed(1),
      wind_speed: +(10 + Math.random() * 8).toFixed(1),
      precipitation: +(Math.random() < 0.1 ? Math.random() * 3 : 0).toFixed(1),
      cloud_cover: +(40 + Math.random() * 30).toFixed(1),
      pressure: +(1010 + Math.random() * 8).toFixed(1),
      consumption_mw: +(baseConsumption + (Math.random() - 0.5) * 200).toFixed(1),
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
      temperature: +(15 + 8 * Math.sin(((hour - 6) / 24) * Math.PI * 2) + (Math.random() - 0.5) * 3).toFixed(1),
      humidity: +(65 + 15 * Math.cos(((hour - 14) / 24) * Math.PI * 2)).toFixed(1),
      wind_speed: +(10 + Math.random() * 10).toFixed(1),
      precipitation: +(Math.random() < 0.15 ? Math.random() * 5 : 0).toFixed(1),
      cloud_cover: +(40 + Math.random() * 30).toFixed(1),
      pressure: +(1010 + Math.random() * 10).toFixed(1),
    });
  }
  return items;
}

export default function Forecast() {
  useDocumentTitle('Forecast');
  const [region, setRegion] = useState<Region>('Lisboa');
  const [historyHours, setHistoryHours] = useState(72);
  const [forecastHours, setForecastHours] = useState(24);
  const [results, setResults] = useState<PredictionResponse[]>([]);
  const [historyData, setHistoryData] = useState<{ timestamp: string; consumption_mw: number }[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [modelName, setModelName] = useState('');
  const [submitting, setSubmitting] = useState(false);
  // Interactive legend state
  const [visibleSeries, setVisibleSeries] = useState({ actual: true, predicted: true, ci: true });
  const [showTable, setShowTable] = useState(false);

  const handleForecast = async () => {
    if (submitting) return; // debounce
    setSubmitting(true);
    setLoading(true);
    setError(null);
    try {
      const history = generateHistory(region, historyHours);
      const forecast = generateForecastItems(region, forecastHours);
      const res = await api.predictSequential(history, forecast);
      setResults(res.predictions);
      setHistoryData(history.map((h) => ({ timestamp: h.timestamp, consumption_mw: h.consumption_mw })));
      setModelName(res.model_name);
      toast.success(`Forecast gerado: ${res.predictions.length} previsoes para ${region}`);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Erro desconhecido';
      setError(msg);
      toast.error('Falha ao gerar forecast');
    } finally {
      setLoading(false);
      setTimeout(() => setSubmitting(false), 1000); // 1s debounce
    }
  };

  const handleExportCSV = () => {
    if (!results.length) return;
    exportCSV(
      `forecast_${region}_${new Date().toISOString().slice(0, 10)}.csv`,
      ['timestamp', 'region', 'predicted_mw', 'ci_lower', 'ci_upper', 'model', 'ci_method'],
      results.map((r) => [
        r.timestamp, r.region,
        r.predicted_consumption_mw.toFixed(2),
        r.confidence_interval_lower.toFixed(2),
        r.confidence_interval_upper.toFixed(2),
        r.model_name, r.ci_method,
      ]),
    );
    toast.success('CSV exportado com sucesso');
  };

  const chartData = [
    ...historyData.map((h) => ({
      time: formatDateShort(h.timestamp),
      actual: h.consumption_mw,
      predicted: null as number | null,
      ciUpper: null as number | null,
      ciLower: null as number | null,
    })),
    ...results.map((r) => ({
      time: formatDateShort(r.timestamp),
      actual: null as number | null,
      predicted: r.predicted_consumption_mw,
      ciUpper: r.confidence_interval_upper,
      ciLower: r.confidence_interval_lower,
    })),
  ];

  const nowLabel = historyData.length > 0
    ? formatDateShort(historyData[historyData.length - 1].timestamp)
    : '';

  const toggleSeries = (key: keyof typeof visibleSeries) => {
    setVisibleSeries((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text-primary tracking-tight">Forecast Sequencial</h1>
        <p className="text-sm text-text-secondary mt-1">
          Previsão lag-aware autoregressiva com histórico e intervalos de confiança
        </p>
      </div>

      <Card title="Configuração">
        <form onSubmit={(e) => { e.preventDefault(); handleForecast(); }} className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <div>
            <label htmlFor="fc-region" className="block text-xs font-medium text-text-secondary mb-1.5">Região</label>
            <select
              id="fc-region"
              value={region}
              onChange={(e) => setRegion(e.target.value as Region)}
              className="block w-full rounded-lg border border-border bg-surface px-3 min-h-[44px] text-sm shadow-xs cursor-pointer
                focus-visible:border-primary-500 focus-visible:ring-2 focus-visible:ring-primary-200 focus-visible:outline-none transition"
            >
              {REGIONS.map((r) => (
                <option key={r} value={r}>{r}</option>
              ))}
            </select>
          </div>
          <ValidatedNumberInput
            id="fc-history"
            label="Histórico (horas)"
            value={historyHours}
            onChange={setHistoryHours}
            min={48}
            max={336}
            help="Min. 48h (lags)"
          />
          <ValidatedNumberInput
            id="fc-forecast"
            label="Previsão (horas)"
            value={forecastHours}
            onChange={setForecastHours}
            min={1}
            max={168}
            help="Max. 168h (1 semana)"
          />
          <div>
            <span aria-hidden="true" className="block text-xs font-medium mb-1.5">&nbsp;</span>
            <button
              type="submit"
              disabled={loading || submitting}
              className="w-full flex items-center justify-center gap-2 bg-primary-600 hover:bg-primary-700 disabled:bg-primary-300 disabled:cursor-not-allowed
                text-white font-medium min-h-[44px] px-4 rounded-lg transition-all duration-200 shadow-sm cursor-pointer
                focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2
                active:scale-[0.97]"
              aria-busy={loading}
            >
              {loading ? (
                <div className="animate-spin w-5 h-5 border-2 border-white/30 border-t-white rounded-full" role="status">
                  <span className="sr-only">A gerar forecast...</span>
                </div>
              ) : (
                <>
                  <Play className="w-4 h-4" aria-hidden="true" />
                  Executar
                </>
              )}
            </button>
          </div>
        </form>

        <div className="flex items-start gap-2 mt-4 p-3 bg-primary-50 rounded-lg text-xs text-primary-700">
          <Info className="w-4 h-4 shrink-0 mt-0.5" aria-hidden="true" />
          <p>Dados meteorologicos simulados para demonstracao. Em produção, integre com dados reais de estacoes meteorologicas.</p>
        </div>
      </Card>

      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-xl p-4 flex items-start gap-3 animate-fade-in-up" role="alert">
          <AlertTriangle className="w-5 h-5 text-red-500 shrink-0 mt-0.5" aria-hidden="true" />
          <div className="flex-1">
            <p className="text-sm font-medium text-red-800 dark:text-red-200">Erro no forecast</p>
            <p className="text-sm text-red-600 dark:text-red-300 mt-0.5">{error}</p>
            <div className="flex gap-3 mt-3">
              <button
                type="button"
                onClick={handleForecast}
                className="text-xs font-medium text-red-700 hover:text-red-900 underline cursor-pointer"
              >
                Tentar novamente
              </button>
              <button
                type="button"
                onClick={() => { setForecastHours(12); setHistoryHours(48); }}
                className="text-xs font-medium text-red-700 hover:text-red-900 underline cursor-pointer"
              >
                Reduzir parametros
              </button>
              <a
                href="/monitoring"
                className="text-xs font-medium text-red-700 hover:text-red-900 underline"
              >
                Ver estado da API
              </a>
            </div>
          </div>
        </div>
      )}

      {loading && <ChartSkeleton height={380} />}

      {chartData.length > 0 && !loading && (
        <div className="animate-fade-in-up shadow-lg rounded-[var(--radius-lg)]">
        <Card
          title="Gráfico de Previsão"
          subtitle={`Modelo: ${modelName} | Região: ${region}`}
          action={
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setShowTable(!showTable)}
                className="flex items-center gap-1.5 text-xs font-medium text-text-muted hover:text-text-primary cursor-pointer
                  min-h-[36px] px-2 rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 transition-colors"
                aria-label={showTable ? 'Mostrar grafico' : 'Mostrar tabela de dados'}
              >
                <HelpCircle className="w-3.5 h-3.5" aria-hidden="true" />
                {showTable ? 'Gráfico' : 'Tabela'}
              </button>
              <button
                type="button"
                onClick={handleExportCSV}
                className="flex items-center gap-1.5 text-xs font-medium text-primary-600 hover:text-primary-800 hover:bg-primary-50 cursor-pointer
                  min-h-[36px] px-2 rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 transition-colors"
                aria-label="Exportar forecast como CSV"
              >
                <Download className="w-3.5 h-3.5" aria-hidden="true" />
                CSV
              </button>
            </div>
          }
        >
          <p className="sr-only">
            Gráfico de area mostrando {historyData.length} horas de histórico e {results.length} horas de previsão
            para a região {region}. Previsão media: {results.length > 0 ? formatNumber(results.reduce((s, r) => s + r.predicted_consumption_mw, 0) / results.length, 0) : 0} MW.
          </p>

          {showTable ? (
            /* Data table alternative — accessibility: data-table */
            <div className="overflow-x-auto -mx-5 sm:-mx-6 px-5 sm:px-6 max-h-[420px] overflow-y-auto">
              <table className="w-full text-sm" aria-label="Dados do forecast">
                <thead className="sticky top-0 bg-surface">
                  <tr className="border-b border-border">
                    <th scope="col" className="text-left py-2 px-3 text-xs font-medium text-text-muted">Hora</th>
                    <th scope="col" className="text-right py-2 px-3 text-xs font-medium text-text-muted">Consumo Real</th>
                    <th scope="col" className="text-right py-2 px-3 text-xs font-medium text-text-muted">Previsão</th>
                    <th scope="col" className="text-right py-2 px-3 text-xs font-medium text-text-muted hidden sm:table-cell">CI Inferior</th>
                    <th scope="col" className="text-right py-2 px-3 text-xs font-medium text-text-muted hidden sm:table-cell">CI Superior</th>
                  </tr>
                </thead>
                <tbody>
                  {chartData.map((d, i) => (
                    <tr key={i} className="border-b border-border/30 hover:bg-surface-dim transition-colors">
                      <td className="py-1.5 px-3 font-mono text-xs text-text-secondary tabular-nums">{d.time}</td>
                      <td className="py-1.5 px-3 text-right text-xs tabular-nums text-energy-green font-medium">{d.actual != null ? formatMW(d.actual) : '—'}</td>
                      <td className="py-1.5 px-3 text-right text-xs tabular-nums text-primary-600 font-medium">{d.predicted != null ? formatMW(d.predicted) : '—'}</td>
                      <td className="py-1.5 px-3 text-right text-xs tabular-nums text-text-muted hidden sm:table-cell">{d.ciLower != null ? formatMW(d.ciLower) : '—'}</td>
                      <td className="py-1.5 px-3 text-right text-xs tabular-nums text-text-muted hidden sm:table-cell">{d.ciUpper != null ? formatMW(d.ciUpper) : '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <>
              <div className="h-[350px] sm:h-[420px]" role="img" aria-label="Gráfico de previsão de consumo energetico">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                    <defs>
                      <linearGradient id="ciGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#fde68a" stopOpacity={0.45} />
                        <stop offset="95%" stopColor="#fde68a" stopOpacity={0.08} />
                      </linearGradient>
                      <linearGradient id="actualGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#16a34a" stopOpacity={0.15} />
                        <stop offset="95%" stopColor="#16a34a" stopOpacity={0} />
                      </linearGradient>
                      {/* Pattern for colorblind — rule: pattern-texture */}
                      <pattern id="ciPattern" patternUnits="userSpaceOnUse" width="6" height="6">
                        <path d="M0,6 L6,0" stroke="#f97316" strokeWidth="0.5" opacity="0.3" />
                      </pattern>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(100,116,139,0.25)" />
                    <XAxis
                      dataKey="time"
                      tick={{ fontSize: 10, fill: '#475569' }}
                      interval="preserveStartEnd"
                      tickCount={typeof window !== 'undefined' && window.innerWidth < 640 ? 4 : 8}
                    />
                    <YAxis
                      tick={{ fontSize: 10, fill: '#475569' }}
                      label={{ value: 'MW', position: 'insideTopLeft', offset: 10, style: { fontSize: 12, fill: 'var(--color-text-secondary)' } }}
                      width={50}
                      tickFormatter={(v: number) => formatNumber(v, 0)}
                    />
                    <Tooltip
                      contentStyle={{
                        borderRadius: '8px',
                        border: '1px solid var(--color-border)',
                        fontSize: '12px',
                        boxShadow: '0 4px 6px -1px rgba(0,0,0,.1)',
                        padding: '8px 12px',
                        backgroundColor: 'var(--color-surface)',
                        color: 'var(--color-text-primary)',
                      }}
                      formatter={(value: number, name: string) => [
                        formatMW(value),
                        name === 'actual' ? 'Consumo Real' : name === 'predicted' ? 'Previsão' : name,
                      ]}
                    />
                    {nowLabel && (
                      <ReferenceLine x={nowLabel} stroke="var(--color-accent)" strokeDasharray="4 4" label={{ value: 'Agora ➤', position: 'top', fill: 'var(--color-accent)', fontSize: 12, fontWeight: 600 }} />
                    )}
                    {visibleSeries.ci && (
                      <>
                        <Area type="monotone" dataKey="ciUpper" stroke="none" fill="url(#ciGrad)" name="CI Superior" />
                        <Area type="monotone" dataKey="ciLower" stroke="none" fill="transparent" name="CI Inferior" />
                      </>
                    )}
                    {visibleSeries.actual && (
                      <Area type="monotone" dataKey="actual" stroke="#16a34a" fill="url(#actualGrad)" strokeWidth={2} name="actual" dot={false} connectNulls={false} />
                    )}
                    {visibleSeries.predicted && (
                      <Area type="monotone" dataKey="predicted" stroke="#d97706" fill="none" strokeWidth={2} strokeDasharray="6 3" name="predicted" dot={false} connectNulls={false} />
                    )}
                  </AreaChart>
                </ResponsiveContainer>
              </div>

              {/* Interactive legend — rule: legend-interactive */}
              <div className="flex flex-wrap items-center justify-center gap-2 mt-4 text-xs font-medium text-text-secondary">
                <button
                  type="button"
                  onClick={() => toggleSeries('actual')}
                  className={`flex items-center gap-2 px-2 py-1 rounded cursor-pointer transition-all ${visibleSeries.actual ? 'bg-primary-50 text-primary-700' : 'opacity-40 line-through'}`}
                  aria-pressed={visibleSeries.actual}
                  aria-label="Toggle consumo real"
                >
                  <span className="w-4 h-0.5 bg-energy-green rounded" aria-hidden="true" />
                  Consumo Real
                </button>
                <button
                  type="button"
                  onClick={() => toggleSeries('predicted')}
                  className={`flex items-center gap-2 px-2 py-1 rounded cursor-pointer transition-all ${visibleSeries.predicted ? 'bg-primary-50 text-primary-700' : 'opacity-40 line-through'}`}
                  aria-pressed={visibleSeries.predicted}
                  aria-label="Toggle previsão"
                >
                  <span className="w-4 h-0.5 rounded" style={{ borderTop: '2px dashed #d97706' }} aria-hidden="true" />
                  Previsão
                </button>
                <button
                  type="button"
                  onClick={() => toggleSeries('ci')}
                  className={`flex items-center gap-2 px-2 py-1 rounded cursor-pointer transition-all ${visibleSeries.ci ? 'bg-primary-50 text-primary-700' : 'opacity-40 line-through'}`}
                  aria-pressed={visibleSeries.ci}
                  aria-label="Toggle intervalo de confianca"
                >
                  <span className="w-4 h-3 bg-primary-200 rounded" aria-hidden="true" />
                  IC 90%
                </button>
              </div>
            </>
          )}
        </Card>
        </div>
      )}

      {chartData.length === 0 && !error && !loading && (
        <div className="bg-surface border border-border rounded-xl">
          <EmptyState
            illustration={<ForecastIllustration />}
            title="Nenhum forecast gerado"
            description="Configure os parâmetros acima e clique em Executar para gerar previsões sequenciais."
          />
        </div>
      )}
    </div>
  );
}

/** Validated number input with blur validation — rule: inline-validation */
function ValidatedNumberInput({ id, label, value, onChange, min, max, help }: {
  id: string; label: string; value: number; onChange: (v: number) => void; min: number; max: number; help: string;
}) {
  const [error, setError] = useState('');
  const [local, setLocal] = useState(String(value));

  const handleBlur = () => {
    const n = parseInt(local) || min;
    if (n < min) {
      setError(`Minimo: ${min}`);
      onChange(min);
      setLocal(String(min));
    } else if (n > max) {
      setError(`Maximo: ${max}`);
      onChange(max);
      setLocal(String(max));
    } else {
      setError('');
      onChange(n);
    }
  };

  return (
    <div>
      <label htmlFor={id} className="block text-xs font-medium text-text-secondary mb-1.5">{label}</label>
      <input
        id={id}
        type="number"
        value={local}
        onChange={(e) => { setLocal(e.target.value); setError(''); }}
        onBlur={handleBlur}
        min={min}
        max={max}
        aria-describedby={`${id}-help`}
        aria-invalid={!!error}
        className={`block w-full rounded-lg border bg-surface px-3 min-h-[44px] text-sm shadow-xs tabular-nums
          focus-visible:ring-2 focus-visible:outline-none transition
          ${error ? 'border-energy-red focus-visible:border-energy-red focus-visible:ring-red-200' : 'border-border focus-visible:border-primary-500 focus-visible:ring-primary-200'}`}
      />
      {error ? (
        <p className="text-[11px] text-energy-red mt-1" role="alert">{error}</p>
      ) : (
        <p id={`${id}-help`} className="text-[11px] text-text-muted mt-1">{help}</p>
      )}
    </div>
  );
}

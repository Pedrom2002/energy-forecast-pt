import { useState, useMemo, useRef, useEffect, useCallback } from 'react';
import { api, type EnergyData, type PredictionResponse, REGIONS, type Region } from '../api/client';
import { Card, CardSkeleton } from '../components/Card';
import { toast } from '../components/Toast';
import { formatMW, formatNumber, exportCSV, formatDateShort } from '../utils/format';
import { useDocumentTitle } from '../hooks/useDocumentTitle';
import { EmptyState } from '../components/EmptyState';
import { BatchIllustration } from '../components/illustrations/BatchIllustration';
import { Play, Download, MapPin, AlertTriangle, ChevronDown, ChevronUp } from 'lucide-react';

function generateBatchItems(region: Region, startDate: string, hours: number): EnergyData[] {
  const items: EnergyData[] = [];
  const start = new Date(startDate);
  for (let i = 0; i < hours; i++) {
    const d = new Date(start.getTime() + i * 3600000);
    const hour = d.getHours();
    items.push({
      timestamp: d.toISOString().slice(0, 19),
      region,
      temperature: +(15 + 8 * Math.sin(((hour - 6) / 24) * Math.PI * 2) + (Math.random() - 0.5) * 3).toFixed(1),
      humidity: +(65 + 15 * Math.cos(((hour - 14) / 24) * Math.PI * 2) + (Math.random() - 0.5) * 10).toFixed(1),
      wind_speed: +(10 + Math.random() * 10).toFixed(1),
      precipitation: +(Math.random() < 0.15 ? Math.random() * 5 : 0).toFixed(1),
      cloud_cover: +(40 + Math.random() * 30).toFixed(1),
      pressure: +(1010 + Math.random() * 10).toFixed(1),
    });
  }
  return items;
}

const ROW_HEIGHT = 40;
const VISIBLE_ROWS = 15;
const BUFFER_ROWS = 5;

export default function Batch() {
  useDocumentTitle('Batch');
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
  const [sortCol, setSortCol] = useState<'time' | 'prediction' | 'amplitude'>('time');
  const [sortAsc, setSortAsc] = useState(true);
  const [submitting, setSubmitting] = useState(false);

  // Virtualization state
  const [scrollTop, setScrollTop] = useState(0);
  const scrollRef = useRef<HTMLDivElement>(null);

  const handleBatch = async () => {
    if (submitting) return;
    setSubmitting(true);
    setLoading(true);
    setError(null);
    try {
      const items = generateBatchItems(region, startDate, hours);
      const res = await api.predictBatch(items);
      setResults(res.predictions);
      toast.success(`Lote processado: ${res.predictions.length} previsoes geradas`);
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Erro desconhecido';
      setError(msg);
      toast.error('Falha no processamento do lote');
    } finally {
      setLoading(false);
      setTimeout(() => setSubmitting(false), 1000);
    }
  };

  const handleExportCSV = () => {
    if (!results.length) return;
    exportCSV(
      `batch_predictions_${region}_${new Date().toISOString().slice(0, 10)}.csv`,
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

  const handleSort = (col: typeof sortCol) => {
    if (sortCol === col) setSortAsc(!sortAsc);
    else { setSortCol(col); setSortAsc(col === 'time'); }
    setScrollTop(0);
    scrollRef.current?.scrollTo(0, 0);
  };

  const sortedResults = useMemo(() => {
    return [...results].sort((a, b) => {
      let diff: number;
      if (sortCol === 'time') diff = new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime();
      else if (sortCol === 'prediction') diff = a.predicted_consumption_mw - b.predicted_consumption_mw;
      else diff = (a.confidence_interval_upper - a.confidence_interval_lower) - (b.confidence_interval_upper - b.confidence_interval_lower);
      return sortAsc ? diff : -diff;
    });
  }, [results, sortCol, sortAsc]);

  const avgPrediction = results.length > 0
    ? results.reduce((s, r) => s + r.predicted_consumption_mw, 0) / results.length
    : 0;

  // Virtualization
  const useVirtualization = sortedResults.length > 50;
  const totalHeight = useVirtualization ? sortedResults.length * ROW_HEIGHT : 0;
  const startIdx = useVirtualization ? Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - BUFFER_ROWS) : 0;
  const endIdx = useVirtualization ? Math.min(sortedResults.length, startIdx + VISIBLE_ROWS + BUFFER_ROWS * 2) : sortedResults.length;
  const visibleRows = sortedResults.slice(startIdx, endIdx);
  const offsetY = startIdx * ROW_HEIGHT;

  const handleScroll = useCallback(() => {
    if (scrollRef.current) setScrollTop(scrollRef.current.scrollTop);
  }, []);

  useEffect(() => {
    const el = scrollRef.current;
    if (el && useVirtualization) {
      el.addEventListener('scroll', handleScroll, { passive: true });
      return () => el.removeEventListener('scroll', handleScroll);
    }
  }, [handleScroll, useVirtualization]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text-primary tracking-tight">Previsão em Lote</h1>
        <p className="text-sm text-text-secondary mt-1">
          Gere previsoes para multiplas horas de uma so vez (ate 1000 itens)
        </p>
      </div>

      <Card title="Configuração do Lote">
        <form onSubmit={(e) => { e.preventDefault(); handleBatch(); }} className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <div>
            <label htmlFor="batch-region" className="flex items-center gap-1.5 text-xs font-medium text-text-secondary mb-1.5">
              <MapPin className="w-3.5 h-3.5" aria-hidden="true" /> Região
            </label>
            <select
              id="batch-region"
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
          <div>
            <label htmlFor="batch-start" className="block text-xs font-medium text-text-secondary mb-1.5">Data Inicio</label>
            <input
              id="batch-start"
              type="datetime-local"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="block w-full rounded-lg border border-border bg-surface px-3 min-h-[44px] text-sm shadow-xs cursor-pointer
                focus-visible:border-primary-500 focus-visible:ring-2 focus-visible:ring-primary-200 focus-visible:outline-none transition"
            />
          </div>
          <div>
            <label htmlFor="batch-hours" className="block text-xs font-medium text-text-secondary mb-1.5">Horas</label>
            <input
              id="batch-hours"
              type="number"
              value={hours}
              onChange={(e) => setHours(Math.min(168, Math.max(1, parseInt(e.target.value) || 1)))}
              min={1}
              max={168}
              aria-describedby="batch-hours-help"
              className="block w-full rounded-lg border border-border bg-surface px-3 min-h-[44px] text-sm shadow-xs tabular-nums
                focus-visible:border-primary-500 focus-visible:ring-2 focus-visible:ring-primary-200 focus-visible:outline-none transition"
            />
            <p id="batch-hours-help" className="text-[11px] text-text-muted mt-1">1 a 168 (1 semana)</p>
          </div>
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
                  <span className="sr-only">A processar lote...</span>
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
      </Card>

      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-xl p-4 flex items-start gap-3 animate-fade-in-up" role="alert">
          <AlertTriangle className="w-5 h-5 text-red-500 shrink-0 mt-0.5" aria-hidden="true" />
          <div className="flex-1">
            <p className="text-sm font-medium text-red-800 dark:text-red-200">Erro no processamento</p>
            <p className="text-sm text-red-600 dark:text-red-300 mt-0.5">{error}</p>
            <div className="flex gap-3 mt-3">
              <button type="button" onClick={handleBatch} className="text-xs font-medium text-red-700 hover:text-red-900 underline cursor-pointer">Tentar novamente</button>
              <button type="button" onClick={() => setHours(Math.max(1, Math.floor(hours / 2)))} className="text-xs font-medium text-red-700 hover:text-red-900 underline cursor-pointer">Reduzir horas</button>
              <a href="/monitoring" className="text-xs font-medium text-red-700 hover:text-red-900 underline">Ver estado da API</a>
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

      {results.length > 0 && !loading && (
        <div className="space-y-4 stagger-children">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            <div className="bg-surface border border-border rounded-xl p-4 hover:shadow-md transition-shadow">
              <p className="text-xs text-text-muted">Total Previsoes</p>
              <p className="text-xl font-bold text-text-primary tabular-nums">{formatNumber(results.length, 0)}</p>
            </div>
            <div className="bg-surface border border-border rounded-xl p-4 hover:shadow-md transition-shadow">
              <p className="text-xs text-text-muted">Media</p>
              <p className="text-xl font-bold text-primary-700 tabular-nums">{formatMW(avgPrediction)}</p>
            </div>
            <div className="bg-surface border border-border rounded-xl p-4 hover:shadow-md transition-shadow">
              <p className="text-xs text-text-muted">Min</p>
              <p className="text-xl font-bold text-energy-blue tabular-nums">
                {formatMW(Math.min(...results.map((r) => r.predicted_consumption_mw)))}
              </p>
            </div>
            <div className="bg-surface border border-border rounded-xl p-4 hover:shadow-md transition-shadow">
              <p className="text-xs text-text-muted">Max</p>
              <p className="text-xl font-bold text-energy-blue tabular-nums">
                {formatMW(Math.max(...results.map((r) => r.predicted_consumption_mw)))}
              </p>
            </div>
          </div>

          <Card
            title={`Resultados — ${formatNumber(results.length, 0)} previsoes`}
            action={
              <button
                type="button"
                onClick={handleExportCSV}
                className="flex items-center gap-1.5 text-xs font-medium text-primary-600 hover:text-primary-800 hover:bg-primary-50 cursor-pointer
                  min-h-[44px] px-3 rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 transition-colors"
                aria-label="Exportar resultados como CSV"
              >
                <Download className="w-3.5 h-3.5" aria-hidden="true" />
                Exportar CSV
              </button>
            }
          >
            {/* Virtualized / normal table */}
            <div
              ref={scrollRef}
              className="overflow-x-auto -mx-5 sm:-mx-6 px-5 sm:px-6"
              style={useVirtualization ? { maxHeight: VISIBLE_ROWS * ROW_HEIGHT + 44, overflowY: 'auto' } : undefined}
            >
              <table className="w-full text-sm" aria-label="Resultados das previsoes em lote">
                <thead className="sticky top-0 bg-surface z-10">
                  <tr className="border-b border-border">
                    <th className="text-left py-3 px-3 text-xs font-medium text-text-muted" aria-sort={sortCol === 'time' ? (sortAsc ? 'ascending' : 'descending') : 'none'}>
                      <button type="button" onClick={() => handleSort('time')} className="flex items-center gap-1 cursor-pointer hover:text-text-primary transition">
                        Hora {sortCol === 'time' && (sortAsc ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />)}
                      </button>
                    </th>
                    <th className="text-right py-3 px-3 text-xs font-medium text-text-muted" aria-sort={sortCol === 'prediction' ? (sortAsc ? 'ascending' : 'descending') : 'none'}>
                      <button type="button" onClick={() => handleSort('prediction')} className="flex items-center gap-1 justify-end cursor-pointer hover:text-text-primary transition ml-auto">
                        Previsão {sortCol === 'prediction' && (sortAsc ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />)}
                      </button>
                    </th>
                    <th className="text-right py-3 px-3 text-xs font-medium text-text-muted hidden sm:table-cell">CI Inferior</th>
                    <th className="text-right py-3 px-3 text-xs font-medium text-text-muted hidden sm:table-cell">CI Superior</th>
                    <th className="text-right py-3 px-3 text-xs font-medium text-text-muted" aria-sort={sortCol === 'amplitude' ? (sortAsc ? 'ascending' : 'descending') : 'none'}>
                      <button type="button" onClick={() => handleSort('amplitude')} className="flex items-center gap-1 justify-end cursor-pointer hover:text-text-primary transition ml-auto">
                        Amplitude {sortCol === 'amplitude' && (sortAsc ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />)}
                      </button>
                    </th>
                    <th className="text-center py-3 px-3 text-xs font-medium text-text-muted hidden md:table-cell">Metodo</th>
                  </tr>
                </thead>
                <tbody>
                  {useVirtualization && <tr style={{ height: offsetY }} aria-hidden="true"><td /></tr>}
                  {visibleRows.map((r, i) => {
                    const range = r.confidence_interval_upper - r.confidence_interval_lower;
                    return (
                      <tr key={startIdx + i} className="border-b border-border/50 hover:bg-surface-dim transition-colors" style={useVirtualization ? { height: ROW_HEIGHT } : undefined}>
                        <td className="py-2.5 px-3 text-text-secondary font-mono text-xs tabular-nums">
                          {formatDateShort(r.timestamp)}
                        </td>
                        <td className="py-2.5 px-3 text-right font-semibold text-text-primary tabular-nums">
                          {formatMW(r.predicted_consumption_mw)}
                        </td>
                        <td className="py-2.5 px-3 text-right text-energy-blue font-mono text-xs tabular-nums hidden sm:table-cell">
                          {formatMW(r.confidence_interval_lower)}
                        </td>
                        <td className="py-2.5 px-3 text-right text-energy-blue font-mono text-xs tabular-nums hidden sm:table-cell">
                          {formatMW(r.confidence_interval_upper)}
                        </td>
                        <td className="py-2.5 px-3 text-right text-text-muted font-mono text-xs tabular-nums">
                          +/-{formatNumber(range / 2)}
                        </td>
                        <td className="py-2.5 px-3 text-center hidden md:table-cell">
                          <span className={`text-[10px] font-medium px-2 py-0.5 rounded-full ${
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
                  {useVirtualization && <tr style={{ height: Math.max(0, totalHeight - offsetY - visibleRows.length * ROW_HEIGHT) }} aria-hidden="true"><td /></tr>}
                </tbody>
              </table>
            </div>
            {useVirtualization && (
              <p className="text-[11px] text-text-muted text-center mt-2">
                A mostrar {visibleRows.length} de {formatNumber(sortedResults.length, 0)} resultados (tabela virtualizada)
              </p>
            )}
          </Card>
        </div>
      )}

      {!results.length && !error && !loading && (
        <EmptyState
          illustration={<BatchIllustration />}
          title="Nenhuma previsão gerada"
          description="Configure os parâmetros e clica em Executar para gerar previsões em massa."
        />
      )}
    </div>
  );
}

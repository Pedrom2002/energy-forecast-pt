import { useState, useMemo, useRef, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { type EnergyData, type PredictionResponse, REGIONS, type Region } from '../api/client';
import { useBatchMutation } from '../api/hooks';
import { Card } from '../components/Card';
import { ChartSkeleton } from '../components/ChartSkeleton';
import { toast } from '../components/Toast';
import { EmptyState } from '../components/EmptyState';
import { ExplanationPanel } from '../components/ExplanationPanel';
import { ForecastIllustration } from '../components/illustrations/ForecastIllustration';
import { useDocumentTitle } from '../hooks/useDocumentTitle';
import { formatMW, formatNumber, formatDateShort, exportCSV } from '../utils/format';
import { Play, AlertTriangle, Info, Download, LineChart, Table as TableIcon, ChevronUp, ChevronDown } from 'lucide-react';
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
      temperature: +(15 + 8 * Math.sin(((hour - 9) / 24) * Math.PI * 2) + (Math.random() - 0.5) * 3).toFixed(1),
      humidity: +(65 + 15 * Math.cos(((hour - 9) / 24) * Math.PI * 2)).toFixed(1),
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

export default function Forecast() {
  const { t } = useTranslation();
  useDocumentTitle(t('forecast.title'));
  const [region, setRegion] = useState<Region>('Lisboa');
  const [forecastHours, setForecastHours] = useState(24);
  const [results, setResults] = useState<PredictionResponse[]>([]);
  const [historyData, setHistoryData] = useState<{ timestamp: string; consumption_mw: number }[]>([]);
  const [modelName, setModelName] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [explainWeather, setExplainWeather] = useState<EnergyData | null>(null);
  // Interactive legend state
  const [visibleSeries, setVisibleSeries] = useState({ actual: true, predicted: true, ci: true });
  const [view, setView] = useState<'chart' | 'table'>('chart');
  const [sortCol, setSortCol] = useState<'time' | 'prediction' | 'amplitude'>('time');
  const [sortAsc, setSortAsc] = useState(true);
  const [scrollTop, setScrollTop] = useState(0);
  const scrollRef = useRef<HTMLDivElement>(null);

  const batchMutation = useBatchMutation({
    onSuccess: (res, items) => {
      setResults(res.predictions);
      setExplainWeather(items[Math.floor(items.length / 2)] ?? null);
      setHistoryData([]); // no history shown — we don't have it
      setModelName(res.predictions[0]?.model_name ?? 'XGBoost (no lags)');
      toast.success(
        t('forecast.forecastGenerated', { count: res.predictions.length, region }),
      );
    },
    onError: () => {
      toast.error(t('forecast.forecastFailed'));
    },
  });
  const loading = batchMutation.isPending;
  const error = batchMutation.error
    ? batchMutation.error.message || t('common.unknownError')
    : null;

  const handleForecast = () => {
    if (submitting) return; // debounce
    setSubmitting(true);
    setExplainWeather(null);
    // Demo: only weather is synthesised. We deliberately use the no-lags
    // model because we have NO live consumption feed — synthesising lag
    // values would produce optically-precise but scientifically dishonest
    // output. The with-lags model (MAPE 1.44%) is exposed via
    // /predict/sequential for production deployments with a real feed.
    const items = generateForecastItems(region, forecastHours);
    batchMutation.mutate(items, {
      onSettled: () => {
        setTimeout(() => setSubmitting(false), 1000); // 1s debounce
      },
    });
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
    toast.success(t('forecast.csvExported'));
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

  // Virtualization (when >50 rows)
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
    if (el && useVirtualization && view === 'table') {
      el.addEventListener('scroll', handleScroll, { passive: true });
      return () => el.removeEventListener('scroll', handleScroll);
    }
  }, [handleScroll, useVirtualization, view]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-2xl sm:text-3xl font-semibold text-text-primary tracking-tight">
          {t('forecast.title')}
        </h1>
        <p className="text-sm text-text-secondary mt-1.5">
          {t('forecast.subtitle')}
        </p>
      </div>

      <Card title={t('forecast.config')}>
        <form onSubmit={(e) => { e.preventDefault(); handleForecast(); }} className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div>
            <label htmlFor="fc-region" className="block text-xs font-medium text-text-secondary mb-1.5">{t('predict.form.region')}</label>
            <select
              id="fc-region"
              value={region}
              onChange={(e) => setRegion(e.target.value as Region)}
              className="block w-full rounded-lg border border-border bg-surface-dim px-3 min-h-[44px] text-sm cursor-pointer
                hover:border-border-strong focus-visible:border-primary-400 focus-visible:ring-2 focus-visible:ring-primary-100 focus-visible:outline-none transition"
            >
              {REGIONS.map((r) => (
                <option key={r} value={r}>{r}</option>
              ))}
            </select>
          </div>
          <ValidatedNumberInput
            id="fc-forecast"
            label={t('forecast.hours')}
            value={forecastHours}
            onChange={setForecastHours}
            min={1}
            max={168}
            help={t('forecast.hoursHelp')}
          />
          <div>
            <span aria-hidden="true" className="block text-xs font-medium mb-1.5">&nbsp;</span>
            <button
              type="submit"
              disabled={loading || submitting}
              className="w-full flex items-center justify-center gap-2 bg-primary-500 hover:bg-primary-400 disabled:bg-primary-500/40 disabled:cursor-not-allowed
                text-[#05080f] font-semibold min-h-[44px] px-4 rounded-lg transition-all duration-200 cursor-pointer
                shadow-[0_0_18px_rgba(34,211,238,0.3)] hover:shadow-[0_0_24px_rgba(34,211,238,0.45)]
                focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-300 focus-visible:ring-offset-2 focus-visible:ring-offset-[#05080f]
                active:scale-[0.98]"
              aria-busy={loading}
            >
              {loading ? (
                <div className="animate-spin w-5 h-5 border-2 border-white/30 border-t-white rounded-full" role="status">
                  <span className="sr-only">{t('forecast.runningSr')}</span>
                </div>
              ) : (
                <>
                  <Play className="w-4 h-4" aria-hidden="true" />
                  {t('forecast.run')}
                </>
              )}
            </button>
          </div>
        </form>

        <div className="flex items-center gap-2.5 mt-4 px-3 py-2.5 rounded-lg border border-primary-400/20 bg-primary-500/[0.06] text-xs text-primary-300 leading-relaxed">
          <Info className="w-4 h-4 shrink-0" aria-hidden="true" />
          <p>{t('forecast.demoInfo')}</p>
        </div>
      </Card>

      {error && (
        <div className="rounded-xl border border-rose-500/25 bg-rose-500/[0.05] p-4 flex items-start gap-3 animate-fade-in-up" role="alert">
          <AlertTriangle className="w-5 h-5 text-energy-red shrink-0 mt-0.5" aria-hidden="true" />
          <div className="flex-1">
            <p className="text-sm font-medium text-rose-200">{t('forecast.errorTitle')}</p>
            <p className="text-sm text-rose-300/80 mt-0.5">{error}</p>
            <div className="flex gap-3 mt-3 flex-wrap">
              <button
                type="button"
                onClick={handleForecast}
                className="text-xs font-medium text-rose-200 hover:text-white underline cursor-pointer"
              >
                {t('common.retry')}
              </button>
              <button
                type="button"
                onClick={() => { setForecastHours(12); }}
                className="text-xs font-medium text-rose-200 hover:text-white underline cursor-pointer"
              >
                {t('forecast.reduceParams')}
              </button>
              <a
                href="/monitoring"
                className="text-xs font-medium text-rose-200 hover:text-white underline"
              >
                {t('forecast.seeApiStatus')}
              </a>
            </div>
          </div>
        </div>
      )}

      {loading && <ChartSkeleton height={380} />}

      {chartData.length > 0 && !loading && (
        <>
          {/* View toggle — segmented control */}
          <div
            role="radiogroup"
            aria-label={t('forecast.viewMode')}
            className="inline-flex items-center gap-1 p-1 rounded-lg border border-border bg-surface-dim"
          >
            <button
              type="button"
              role="radio"
              aria-checked={view === 'chart'}
              onClick={() => setView('chart')}
              className={`flex items-center gap-1.5 min-h-[36px] px-3 rounded-md text-xs font-mono font-medium uppercase tracking-wider cursor-pointer transition-colors
                focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-400
                ${view === 'chart' ? 'bg-primary-500/15 text-primary-300 ring-1 ring-primary-400/25' : 'text-text-muted hover:text-text-primary'}`}
            >
              <LineChart className="w-3.5 h-3.5" aria-hidden="true" />
              {t('forecast.chart')}
            </button>
            <button
              type="button"
              role="radio"
              aria-checked={view === 'table'}
              onClick={() => setView('table')}
              className={`flex items-center gap-1.5 min-h-[36px] px-3 rounded-md text-xs font-mono font-medium uppercase tracking-wider cursor-pointer transition-colors
                focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-400
                ${view === 'table' ? 'bg-primary-500/15 text-primary-300 ring-1 ring-primary-400/25' : 'text-text-muted hover:text-text-primary'}`}
            >
              <TableIcon className="w-3.5 h-3.5" aria-hidden="true" />
              {t('forecast.table')}
            </button>
          </div>

          {view === 'chart' && (
            <div className="animate-fade-in-up shadow-lg rounded-[var(--radius-lg)]">
              <Card
                title={t('forecast.chartTitle')}
                subtitle={t('forecast.chartSubtitle', { model: modelName, region })}
                action={
                  <button
                    type="button"
                    onClick={handleExportCSV}
                    className="flex items-center gap-1.5 text-xs font-mono font-medium uppercase tracking-wider text-primary-300 hover:text-primary-200 hover:bg-primary-500/10 cursor-pointer
                      min-h-[36px] px-2 rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 transition-colors"
                    aria-label={t('forecast.exportCsvAria')}
                  >
                    <Download className="w-3.5 h-3.5" aria-hidden="true" />
                    CSV
                  </button>
                }
              >
                <p className="sr-only">
                  {t('forecast.chartDescription', {
                    history: historyData.length,
                    forecast: results.length,
                    region,
                    avg: results.length > 0 ? formatNumber(results.reduce((s, r) => s + r.predicted_consumption_mw, 0) / results.length, 0) : 0,
                  })}
                </p>

                <div className="h-[350px] sm:h-[420px]" role="img" aria-label={t('forecast.chartAria')}>
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                      <defs>
                        <linearGradient id="ciGrad" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#22d3ee" stopOpacity={0.35} />
                          <stop offset="95%" stopColor="#22d3ee" stopOpacity={0.04} />
                        </linearGradient>
                        <linearGradient id="actualGrad" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="5%" stopColor="#10b981" stopOpacity={0.25} />
                          <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                      <XAxis
                        dataKey="time"
                        tick={{ fontSize: 10, fill: '#6b7a92', fontFamily: 'JetBrains Mono, monospace' }}
                        interval="preserveStartEnd"
                        tickCount={typeof window !== 'undefined' && window.innerWidth < 640 ? 4 : 8}
                        axisLine={{ stroke: 'rgba(255,255,255,0.1)' }}
                        tickLine={{ stroke: 'rgba(255,255,255,0.1)' }}
                      />
                      <YAxis
                        tick={{ fontSize: 10, fill: '#6b7a92', fontFamily: 'JetBrains Mono, monospace' }}
                        label={{ value: 'MW', position: 'insideTopLeft', offset: 10, style: { fontSize: 10, fill: '#6b7a92', fontFamily: 'JetBrains Mono, monospace' } }}
                        width={50}
                        tickFormatter={(v: number) => formatNumber(v, 0)}
                        axisLine={{ stroke: 'rgba(255,255,255,0.1)' }}
                        tickLine={{ stroke: 'rgba(255,255,255,0.1)' }}
                      />
                      <Tooltip
                        contentStyle={{
                          borderRadius: '8px',
                          border: '1px solid rgba(34,211,238,0.25)',
                          fontSize: '12px',
                          fontFamily: 'JetBrains Mono, monospace',
                          boxShadow: '0 8px 24px -8px rgba(0,0,0,0.6)',
                          padding: '8px 12px',
                          backgroundColor: 'rgba(11,16,32,0.95)',
                          color: '#f0f6fc',
                          backdropFilter: 'blur(12px)',
                        }}
                        formatter={(value, name) => [
                          typeof value === 'number' ? formatMW(value) : String(value),
                          name === 'actual' ? t('forecast.actualConsumption') : name === 'predicted' ? t('forecast.predictionSeries') : String(name),
                        ]}
                      />
                      {nowLabel && (
                        <ReferenceLine x={nowLabel} stroke="#fbbf24" strokeDasharray="4 4" label={{ value: `${t('forecast.now')} ➤`, position: 'top', fill: '#fbbf24', fontSize: 11, fontWeight: 600, fontFamily: 'JetBrains Mono, monospace' }} />
                      )}
                      {visibleSeries.ci && (
                        <>
                          <Area type="monotone" dataKey="ciUpper" stroke="none" fill="url(#ciGrad)" name={t('forecast.ciUpper')} />
                          <Area type="monotone" dataKey="ciLower" stroke="none" fill="transparent" name={t('forecast.ciLower')} />
                        </>
                      )}
                      {visibleSeries.actual && (
                        <Area type="monotone" dataKey="actual" stroke="#10b981" fill="url(#actualGrad)" strokeWidth={2} name="actual" dot={false} connectNulls={false} />
                      )}
                      {visibleSeries.predicted && (
                        <Area type="monotone" dataKey="predicted" stroke="#fbbf24" fill="none" strokeWidth={2} strokeDasharray="6 3" name="predicted" dot={false} connectNulls={false} />
                      )}
                    </AreaChart>
                  </ResponsiveContainer>
                </div>

                {/* Interactive legend */}
                <div className="flex flex-wrap items-center justify-center gap-2 mt-4 text-xs font-medium text-text-secondary">
                  <button
                    type="button"
                    onClick={() => toggleSeries('actual')}
                    className={`flex items-center gap-2 px-2 py-1 rounded cursor-pointer transition-all ${visibleSeries.actual ? 'bg-primary-500/10 text-primary-300 ring-1 ring-primary-400/20' : 'opacity-40 line-through'}`}
                    aria-pressed={visibleSeries.actual}
                    aria-label={t('forecast.toggleActual')}
                  >
                    <span className="w-4 h-0.5 bg-energy-green rounded" aria-hidden="true" />
                    {t('forecast.actualConsumption')}
                  </button>
                  <button
                    type="button"
                    onClick={() => toggleSeries('predicted')}
                    className={`flex items-center gap-2 px-2 py-1 rounded cursor-pointer transition-all ${visibleSeries.predicted ? 'bg-amber-500/10 text-accent-400 ring-1 ring-amber-400/20' : 'opacity-40 line-through'}`}
                    aria-pressed={visibleSeries.predicted}
                    aria-label={t('forecast.togglePredicted')}
                  >
                    <span className="w-4 h-0.5 rounded" style={{ borderTop: '2px dashed #fbbf24' }} aria-hidden="true" />
                    {t('forecast.predictionSeries')}
                  </button>
                  <button
                    type="button"
                    onClick={() => toggleSeries('ci')}
                    className={`flex items-center gap-2 px-2 py-1 rounded cursor-pointer transition-all ${visibleSeries.ci ? 'bg-primary-500/10 text-primary-300 ring-1 ring-primary-400/20' : 'opacity-40 line-through'}`}
                    aria-pressed={visibleSeries.ci}
                    aria-label={t('forecast.toggleCi')}
                  >
                    <span className="w-4 h-3 rounded bg-gradient-to-b from-primary-400/50 to-primary-500/10" aria-hidden="true" />
                    {t('forecast.ci90')}
                  </button>
                </div>
              </Card>
            </div>
          )}

          {view === 'table' && (
            <div className="animate-fade-in-up">
              <Card
                title={t('forecast.resultsTitle', { count: formatNumber(results.length, 0) })}
                subtitle={t('forecast.chartSubtitle', { model: modelName, region })}
                action={
                  <button
                    type="button"
                    onClick={handleExportCSV}
                    className="flex items-center gap-1.5 text-xs font-mono font-medium uppercase tracking-wider text-primary-300 hover:text-primary-200 hover:bg-primary-500/10 cursor-pointer
                      min-h-[44px] px-3 rounded-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 transition-colors"
                    aria-label={t('forecast.exportCsvAria')}
                  >
                    <Download className="w-3.5 h-3.5" aria-hidden="true" />
                    {t('forecast.exportCsv')}
                  </button>
                }
              >
                <div
                  ref={scrollRef}
                  className="overflow-x-auto -mx-5 sm:-mx-6 px-5 sm:px-6"
                  style={useVirtualization ? { maxHeight: VISIBLE_ROWS * ROW_HEIGHT + 44, overflowY: 'auto' } : undefined}
                >
                  <table className="w-full text-sm" aria-label={t('forecast.tableAria')}>
                    <thead className="sticky top-0 bg-surface z-10">
                      <tr className="border-b border-border">
                        <th className="text-left py-3 px-3 text-xs font-medium text-text-muted" aria-sort={sortCol === 'time' ? (sortAsc ? 'ascending' : 'descending') : 'none'}>
                          <button type="button" onClick={() => handleSort('time')} className="flex items-center gap-1 cursor-pointer hover:text-text-primary transition">
                            {t('forecast.colTime')} {sortCol === 'time' && (sortAsc ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />)}
                          </button>
                        </th>
                        <th className="text-right py-3 px-3 text-xs font-medium text-text-muted" aria-sort={sortCol === 'prediction' ? (sortAsc ? 'ascending' : 'descending') : 'none'}>
                          <button type="button" onClick={() => handleSort('prediction')} className="flex items-center gap-1 justify-end cursor-pointer hover:text-text-primary transition ml-auto">
                            {t('forecast.colPrediction')} {sortCol === 'prediction' && (sortAsc ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />)}
                          </button>
                        </th>
                        <th className="text-right py-3 px-3 text-xs font-medium text-text-muted hidden sm:table-cell">{t('forecast.colCiLower')}</th>
                        <th className="text-right py-3 px-3 text-xs font-medium text-text-muted hidden sm:table-cell">{t('forecast.colCiUpper')}</th>
                        <th className="text-right py-3 px-3 text-xs font-medium text-text-muted" aria-sort={sortCol === 'amplitude' ? (sortAsc ? 'ascending' : 'descending') : 'none'}>
                          <button type="button" onClick={() => handleSort('amplitude')} className="flex items-center gap-1 justify-end cursor-pointer hover:text-text-primary transition ml-auto">
                            {t('forecast.colAmplitude')} {sortCol === 'amplitude' && (sortAsc ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />)}
                          </button>
                        </th>
                        <th className="text-center py-3 px-3 text-xs font-medium text-text-muted hidden md:table-cell">{t('forecast.colMethod')}</th>
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
                              <span className={`text-[10px] font-mono font-medium uppercase tracking-wider px-2 py-0.5 rounded-full ring-1 ${
                                r.ci_method === 'conformal'
                                  ? 'bg-emerald-500/10 text-energy-green ring-emerald-400/20'
                                  : 'bg-yellow-500/10 text-energy-yellow ring-yellow-400/20'
                              }`}>
                                {r.ci_method === 'conformal' ? t('forecast.methodConformal') : t('forecast.methodGaussian')}
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
                    {t('forecast.virtualized', { shown: visibleRows.length, total: formatNumber(sortedResults.length, 0) })}
                  </p>
                )}
              </Card>
            </div>
          )}
        </>
      )}

      {explainWeather && results.length > 0 && !loading && (
        <Card title={t('forecast.explainTitle')} subtitle={t('forecast.explainSubtitle')}>
          <ExplanationPanel weather={explainWeather} />
        </Card>
      )}

      {chartData.length === 0 && !error && !loading && (
        <div className="glass-card">
          <EmptyState
            illustration={<ForecastIllustration />}
            title={t('forecast.emptyTitle')}
            description={t('forecast.emptyDescription')}
          />
        </div>
      )}
    </div>
  );
}

/** Validated number input with blur validation */
function ValidatedNumberInput({ id, label, value, onChange, min, max, help }: {
  id: string; label: string; value: number; onChange: (v: number) => void; min: number; max: number; help: string;
}) {
  const { t } = useTranslation();
  const [error, setError] = useState('');
  const [local, setLocal] = useState(String(value));

  const handleBlur = () => {
    const n = parseInt(local) || min;
    if (n < min) {
      setError(t('forecast.minError', { value: min }));
      onChange(min);
      setLocal(String(min));
    } else if (n > max) {
      setError(t('forecast.maxError', { value: max }));
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
        className={`block w-full rounded-lg border bg-surface-dim px-3 min-h-[44px] text-sm tabular-nums
          focus-visible:ring-2 focus-visible:outline-none transition
          ${error
            ? 'border-energy-red focus-visible:border-energy-red focus-visible:ring-rose-400/30'
            : 'border-border hover:border-border-strong focus-visible:border-primary-400 focus-visible:ring-primary-100'}`}
      />
      {error ? (
        <p className="text-[11px] text-energy-red mt-1" role="alert">{error}</p>
      ) : (
        <p id={`${id}-help`} className="text-[11px] text-text-muted mt-1">{help}</p>
      )}
    </div>
  );
}

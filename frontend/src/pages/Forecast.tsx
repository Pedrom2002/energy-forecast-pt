import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { REGIONS, type Region } from '../api/client';
import { Card } from '../components/Card';
import { ChartSkeleton } from '../components/ChartSkeleton';
import { EmptyState } from '../components/EmptyState';
import { ExplanationPanel } from '../components/ExplanationPanel';
import { ForecastChart } from '../components/forecast/ForecastChart';
import { ForecastTable } from '../components/forecast/ForecastTable';
import { ForecastIllustration } from '../components/illustrations/ForecastIllustration';
import { useDocumentTitle } from '../hooks/useDocumentTitle';
import { useForecastData } from '../hooks/useForecastData';
import { AlertTriangle, Info, LineChart, Play, Table as TableIcon } from 'lucide-react';

export default function Forecast() {
  const { t } = useTranslation();
  useDocumentTitle(t('forecast.title'));
  const [region, setRegion] = useState<Region>('Lisboa');
  const [forecastHours, setForecastHours] = useState(24);
  const [view, setView] = useState<'chart' | 'table'>('chart');

  const {
    results,
    modelName,
    explainWeather,
    loading,
    submitting,
    error,
    run,
    exportCsv,
  } = useForecastData(region, forecastHours);

  const hasResults = results.length > 0;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="font-display text-2xl sm:text-3xl font-semibold text-text-primary tracking-tight">
          {t('forecast.title')}
        </h1>
        <p className="text-sm text-text-secondary mt-1.5">{t('forecast.subtitle')}</p>
      </div>

      <Card title={t('forecast.config')}>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            run();
          }}
          className="grid grid-cols-1 sm:grid-cols-3 gap-4"
        >
          <div>
            <label
              htmlFor="fc-region"
              className="block text-xs font-medium text-text-secondary mb-1.5"
            >
              {t('predict.form.region')}
            </label>
            <select
              id="fc-region"
              value={region}
              onChange={(e) => setRegion(e.target.value as Region)}
              className="block w-full rounded-lg border border-border bg-surface-dim px-3 min-h-[44px] text-sm cursor-pointer
                hover:border-border-strong focus-visible:border-primary-400 focus-visible:ring-2 focus-visible:ring-primary-100 focus-visible:outline-none transition"
            >
              {REGIONS.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
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
              className="w-full flex items-center justify-center gap-2
                bg-primary-500 hover:bg-primary-400 disabled:bg-primary-500/40 disabled:cursor-not-allowed
                text-[#05080f] font-semibold min-h-[44px] px-4 rounded-lg transition-all duration-200 cursor-pointer
                shadow-[0_0_18px_rgba(34,211,238,0.3)] hover:shadow-[0_0_24px_rgba(34,211,238,0.45)]
                focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-300 focus-visible:ring-offset-2 focus-visible:ring-offset-[#05080f]
                active:scale-[0.98]"
              aria-busy={loading}
            >
              {loading ? (
                <div
                  className="animate-spin w-5 h-5 border-2 border-white/30 border-t-white rounded-full"
                  role="status"
                >
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
        <div
          className="rounded-xl border border-rose-500/25 bg-rose-500/[0.05] p-4 flex items-start gap-3 animate-fade-in-up"
          role="alert"
        >
          <AlertTriangle className="w-5 h-5 text-energy-red shrink-0 mt-0.5" aria-hidden="true" />
          <div className="flex-1">
            <p className="text-sm font-medium text-rose-200">{t('forecast.errorTitle')}</p>
            <p className="text-sm text-rose-300/80 mt-0.5">{error}</p>
            <div className="flex gap-3 mt-3 flex-wrap">
              <button
                type="button"
                onClick={run}
                className="text-xs font-medium text-rose-200 hover:text-white underline cursor-pointer"
              >
                {t('common.retry')}
              </button>
              <button
                type="button"
                onClick={() => setForecastHours(12)}
                className="text-xs font-medium text-rose-200 hover:text-white underline cursor-pointer"
              >
                {t('forecast.reduceParams')}
              </button>
              <a href="/monitoring" className="text-xs font-medium text-rose-200 hover:text-white underline">
                {t('forecast.seeApiStatus')}
              </a>
            </div>
          </div>
        </div>
      )}

      {loading && <ChartSkeleton height={380} />}

      {hasResults && !loading && (
        <>
          <div
            role="radiogroup"
            aria-label={t('forecast.viewMode')}
            className="inline-flex items-center gap-1 p-1 rounded-lg border border-border bg-surface-dim"
          >
            <ViewToggleButton
              active={view === 'chart'}
              onClick={() => setView('chart')}
              icon={<LineChart className="w-3.5 h-3.5" aria-hidden="true" />}
              label={t('forecast.chart')}
            />
            <ViewToggleButton
              active={view === 'table'}
              onClick={() => setView('table')}
              icon={<TableIcon className="w-3.5 h-3.5" aria-hidden="true" />}
              label={t('forecast.table')}
            />
          </div>

          {view === 'chart' && (
            <ForecastChart
              results={results}
              historyData={[]}
              modelName={modelName}
              region={region}
              onExport={exportCsv}
            />
          )}

          {view === 'table' && (
            <ForecastTable
              results={results}
              modelName={modelName}
              region={region}
              onExport={exportCsv}
            />
          )}
        </>
      )}

      {explainWeather && hasResults && !loading && (
        <Card title={t('forecast.explainTitle')} subtitle={t('forecast.explainSubtitle')}>
          <ExplanationPanel weather={explainWeather} />
        </Card>
      )}

      {!hasResults && !error && !loading && (
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

function ViewToggleButton({
  active,
  onClick,
  icon,
  label,
}: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
}) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={active}
      onClick={onClick}
      className={`flex items-center gap-1.5 min-h-[36px] px-3 rounded-md text-xs font-mono font-medium uppercase tracking-wider cursor-pointer transition-colors
        focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-400
        ${active ? 'bg-primary-500/15 text-primary-300 ring-1 ring-primary-400/25' : 'text-text-muted hover:text-text-primary'}`}
    >
      {icon}
      {label}
    </button>
  );
}

/** Validated number input with blur validation. */
function ValidatedNumberInput({
  id,
  label,
  value,
  onChange,
  min,
  max,
  help,
}: {
  id: string;
  label: string;
  value: number;
  onChange: (v: number) => void;
  min: number;
  max: number;
  help: string;
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
      <label htmlFor={id} className="block text-xs font-medium text-text-secondary mb-1.5">
        {label}
      </label>
      <input
        id={id}
        type="number"
        value={local}
        onChange={(e) => {
          setLocal(e.target.value);
          setError('');
        }}
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
        <p className="text-[11px] text-energy-red mt-1" role="alert">
          {error}
        </p>
      ) : (
        <p id={`${id}-help`} className="text-[11px] text-text-muted mt-1">
          {help}
        </p>
      )}
    </div>
  );
}

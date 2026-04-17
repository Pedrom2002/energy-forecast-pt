import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Area,
  AreaChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { Card } from '../Card';
import { Download } from 'lucide-react';
import { formatDateShort, formatMW, formatNumber } from '../../utils/format';
import type { PredictionResponse } from '../../api/client';

export interface ChartPoint {
  time: string;
  actual: number | null;
  predicted: number | null;
  ciUpper: number | null;
  ciLower: number | null;
}

export interface ForecastChartProps {
  results: PredictionResponse[];
  historyData: { timestamp: string; consumption_mw: number }[];
  modelName: string;
  region: string;
  onExport: () => void;
}

type VisibleSeries = { actual: boolean; predicted: boolean; ci: boolean };

export function ForecastChart({
  results,
  historyData,
  modelName,
  region,
  onExport,
}: ForecastChartProps) {
  const { t } = useTranslation();
  const [visibleSeries, setVisibleSeries] = useState<VisibleSeries>({
    actual: true,
    predicted: true,
    ci: true,
  });

  const chartData: ChartPoint[] = [
    ...historyData.map((h) => ({
      time: formatDateShort(h.timestamp),
      actual: h.consumption_mw,
      predicted: null,
      ciUpper: null,
      ciLower: null,
    })),
    ...results.map((r) => ({
      time: formatDateShort(r.timestamp),
      actual: null,
      predicted: r.predicted_consumption_mw,
      ciUpper: r.confidence_interval_upper,
      ciLower: r.confidence_interval_lower,
    })),
  ];

  const nowLabel =
    historyData.length > 0 ? formatDateShort(historyData[historyData.length - 1].timestamp) : '';

  const toggleSeries = (key: keyof VisibleSeries) => {
    setVisibleSeries((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const avg =
    results.length > 0
      ? results.reduce((s, r) => s + r.predicted_consumption_mw, 0) / results.length
      : 0;

  return (
    <div className="animate-fade-in-up shadow-lg rounded-[var(--radius-lg)]">
      <Card
        title={t('forecast.chartTitle')}
        subtitle={t('forecast.chartSubtitle', { model: modelName, region })}
        action={
          <button
            type="button"
            onClick={onExport}
            className="flex items-center gap-1.5 text-xs font-mono font-medium uppercase tracking-wider
              text-primary-300 hover:text-primary-200 hover:bg-primary-500/10 cursor-pointer
              min-h-[36px] px-2 rounded-lg
              focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 transition-colors"
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
            avg: formatNumber(avg, 0),
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
                label={{
                  value: 'MW',
                  position: 'insideTopLeft',
                  offset: 10,
                  style: {
                    fontSize: 10,
                    fill: '#6b7a92',
                    fontFamily: 'JetBrains Mono, monospace',
                  },
                }}
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
                  name === 'actual'
                    ? t('forecast.actualConsumption')
                    : name === 'predicted'
                      ? t('forecast.predictionSeries')
                      : String(name),
                ]}
              />
              {nowLabel && (
                <ReferenceLine
                  x={nowLabel}
                  stroke="#fbbf24"
                  strokeDasharray="4 4"
                  label={{
                    value: `${t('forecast.now')} ➤`,
                    position: 'top',
                    fill: '#fbbf24',
                    fontSize: 11,
                    fontWeight: 600,
                    fontFamily: 'JetBrains Mono, monospace',
                  }}
                />
              )}
              {visibleSeries.ci && (
                <>
                  <Area
                    type="monotone"
                    dataKey="ciUpper"
                    stroke="none"
                    fill="url(#ciGrad)"
                    name={t('forecast.ciUpper')}
                  />
                  <Area
                    type="monotone"
                    dataKey="ciLower"
                    stroke="none"
                    fill="transparent"
                    name={t('forecast.ciLower')}
                  />
                </>
              )}
              {visibleSeries.actual && (
                <Area
                  type="monotone"
                  dataKey="actual"
                  stroke="#10b981"
                  fill="url(#actualGrad)"
                  strokeWidth={2}
                  name="actual"
                  dot={false}
                  connectNulls={false}
                />
              )}
              {visibleSeries.predicted && (
                <Area
                  type="monotone"
                  dataKey="predicted"
                  stroke="#fbbf24"
                  fill="none"
                  strokeWidth={2}
                  strokeDasharray="6 3"
                  name="predicted"
                  dot={false}
                  connectNulls={false}
                />
              )}
            </AreaChart>
          </ResponsiveContainer>
        </div>

        {/* Interactive legend */}
        <div className="flex flex-wrap items-center justify-center gap-2 mt-4 text-xs font-medium text-text-secondary">
          <button
            type="button"
            onClick={() => toggleSeries('actual')}
            className={`flex items-center gap-2 px-2 py-1 rounded cursor-pointer transition-all ${
              visibleSeries.actual
                ? 'bg-primary-500/10 text-primary-300 ring-1 ring-primary-400/20'
                : 'opacity-40 line-through'
            }`}
            aria-pressed={visibleSeries.actual}
            aria-label={t('forecast.toggleActual')}
          >
            <span className="w-4 h-0.5 bg-energy-green rounded" aria-hidden="true" />
            {t('forecast.actualConsumption')}
          </button>
          <button
            type="button"
            onClick={() => toggleSeries('predicted')}
            className={`flex items-center gap-2 px-2 py-1 rounded cursor-pointer transition-all ${
              visibleSeries.predicted
                ? 'bg-amber-500/10 text-accent-400 ring-1 ring-amber-400/20'
                : 'opacity-40 line-through'
            }`}
            aria-pressed={visibleSeries.predicted}
            aria-label={t('forecast.togglePredicted')}
          >
            <span
              className="w-4 h-0.5 rounded"
              style={{ borderTop: '2px dashed #fbbf24' }}
              aria-hidden="true"
            />
            {t('forecast.predictionSeries')}
          </button>
          <button
            type="button"
            onClick={() => toggleSeries('ci')}
            className={`flex items-center gap-2 px-2 py-1 rounded cursor-pointer transition-all ${
              visibleSeries.ci
                ? 'bg-primary-500/10 text-primary-300 ring-1 ring-primary-400/20'
                : 'opacity-40 line-through'
            }`}
            aria-pressed={visibleSeries.ci}
            aria-label={t('forecast.toggleCi')}
          >
            <span
              className="w-4 h-3 rounded bg-gradient-to-b from-primary-400/50 to-primary-500/10"
              aria-hidden="true"
            />
            {t('forecast.ci90')}
          </button>
        </div>
      </Card>
    </div>
  );
}

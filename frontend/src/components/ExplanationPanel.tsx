import { useState, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { api, type EnergyData, type ExplanationResponse } from '../api/client';
import { CardSkeleton } from './Card';
import { formatMW, formatPercent } from '../utils/format';
import { FadeInView } from './motion';
import { Brain, ChevronDown, ChevronUp, AlertTriangle } from 'lucide-react';
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

const POSITIVE_COLORS = ['#f97316', '#fb923c', '#fdba74', '#fed7aa', '#ffedd5'];
const NEGATIVE_COLORS = ['#0369a1', '#0284c7', '#0ea5e9', '#38bdf8', '#7dd3fc'];

function pickColor(contribution: number, idx: number): string {
  const palette = contribution < 0 ? NEGATIVE_COLORS : POSITIVE_COLORS;
  return palette[idx % palette.length];
}

type SortCol = 'rank' | 'importance' | 'value';

interface Props {
  weather: EnergyData;
}

export function ExplanationPanel({ weather }: Props) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const [result, setResult] = useState<ExplanationResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showTable, setShowTable] = useState(false);
  const [sortCol, setSortCol] = useState<SortCol>('rank');
  const [sortAsc, setSortAsc] = useState(true);

  const fetchExplanation = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.predictExplain(weather, 10);
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('common.unknownError'));
    } finally {
      setLoading(false);
    }
  }, [weather]);

  const handleToggle = () => {
    const next = !expanded;
    setExpanded(next);
    if (next && !result && !loading && !error) {
      void fetchExplanation();
    }
  };

  const handleRetry = () => {
    void fetchExplanation();
  };

  const chartData =
    result?.top_features.map((f) => {
      const contribution =
        (f as unknown as { contribution?: number }).contribution ?? f.importance;
      return {
        name: f.feature.length > 28 ? f.feature.slice(0, 26) + '...' : f.feature,
        fullName: f.feature,
        importance: +(f.importance * 100).toFixed(2),
        contribution,
        value: f.value,
        rank: f.rank,
      };
    }) || [];

  const sortedFeatures = result
    ? [...result.top_features].sort((a, b) => {
        const diff =
          sortCol === 'rank'
            ? a.rank - b.rank
            : sortCol === 'importance'
            ? a.importance - b.importance
            : a.value - b.value;
        return sortAsc ? diff : -diff;
      })
    : [];

  const handleSort = (col: SortCol) => {
    if (sortCol === col) setSortAsc(!sortAsc);
    else {
      setSortCol(col);
      setSortAsc(col === 'rank');
    }
  };

  return (
    <div className="space-y-3">
      <button
        type="button"
        onClick={handleToggle}
        aria-expanded={expanded}
        aria-controls="explanation-panel-body"
        className="w-full flex items-center justify-between gap-3 px-4 min-h-[44px] rounded-lg
          bg-primary-50 dark:bg-primary-900/20 hover:bg-primary-100 dark:hover:bg-primary-900/30
          border border-primary-200 dark:border-primary-800
          text-sm font-medium text-primary-700 dark:text-primary-300 cursor-pointer transition-colors
          focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 focus-visible:ring-offset-2"
      >
        <span className="flex items-center gap-2">
          <Brain className="w-4 h-4" aria-hidden="true" />
          {t('explain.button')}
        </span>
        {expanded ? (
          <ChevronUp className="w-4 h-4" aria-hidden="true" />
        ) : (
          <ChevronDown className="w-4 h-4" aria-hidden="true" />
        )}
      </button>

      {expanded && (
        <FadeInView>
          <div id="explanation-panel-body" className="space-y-4">
            {loading && (
              <div aria-busy="true">
                <CardSkeleton lines={5} />
              </div>
            )}

            {error && !loading && (
              <div
                className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-xl p-4 flex items-start gap-3"
                role="alert"
              >
                <AlertTriangle
                  className="w-5 h-5 text-red-500 shrink-0 mt-0.5"
                  aria-hidden="true"
                />
                <div className="flex-1">
                  <p className="text-sm font-medium text-red-800 dark:text-red-200">
                    {t('explain.errorTitle')}
                  </p>
                  <p className="text-sm text-red-600 dark:text-red-300 mt-0.5">{error}</p>
                  <button
                    type="button"
                    onClick={handleRetry}
                    className="mt-2 text-xs font-medium text-red-700 hover:text-red-900 underline cursor-pointer
                      focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-400 rounded"
                  >
                    {t('common.retry')}
                  </button>
                </div>
              </div>
            )}

            {result && !loading && !error && (
              <>
                <p className="text-sm text-text-secondary">
                  {t('explain.description')}
                </p>

                <div
                  className="h-[280px]"
                  role="img"
                  aria-label={t('explain.chartAria')}
                >
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart
                      data={chartData}
                      layout="vertical"
                      margin={{ top: 5, right: 20, left: 150, bottom: 5 }}
                    >
                      <CartesianGrid
                        strokeDasharray="3 3"
                        stroke="rgba(100,116,139,0.25)"
                        horizontal={false}
                      />
                      <XAxis
                        type="number"
                        tick={{ fontSize: 10, fill: 'var(--color-text-muted)' }}
                        label={{
                          value: t('explain.importance'),
                          position: 'insideBottom',
                          offset: -5,
                          style: { fontSize: 11, fill: 'var(--color-text-muted)' },
                        }}
                      />
                      <YAxis
                        type="category"
                        dataKey="name"
                        tick={{ fontSize: 12, fill: 'var(--color-text-secondary)' }}
                        width={150}
                      />
                      <Tooltip
                        content={({ active, payload }) => {
                          if (!active || !payload?.length) return null;
                          const d = payload[0].payload;
                          return (
                            <div className="bg-white border border-primary-200 rounded-md p-3 shadow-lg text-xs">
                              <p className="font-semibold text-text-primary">
                                {d.fullName}
                              </p>
                              <p className="text-text-secondary mt-1">
                                {t('explain.contribution')}:{' '}
                                <span className="font-mono tabular-nums">
                                  {formatMW(d.contribution)}
                                </span>
                              </p>
                              <p className="text-text-muted">{t('explain.rank')}: #{d.rank}</p>
                            </div>
                          );
                        }}
                      />
                      <Bar dataKey="importance" radius={[0, 4, 4, 0]} maxBarSize={24}>
                        {chartData.map((d, idx) => (
                          <Cell key={idx} fill={pickColor(d.contribution, idx)} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>

                <button
                  type="button"
                  onClick={() => setShowTable((s) => !s)}
                  aria-expanded={showTable}
                  aria-controls="explanation-table"
                  className="text-xs font-medium text-primary-600 hover:text-primary-800 underline cursor-pointer
                    focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 rounded"
                >
                  {showTable ? t('explain.hideTable') : t('explain.showTable')}
                </button>

                {showTable && (
                  <div
                    id="explanation-table"
                    className="overflow-x-auto -mx-5 sm:-mx-6 px-5 sm:px-6"
                  >
                    <table
                      className="w-full text-sm"
                      aria-label={t('explain.tableAria')}
                    >
                      <thead>
                        <tr className="border-b border-border">
                          <SortableHeader
                            label="#"
                            column="rank"
                            current={sortCol}
                            asc={sortAsc}
                            onSort={handleSort}
                            className="w-10 text-left"
                          />
                          <th
                            scope="col"
                            className="text-left py-3 px-3 text-xs font-medium text-text-muted"
                          >
                            {t('explain.colFeature')}
                          </th>
                          <SortableHeader
                            label={t('explain.colImportance')}
                            column="importance"
                            current={sortCol}
                            asc={sortAsc}
                            onSort={handleSort}
                            className="text-right"
                          />
                          <SortableHeader
                            label={t('explain.colValue')}
                            column="value"
                            current={sortCol}
                            asc={sortAsc}
                            onSort={handleSort}
                            className="text-right hidden sm:table-cell"
                          />
                        </tr>
                      </thead>
                      <tbody>
                        {sortedFeatures.map((f) => {
                          const contribution =
                            (f as unknown as { contribution?: number }).contribution ??
                            f.importance;
                          const contribColor =
                            contribution >= 0 ? 'text-emerald-600' : 'text-rose-600';
                          return (
                            <tr
                              key={f.rank}
                              className="border-b border-border/50 hover:bg-surface-dim transition-colors"
                            >
                              <td className="py-2.5 px-3 text-text-muted tabular-nums">
                                {f.rank}
                              </td>
                              <td className="py-2.5 px-3 font-mono text-xs text-text-primary whitespace-normal">
                                {f.feature}
                              </td>
                              <td className="py-2.5 px-3 text-right">
                                <div className="flex items-center justify-end gap-2">
                                  <div
                                    className="w-16 h-2 bg-surface-bright rounded-full overflow-hidden"
                                    role="progressbar"
                                    aria-valuenow={+(f.importance * 100).toFixed(1)}
                                    aria-valuemin={0}
                                    aria-valuemax={100}
                                  >
                                    <div
                                      className="h-full bg-primary-500 rounded-full transition-all duration-300"
                                      style={{
                                        width: `${Math.min(100, f.importance * 100)}%`,
                                      }}
                                    />
                                  </div>
                                  <span
                                    className={`font-mono text-xs w-20 text-right tabular-nums ${contribColor}`}
                                  >
                                    {formatPercent(f.importance * 100)}
                                  </span>
                                </div>
                              </td>
                              <td
                                className={`py-2.5 px-3 text-right font-mono text-xs tabular-nums hidden sm:table-cell ${contribColor}`}
                              >
                                {f.value.toFixed(4)}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </>
            )}
          </div>
        </FadeInView>
      )}
    </div>
  );
}

function SortableHeader({
  label,
  column,
  current,
  asc,
  onSort,
  className = '',
}: {
  label: string;
  column: SortCol;
  current: SortCol;
  asc: boolean;
  onSort: (col: SortCol) => void;
  className?: string;
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
        onClick={() => onSort(column)}
        className="flex items-center gap-1 cursor-pointer hover:text-text-primary transition
          focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 rounded"
      >
        {label}
        {isActive && <span className="text-[10px]">{asc ? '↑' : '↓'}</span>}
      </button>
    </th>
  );
}

export default ExplanationPanel;

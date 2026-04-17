import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ChevronDown, ChevronUp, Download } from 'lucide-react';
import { Card } from '../Card';
import { formatDateShort, formatMW, formatNumber } from '../../utils/format';
import type { PredictionResponse } from '../../api/client';

const ROW_HEIGHT = 40;
const VISIBLE_ROWS = 15;
const BUFFER_ROWS = 5;

type SortCol = 'time' | 'prediction' | 'amplitude';

export interface ForecastTableProps {
  results: PredictionResponse[];
  modelName: string;
  region: string;
  onExport: () => void;
}

/**
 * Virtualised, sortable table of forecast predictions. Used when the
 * Forecast page's view is switched to `'table'`. Keeps sorting state
 * local — reset on column change, toggled on repeat clicks.
 */
export function ForecastTable({ results, modelName, region, onExport }: ForecastTableProps) {
  const { t } = useTranslation();
  const [sortCol, setSortCol] = useState<SortCol>('time');
  const [sortAsc, setSortAsc] = useState(true);
  const [scrollTop, setScrollTop] = useState(0);
  const scrollRef = useRef<HTMLDivElement>(null);

  const handleSort = (col: SortCol) => {
    if (sortCol === col) setSortAsc(!sortAsc);
    else {
      setSortCol(col);
      setSortAsc(col === 'time');
    }
    setScrollTop(0);
    scrollRef.current?.scrollTo(0, 0);
  };

  const sortedResults = useMemo(() => {
    return [...results].sort((a, b) => {
      let diff: number;
      if (sortCol === 'time') {
        diff = new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime();
      } else if (sortCol === 'prediction') {
        diff = a.predicted_consumption_mw - b.predicted_consumption_mw;
      } else {
        diff =
          a.confidence_interval_upper - a.confidence_interval_lower -
          (b.confidence_interval_upper - b.confidence_interval_lower);
      }
      return sortAsc ? diff : -diff;
    });
  }, [results, sortCol, sortAsc]);

  const useVirtualization = sortedResults.length > 50;
  const totalHeight = useVirtualization ? sortedResults.length * ROW_HEIGHT : 0;
  const startIdx = useVirtualization
    ? Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - BUFFER_ROWS)
    : 0;
  const endIdx = useVirtualization
    ? Math.min(sortedResults.length, startIdx + VISIBLE_ROWS + BUFFER_ROWS * 2)
    : sortedResults.length;
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
    <div className="animate-fade-in-up">
      <Card
        title={t('forecast.resultsTitle', { count: formatNumber(results.length, 0) })}
        subtitle={t('forecast.chartSubtitle', { model: modelName, region })}
        action={
          <button
            type="button"
            onClick={onExport}
            className="flex items-center gap-1.5 text-xs font-mono font-medium uppercase tracking-wider
              text-primary-300 hover:text-primary-200 hover:bg-primary-500/10 cursor-pointer
              min-h-[44px] px-3 rounded-lg
              focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500 transition-colors"
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
                <th
                  className="text-left py-3 px-3 text-xs font-medium text-text-muted"
                  aria-sort={sortCol === 'time' ? (sortAsc ? 'ascending' : 'descending') : 'none'}
                >
                  <button
                    type="button"
                    onClick={() => handleSort('time')}
                    className="flex items-center gap-1 cursor-pointer hover:text-text-primary transition"
                  >
                    {t('forecast.colTime')}{' '}
                    {sortCol === 'time' &&
                      (sortAsc ? (
                        <ChevronUp className="w-3 h-3" aria-hidden="true" />
                      ) : (
                        <ChevronDown className="w-3 h-3" aria-hidden="true" />
                      ))}
                  </button>
                </th>
                <th
                  className="text-right py-3 px-3 text-xs font-medium text-text-muted"
                  aria-sort={sortCol === 'prediction' ? (sortAsc ? 'ascending' : 'descending') : 'none'}
                >
                  <button
                    type="button"
                    onClick={() => handleSort('prediction')}
                    className="flex items-center gap-1 justify-end cursor-pointer hover:text-text-primary transition ml-auto"
                  >
                    {t('forecast.colPrediction')}{' '}
                    {sortCol === 'prediction' &&
                      (sortAsc ? (
                        <ChevronUp className="w-3 h-3" aria-hidden="true" />
                      ) : (
                        <ChevronDown className="w-3 h-3" aria-hidden="true" />
                      ))}
                  </button>
                </th>
                <th className="text-right py-3 px-3 text-xs font-medium text-text-muted hidden sm:table-cell">
                  {t('forecast.colCiLower')}
                </th>
                <th className="text-right py-3 px-3 text-xs font-medium text-text-muted hidden sm:table-cell">
                  {t('forecast.colCiUpper')}
                </th>
                <th
                  className="text-right py-3 px-3 text-xs font-medium text-text-muted"
                  aria-sort={sortCol === 'amplitude' ? (sortAsc ? 'ascending' : 'descending') : 'none'}
                >
                  <button
                    type="button"
                    onClick={() => handleSort('amplitude')}
                    className="flex items-center gap-1 justify-end cursor-pointer hover:text-text-primary transition ml-auto"
                  >
                    {t('forecast.colAmplitude')}{' '}
                    {sortCol === 'amplitude' &&
                      (sortAsc ? (
                        <ChevronUp className="w-3 h-3" aria-hidden="true" />
                      ) : (
                        <ChevronDown className="w-3 h-3" aria-hidden="true" />
                      ))}
                  </button>
                </th>
                <th className="text-center py-3 px-3 text-xs font-medium text-text-muted hidden md:table-cell">
                  {t('forecast.colMethod')}
                </th>
              </tr>
            </thead>
            <tbody>
              {useVirtualization && (
                <tr style={{ height: offsetY }} aria-hidden="true">
                  <td />
                </tr>
              )}
              {visibleRows.map((r, i) => {
                const range = r.confidence_interval_upper - r.confidence_interval_lower;
                return (
                  <tr
                    key={startIdx + i}
                    className="border-b border-border/50 hover:bg-surface-dim transition-colors"
                    style={useVirtualization ? { height: ROW_HEIGHT } : undefined}
                  >
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
                      <span
                        className={`text-[10px] font-mono font-medium uppercase tracking-wider px-2 py-0.5 rounded-full ring-1 ${
                          r.ci_method === 'conformal'
                            ? 'bg-emerald-500/10 text-energy-green ring-emerald-400/20'
                            : 'bg-yellow-500/10 text-energy-yellow ring-yellow-400/20'
                        }`}
                      >
                        {r.ci_method === 'conformal'
                          ? t('forecast.methodConformal')
                          : t('forecast.methodGaussian')}
                      </span>
                    </td>
                  </tr>
                );
              })}
              {useVirtualization && (
                <tr
                  style={{ height: Math.max(0, totalHeight - offsetY - visibleRows.length * ROW_HEIGHT) }}
                  aria-hidden="true"
                >
                  <td />
                </tr>
              )}
            </tbody>
          </table>
        </div>
        {useVirtualization && (
          <p className="text-[11px] text-text-muted text-center mt-2">
            {t('forecast.virtualized', {
              shown: visibleRows.length,
              total: formatNumber(sortedResults.length, 0),
            })}
          </p>
        )}
      </Card>
    </div>
  );
}

import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { type EnergyData, type PredictionResponse, type Region } from '../api/client';
import { useBatchMutation } from '../api/hooks';
import { toast } from '../components/Toast';
import { exportCSV } from '../utils/format';

/**
 * Synthesise a plausible weather forecast payload for the demo's batch
 * prediction. Keeps the temperature/humidity daily cycle while jittering
 * values so the resulting chart has some variation. Only weather is
 * synthesised — no consumption lags — which is why the demo uses the
 * no-lags model: synthesising lag values would produce optically precise
 * but scientifically dishonest output.
 */
export function generateForecastItems(region: Region, hours: number): EnergyData[] {
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

export interface UseForecastDataResult {
  results: PredictionResponse[];
  modelName: string;
  explainWeather: EnergyData | null;
  loading: boolean;
  submitting: boolean;
  error: string | null;
  run: () => void;
  exportCsv: () => void;
}

/**
 * Encapsulates all data/state for the Forecast page: batch mutation
 * (predict), CSV export, loading + error derivations. Keeps the page
 * component concerned only with layout.
 */
export function useForecastData(region: Region, forecastHours: number): UseForecastDataResult {
  const { t } = useTranslation();
  const [results, setResults] = useState<PredictionResponse[]>([]);
  const [modelName, setModelName] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [explainWeather, setExplainWeather] = useState<EnergyData | null>(null);

  const batch = useBatchMutation({
    onSuccess: (res, items) => {
      setResults(res.predictions);
      setExplainWeather(items[Math.floor(items.length / 2)] ?? null);
      setModelName(res.predictions[0]?.model_name ?? 'XGBoost (no lags)');
      toast.success(
        t('forecast.forecastGenerated', { count: res.predictions.length, region }),
      );
    },
    onError: () => {
      toast.error(t('forecast.forecastFailed'));
    },
  });

  const run = () => {
    if (submitting) return;
    setSubmitting(true);
    setExplainWeather(null);
    const items = generateForecastItems(region, forecastHours);
    batch.mutate(items, {
      onSettled: () => {
        setTimeout(() => setSubmitting(false), 1000);
      },
    });
  };

  const exportCsv = () => {
    if (!results.length) return;
    exportCSV(
      `forecast_${region}_${new Date().toISOString().slice(0, 10)}.csv`,
      ['timestamp', 'region', 'predicted_mw', 'ci_lower', 'ci_upper', 'model', 'ci_method'],
      results.map((r) => [
        r.timestamp,
        r.region,
        r.predicted_consumption_mw.toFixed(2),
        r.confidence_interval_lower.toFixed(2),
        r.confidence_interval_upper.toFixed(2),
        r.model_name,
        r.ci_method,
      ]),
    );
    toast.success(t('forecast.csvExported'));
  };

  const loading = batch.isPending;
  const error = batch.error ? batch.error.message || t('common.unknownError') : null;

  return {
    results,
    modelName,
    explainWeather,
    loading,
    submitting,
    error,
    run,
    exportCsv,
  };
}

/**
 * Base URL for the FastAPI backend.
 *
 * Resolution order:
 *   1. `VITE_API_URL` environment variable (e.g. `http://localhost:8000`)
 *      — used for production builds or when hitting the backend directly
 *      without the Vite dev proxy.
 *   2. Default `/api` — during `vite dev`/`vite preview` this is rewritten
 *      to `http://localhost:8000` by the proxy defined in `vite.config.ts`.
 *
 * See `frontend/.env.example` for documentation.
 */
export const BASE_URL: string =
  (import.meta.env?.VITE_API_URL as string | undefined)?.replace(/\/$/, '') ?? '/api';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: { message: res.statusText } }));
    throw new Error(body?.detail?.message || `HTTP ${res.status}`);
  }
  return res.json();
}

// Types
export interface PredictionResponse {
  timestamp: string;
  region: string;
  predicted_consumption_mw: number;
  confidence_interval_lower: number;
  confidence_interval_upper: number;
  model_name: string;
  confidence_level: number;
  ci_method: string;
  ci_lower_clipped: boolean;
}

export interface BatchPredictionResponse {
  predictions: PredictionResponse[];
  total_predictions: number;
}

export interface SequentialForecastResponse {
  predictions: PredictionResponse[];
  total_predictions: number;
  history_rows_used: number;
  model_name: string;
}

export interface FeatureContribution {
  feature: string;
  importance: number;
  value: number;
  rank: number;
}

export interface ExplanationResponse {
  prediction: PredictionResponse;
  top_features: FeatureContribution[];
  explanation_method: string;
  total_features: number;
}

export interface EnergyData {
  timestamp: string;
  region: string;
  temperature: number;
  humidity: number;
  wind_speed: number;
  precipitation: number;
  cloud_cover: number;
  pressure: number;
}

export interface HealthResponse {
  status: string;
  version: string;
  uptime_seconds: number;
  models_loaded: Record<string, boolean>;
  coverage_alert?: boolean;
  [key: string]: unknown;
}

export interface ModelInfoResponse {
  [key: string]: unknown;
}

export interface DriftCheckResponse {
  [key: string]: unknown;
}

export interface CoverageResponse {
  [key: string]: unknown;
}

export type Region = 'Alentejo' | 'Algarve' | 'Centro' | 'Lisboa' | 'Norte';
export const REGIONS: Region[] = ['Alentejo', 'Algarve', 'Centro', 'Lisboa', 'Norte'];

// API calls
export const api = {
  health: () => request<HealthResponse>('/health'),
  regions: () => request<{ regions: string[] }>('/regions'),
  limitations: () => request<Record<string, unknown>>('/limitations'),
  modelInfo: () => request<ModelInfoResponse>('/model/info'),
  modelDrift: () => request<Record<string, unknown>>('/model/drift'),
  modelCoverage: () => request<CoverageResponse>('/model/coverage'),
  metricsSummary: () => request<Record<string, unknown>>('/metrics/summary'),

  predict: (data: EnergyData) =>
    request<PredictionResponse>('/predict', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  predictBatch: (items: EnergyData[]) =>
    request<BatchPredictionResponse>('/predict/batch', {
      method: 'POST',
      body: JSON.stringify(items),
    }),

  predictSequential: (history: unknown[], forecast: EnergyData[]) =>
    request<SequentialForecastResponse>('/predict/sequential', {
      method: 'POST',
      body: JSON.stringify({ history, forecast }),
    }),

  predictExplain: (data: EnergyData, topN = 10) =>
    request<ExplanationResponse>(`/predict/explain?top_n=${topN}`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  driftCheck: (features: Record<string, number>) =>
    request<DriftCheckResponse>('/model/drift/check', {
      method: 'POST',
      body: JSON.stringify({ features }),
    }),

  recordCoverage: (timestamp: string, region: string, predicted: number, actual: number, ciLower: number, ciUpper: number) =>
    request<Record<string, unknown>>('/model/coverage/record', {
      method: 'POST',
      body: JSON.stringify({
        timestamp, region,
        predicted_consumption_mw: predicted,
        actual_consumption_mw: actual,
        confidence_interval_lower: ciLower,
        confidence_interval_upper: ciUpper,
      }),
    }),
};

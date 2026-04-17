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

export interface ModelVariantInfo {
  model_type?: string;
  features_count?: number;
  mae?: number;
  rmse?: number;
  mape?: number;
  r2?: number;
  mase?: number;
  trained_at?: string;
  conformal_q90?: number;
  [key: string]: unknown;
}

export interface ModelInfoResponse {
  status: string;
  models_available: {
    with_lags?: ModelVariantInfo;
    no_lags?: ModelVariantInfo;
    advanced?: ModelVariantInfo;
  };
  model_checksums?: Record<string, string>;
}

export interface FeatureStat {
  mean?: number;
  std?: number;
  min?: number;
  max?: number;
  q25?: number;
  q50?: number;
  q75?: number;
}

export type DriftResponse =
  | {
      available: false;
      message: string;
      guidance: { how_to_generate: string; alert_threshold: string };
    }
  | {
      available: true;
      source_model: string | null;
      feature_count: number;
      feature_stats: Record<string, FeatureStat>;
      usage_note: string;
    };

export type DriftLevel = "normal" | "elevated" | "alert";

export interface FeatureDriftScore {
  z_score: number | null;
  live_mean?: number;
  training_mean?: number;
  training_std?: number;
  drift_level?: DriftLevel;
  note?: string;
}

export interface DriftCheckResponse {
  source_model: string | null;
  features_checked: number;
  alerts: string[];
  alert_count: number;
  drift_scores: Record<string, FeatureDriftScore>;
  thresholds: { normal: string; elevated: string; alert: string };
}

export interface CoverageSummary {
  coverage: number | null;
  n_observations: number;
  alert: boolean;
  alert_threshold: number;
  nominal_coverage: number;
  window_size: number;
}

export type CoverageResponse =
  | { available: false; message: string }
  | ({ available: true } & CoverageSummary);

export interface MetricsSummaryResponse {
  uptime_seconds: number | null;
  api_version: string;
  models: {
    total_loaded: number;
    with_lags: boolean;
    no_lags: boolean;
    advanced: boolean;
    rmse_calibrated: boolean;
  };
  coverage: CoverageResponse;
  config: {
    rate_limit_max: number;
    rate_limit_window_seconds: number;
    max_request_body_bytes: number;
    prediction_timeout_seconds: number;
    log_level: string;
    trust_proxy: boolean;
    auth_enabled: boolean;
  };
}

export type Region = 'Alentejo' | 'Algarve' | 'Centro' | 'Lisboa' | 'Norte';
export const REGIONS: Region[] = ['Alentejo', 'Algarve', 'Centro', 'Lisboa', 'Norte'];

// API calls
export const api = {
  health: () => request<HealthResponse>('/health'),
  regions: () => request<{ regions: string[] }>('/regions'),
  limitations: () => request<Record<string, unknown>>('/limitations'),
  modelInfo: () => request<ModelInfoResponse>('/model/info'),
  modelDrift: () => request<DriftResponse>('/model/drift'),
  modelCoverage: () => request<CoverageResponse>('/model/coverage'),
  metricsSummary: () => request<MetricsSummaryResponse>('/metrics/summary'),

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

import {
  useMutation,
  useQuery,
  type UseMutationOptions,
  type UseQueryOptions,
} from '@tanstack/react-query';
import {
  api,
  type BatchPredictionResponse,
  type CoverageResponse,
  type DriftResponse,
  type EnergyData,
  type ExplanationResponse,
  type HealthResponse,
  type MetricsSummaryResponse,
  type ModelInfoResponse,
  type PredictionResponse,
  type SequentialForecastResponse,
} from './client';

/**
 * Query keys — single source of truth so we can invalidate/prefetch
 * from anywhere in the app. Keep them flat; nested arrays only when a
 * query takes parameters (then the second entry is the param object).
 */
export const queryKeys = {
  health: ['health'] as const,
  modelInfo: ['modelInfo'] as const,
  modelCoverage: ['modelCoverage'] as const,
  modelDrift: ['modelDrift'] as const,
  metricsSummary: ['metricsSummary'] as const,
};

// ── Queries (reads) ─────────────────────────────────────────────────────────

/** Poll `/health` every 30 s; retry twice on transient failure. */
export function useHealth(
  options?: Omit<UseQueryOptions<HealthResponse>, 'queryKey' | 'queryFn'>,
) {
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: api.health,
    staleTime: 30_000,
    refetchInterval: 30_000,
    refetchOnWindowFocus: false,
    ...options,
  });
}

export function useModelInfo(
  options?: Omit<UseQueryOptions<ModelInfoResponse>, 'queryKey' | 'queryFn'>,
) {
  return useQuery({
    queryKey: queryKeys.modelInfo,
    queryFn: api.modelInfo,
    staleTime: 5 * 60_000,
    ...options,
  });
}

export function useMetricsSummary(
  options?: Omit<UseQueryOptions<MetricsSummaryResponse>, 'queryKey' | 'queryFn'>,
) {
  return useQuery({
    queryKey: queryKeys.metricsSummary,
    queryFn: api.metricsSummary,
    staleTime: 30_000,
    refetchInterval: 30_000,
    ...options,
  });
}

export function useModelCoverage(
  options?: Omit<UseQueryOptions<CoverageResponse>, 'queryKey' | 'queryFn'>,
) {
  return useQuery({
    queryKey: queryKeys.modelCoverage,
    queryFn: api.modelCoverage,
    staleTime: 60_000,
    ...options,
  });
}

export function useModelDrift(
  options?: Omit<UseQueryOptions<DriftResponse>, 'queryKey' | 'queryFn'>,
) {
  return useQuery({
    queryKey: queryKeys.modelDrift,
    queryFn: api.modelDrift,
    staleTime: 5 * 60_000,
    ...options,
  });
}

// ── Mutations (writes) ─────────────────────────────────────────────────────

export function usePredictMutation(
  options?: UseMutationOptions<PredictionResponse, Error, EnergyData>,
) {
  return useMutation({
    mutationFn: api.predict,
    ...options,
  });
}

export function useBatchMutation(
  options?: UseMutationOptions<BatchPredictionResponse, Error, EnergyData[]>,
) {
  return useMutation({
    mutationFn: api.predictBatch,
    ...options,
  });
}

export function useExplainMutation(
  options?: UseMutationOptions<
    ExplanationResponse,
    Error,
    { data: EnergyData; topN?: number }
  >,
) {
  return useMutation({
    mutationFn: ({ data, topN }) => api.predictExplain(data, topN),
    ...options,
  });
}

export function useSequentialMutation(
  options?: UseMutationOptions<
    SequentialForecastResponse,
    Error,
    { history: unknown[]; forecast: EnergyData[] }
  >,
) {
  return useMutation({
    mutationFn: ({ history, forecast }) => api.predictSequential(history, forecast),
    ...options,
  });
}

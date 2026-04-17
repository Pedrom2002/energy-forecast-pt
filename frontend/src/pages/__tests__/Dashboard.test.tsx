import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import Dashboard from '../Dashboard';
import { renderWithProviders } from '../../test/test-utils';
import { api } from '../../api/client';

// Mock the API client — happy path. Individual tests can override.
vi.mock('../../api/client', async () => {
  const actual = await vi.importActual<typeof import('../../api/client')>('../../api/client');
  return {
    ...actual,
    api: {
      health: vi.fn(),
      modelInfo: vi.fn(),
      metricsSummary: vi.fn(),
      regions: vi.fn(),
      limitations: vi.fn(),
      modelDrift: vi.fn(),
      modelCoverage: vi.fn(),
      predict: vi.fn(),
      predictBatch: vi.fn(),
      predictSequential: vi.fn(),
      predictExplain: vi.fn(),
      driftCheck: vi.fn(),
      recordCoverage: vi.fn(),
    },
  };
});

// HeroChart calls predictBatch on mount — stub quietly.
const healthy = {
  status: 'healthy' as const,
  version: '1.0.0',
  uptime_seconds: 3600,
  models_loaded: { with_lags: true, no_lags: true },
  total_models: 2,
};

const mockedApi = vi.mocked(api);

describe('Dashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedApi.predictBatch.mockResolvedValue({ predictions: [], total_predictions: 0 });
  });

  it('shows loading skeletons initially', () => {
    mockedApi.health.mockReturnValue(new Promise(() => {})); // never resolves
    mockedApi.modelInfo.mockReturnValue(new Promise(() => {}));
    mockedApi.metricsSummary.mockReturnValue(new Promise(() => {}));

    const { container } = renderWithProviders(<Dashboard />);
    expect(container.querySelector('[aria-busy="true"]')).not.toBeNull();
  });

  it('renders main heading and status chip on happy path', async () => {
    mockedApi.health.mockResolvedValue(healthy);
    mockedApi.modelInfo.mockResolvedValue({ status: 'healthy', models_available: {} });
    mockedApi.metricsSummary.mockResolvedValue({
      uptime_seconds: 3600,
      api_version: '1.0.0',
      models: { total_loaded: 2, with_lags: true, no_lags: true, advanced: false, rmse_calibrated: true },
      coverage: { available: false, message: 'n/a' },
      config: {
        rate_limit_max: 60,
        rate_limit_window_seconds: 60,
        max_request_body_bytes: 1_000_000,
        prediction_timeout_seconds: 5,
        log_level: 'INFO',
        trust_proxy: true,
        auth_enabled: false,
      },
    });

    renderWithProviders(<Dashboard />);

    // Title is the biggest H1 — it includes the "PT" gradient accent.
    await waitFor(() => {
      expect(screen.getAllByRole('heading', { level: 1 }).length).toBeGreaterThan(0);
    });
  });

  it('shows API unavailable state on /health failure', async () => {
    mockedApi.health.mockRejectedValue(new Error('ECONNREFUSED localhost:8000'));
    mockedApi.modelInfo.mockRejectedValue(new Error('nope'));
    mockedApi.metricsSummary.mockRejectedValue(new Error('nope'));

    renderWithProviders(<Dashboard />);

    await waitFor(() => {
      expect(screen.getByText(/ECONNREFUSED/i)).toBeInTheDocument();
    });
  });

  it('displays the refresh button with accessible label', async () => {
    mockedApi.health.mockResolvedValue(healthy);
    mockedApi.modelInfo.mockResolvedValue({ status: 'healthy', models_available: {} });
    mockedApi.metricsSummary.mockResolvedValue({
      uptime_seconds: 3600,
      api_version: '1.0.0',
      models: { total_loaded: 2, with_lags: true, no_lags: true, advanced: false, rmse_calibrated: true },
      coverage: { available: false, message: 'n/a' },
      config: {
        rate_limit_max: 60,
        rate_limit_window_seconds: 60,
        max_request_body_bytes: 1_000_000,
        prediction_timeout_seconds: 5,
        log_level: 'INFO',
        trust_proxy: true,
        auth_enabled: false,
      },
    });

    renderWithProviders(<Dashboard />);

    await waitFor(() => {
      // The refresh button uses aria-label from t('dashboard.updateData').
      // Match by accessible role + it exists (name covers any i18n string).
      expect(
        screen.getAllByRole('button', { name: /atualizar|update/i }).length,
      ).toBeGreaterThan(0);
    });
  });
});

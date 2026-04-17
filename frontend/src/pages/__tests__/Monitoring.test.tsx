import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import Monitoring from '../Monitoring';
import { renderWithProviders } from '../../test/test-utils';
import { api } from '../../api/client';

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

const mockedApi = vi.mocked(api);

const coverageOk = {
  available: true as const,
  coverage: 0.91,
  n_observations: 150,
  alert: false,
  alert_threshold: 0.8,
  nominal_coverage: 0.9,
  window_size: 168,
};

const metricsOk = {
  uptime_seconds: 3600,
  api_version: '1.0.0',
  models: {
    total_loaded: 2,
    with_lags: true,
    no_lags: true,
    advanced: false,
    rmse_calibrated: true,
  },
  coverage: coverageOk,
  config: {
    rate_limit_max: 60,
    rate_limit_window_seconds: 60,
    max_request_body_bytes: 1_000_000,
    prediction_timeout_seconds: 5,
    log_level: 'INFO',
    trust_proxy: true,
    auth_enabled: false,
  },
};

describe('Monitoring', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows loading skeletons while fetching', () => {
    mockedApi.modelCoverage.mockReturnValue(new Promise(() => {}));
    mockedApi.metricsSummary.mockReturnValue(new Promise(() => {}));

    const { container } = renderWithProviders(<Monitoring />);
    expect(container.querySelector('[aria-busy="true"]')).not.toBeNull();
  });

  it('renders KPI tiles on happy path', async () => {
    mockedApi.modelCoverage.mockResolvedValue(coverageOk);
    mockedApi.metricsSummary.mockResolvedValue(metricsOk);

    renderWithProviders(<Monitoring />);

    await waitFor(() => {
      // Coverage percent appears somewhere — displayed with one decimal.
      expect(screen.getAllByText(/9[01]\.\d%/).length).toBeGreaterThan(0);
    });
  });

  it('surfaces limited data warning on coverage endpoint failure', async () => {
    mockedApi.modelCoverage.mockRejectedValue(new Error('Coverage tracker unavailable'));
    mockedApi.metricsSummary.mockResolvedValue(metricsOk);

    renderWithProviders(<Monitoring />);

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument();
    });
  });
});

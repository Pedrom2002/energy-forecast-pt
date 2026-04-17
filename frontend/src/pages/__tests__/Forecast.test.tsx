import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Forecast from '../Forecast';
import { renderWithProviders } from '../../test/test-utils';
import { api, type PredictionResponse } from '../../api/client';

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

function predictionAt(ts: string, mw: number): PredictionResponse {
  return {
    timestamp: ts,
    region: 'Lisboa',
    predicted_consumption_mw: mw,
    confidence_interval_lower: mw * 0.9,
    confidence_interval_upper: mw * 1.1,
    model_name: 'xgboost_no_lags',
    confidence_level: 0.9,
    ci_method: 'conformal',
    ci_lower_clipped: false,
  };
}

describe('Forecast', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders empty state by default', () => {
    renderWithProviders(<Forecast />);
    // Title heading.
    expect(screen.getAllByRole('heading', { level: 1 }).length).toBeGreaterThan(0);
    // Run button.
    expect(screen.getByRole('button', { name: /executar|run/i })).toBeInTheDocument();
  });

  it('shows chart + table toggle after a successful forecast', async () => {
    mockedApi.predictBatch.mockResolvedValue({
      predictions: [
        predictionAt('2026-04-17T10:00:00', 200),
        predictionAt('2026-04-17T11:00:00', 210),
      ],
      total_predictions: 2,
    });

    renderWithProviders(<Forecast />);

    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /executar|run/i }));

    await waitFor(() => {
      // radio-group toggle visible once we have results.
      expect(screen.getByRole('radiogroup')).toBeInTheDocument();
    });
  });

  it('shows error banner with retry on API failure', async () => {
    mockedApi.predictBatch.mockRejectedValue(new Error('Timeout'));

    renderWithProviders(<Forecast />);

    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /executar|run/i }));

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(/timeout/i);
    });
  });
});

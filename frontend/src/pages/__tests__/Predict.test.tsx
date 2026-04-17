import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Predict from '../Predict';
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

describe('Predict', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the form in empty/ready state', () => {
    renderWithProviders(<Predict />);
    // Title heading.
    expect(screen.getAllByRole('heading', { level: 1 }).length).toBeGreaterThan(0);
    // Submit button.
    expect(screen.getByRole('button', { name: /prever|predict/i })).toBeInTheDocument();
  });

  it('displays the result after a successful prediction', async () => {
    mockedApi.predict.mockResolvedValue({
      timestamp: '2026-04-17T10:00:00',
      region: 'Lisboa',
      predicted_consumption_mw: 250.5,
      confidence_interval_lower: 230.0,
      confidence_interval_upper: 270.0,
      model_name: 'xgboost_no_lags',
      confidence_level: 0.9,
      ci_method: 'conformal',
      ci_lower_clipped: false,
    });

    renderWithProviders(<Predict />);

    const user = userEvent.setup();
    const submit = screen.getByRole('button', { name: /prever|predict/i });
    await user.click(submit);

    await waitFor(() => {
      // Predicted MW value rendered — multiple places (hero + CI grid).
      expect(screen.getAllByText(/250/).length).toBeGreaterThan(0);
      expect(screen.getByText(/xgboost_no_lags/i)).toBeInTheDocument();
    });
  });

  it('shows an error banner when /predict fails', async () => {
    mockedApi.predict.mockRejectedValue(new Error('Service unavailable'));

    renderWithProviders(<Predict />);

    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /prever|predict/i }));

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(/service unavailable/i);
    });
  });
});

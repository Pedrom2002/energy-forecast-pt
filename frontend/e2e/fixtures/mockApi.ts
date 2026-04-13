import type { Page, Route } from '@playwright/test';

/**
 * Shared API mocks so smoke tests don't need a live FastAPI backend.
 *
 * The frontend talks to the backend via the Vite dev proxy at `/api/**`.
 * We intercept every `/api/**` request and return canned JSON.
 */

const healthResponse = {
  status: 'healthy',
  version: '1.0.0-test',
  uptime_seconds: 12345,
  models_loaded: {
    catboost_main: true,
    conformal_calibrator: true,
  },
  coverage_alert: false,
};

const modelInfoResponse = {
  model_name: 'catboost_v8',
  mape: 1.44,
  rmse: 210.3,
  training_date: '2026-03-15',
  features: 42,
};

const metricsSummaryResponse = {
  requests_total: 1024,
  cache_hit_rate: 0.87,
  p50_latency_ms: 12,
  p95_latency_ms: 38,
};

const regionsResponse = {
  regions: ['Alentejo', 'Algarve', 'Centro', 'Lisboa', 'Norte'],
};

const predictResponse = {
  timestamp: '2026-04-11T12:00:00',
  region: 'Lisboa',
  predicted_consumption_mw: 5432.1,
  confidence_interval_lower: 5200.0,
  confidence_interval_upper: 5664.2,
  model_name: 'catboost_v8',
  confidence_level: 0.9,
  ci_method: 'conformal',
  ci_lower_clipped: false,
};

const driftResponse = { drift_detected: false, score: 0.12 };
const coverageResponse = { coverage: 0.91, target: 0.9, alert: false };
const limitationsResponse = { max_forecast_horizon_h: 168 };

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  });
}

/**
 * Install default GET/POST mocks for every backend endpoint the UI touches.
 * Call once per test, before `page.goto(...)`.
 */
export async function mockBackend(page: Page): Promise<void> {
  await page.route(
    (url) => /^\/api(\/|$)/.test(url.pathname),
    async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname.replace(/^\/api/, '') || '/';

    // Routes are matched by suffix so proxied `/api/<path>` and direct
    // `http://localhost:8000/<path>` both work.
    if (path === '/health') return json(route, healthResponse);
    if (path === '/model/info') return json(route, modelInfoResponse);
    if (path === '/metrics/summary') return json(route, metricsSummaryResponse);
    if (path === '/regions') return json(route, regionsResponse);
    if (path === '/limitations') return json(route, limitationsResponse);
    if (path === '/model/drift') return json(route, driftResponse);
    if (path === '/model/coverage') return json(route, coverageResponse);

    if (path === '/predict') return json(route, predictResponse);
    if (path === '/predict/batch') {
      return json(route, { predictions: [predictResponse], total_predictions: 1 });
    }
    if (path === '/predict/sequential') {
      return json(route, {
        predictions: [predictResponse],
        total_predictions: 1,
        history_rows_used: 24,
        model_name: 'catboost_v8',
      });
    }
    if (path.startsWith('/predict/explain')) {
      return json(route, {
        prediction: predictResponse,
        top_features: [
          { feature: 'hour_of_day', importance: 0.32, value: 12, rank: 1 },
          { feature: 'temperature', importance: 0.21, value: 18.5, rank: 2 },
        ],
        explanation_method: 'shap',
        total_features: 42,
      });
    }

    // Fallback so unexpected calls fail loudly rather than hang on the
    // real network.
    return json(route, { detail: { message: `unmocked ${path}` } }, 404);
    },
  );
}

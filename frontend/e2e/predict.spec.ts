import { test, expect } from '@playwright/test';
import { mockBackend } from './fixtures/mockApi';

test.describe('Predict page smoke', () => {
  test('renders weather form fields and an enabled submit button', async ({ page }) => {
    await mockBackend(page);
    await page.goto('/predict');

    // Page heading
    await expect(
      page.getByRole('heading', { level: 1, name: /Previsao Individual/i }),
    ).toBeVisible();

    // All required weather inputs are present (ids come from WeatherForm
    // with idPrefix="pred").
    const expectedIds = [
      '#pred-timestamp',
      '#pred-region',
      '#pred-temp',
      '#pred-hum',
      '#pred-wind',
      '#pred-precip',
      '#pred-cloud',
      '#pred-pressure',
    ];
    for (const id of expectedIds) {
      await expect(page.locator(id)).toBeVisible();
    }

    // Submit button exists and is enabled once the form has values (the
    // form ships with sensible defaults, so the button is immediately
    // actionable — we still assert "enabled after fields filled" by
    // touching one field and re-asserting).
    const submit = page.getByRole('button', { name: /Prever Consumo/i });
    await expect(submit).toBeVisible();
    await expect(submit).toBeEnabled();

    // Simulate the user editing a required field, then ensure the submit
    // button remains actionable (not disabled).
    await page.locator('#pred-temp').fill('22.5');
    await expect(submit).toBeEnabled();

    // Clicking submit should hit the mocked /predict endpoint and render
    // the prediction card.
    await submit.click();
    await expect(page.getByText(/Consumo Previsto/i)).toBeVisible();
  });
});

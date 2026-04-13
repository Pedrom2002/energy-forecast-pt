import { test, expect } from '@playwright/test';
import { mockBackend } from './fixtures/mockApi';

test.describe('Predict page smoke', () => {
  test('renders weather form fields and an enabled submit button', async ({ page }) => {
    await mockBackend(page);
    await page.goto('/predict');

    // Page heading — matches both EN ("Single prediction") and PT ("Previsão pontual")
    await expect(
      page.getByRole('heading', { level: 1, name: /(single prediction|previs[aã]o pontual)/i }),
    ).toBeVisible();

    // All required weather inputs are present (ids come from WeatherForm with idPrefix="pred")
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

    // Submit button — matches both EN ("Predict") and PT ("Prever")
    const submit = page.getByRole('button', { name: /(predict|prever)/i }).first();
    await expect(submit).toBeVisible();
    await expect(submit).toBeEnabled();

    await page.locator('#pred-temp').fill('22.5');
    await expect(submit).toBeEnabled();
  });
});

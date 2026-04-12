import { test, expect } from '@playwright/test';
import { mockBackend } from './fixtures/mockApi';

test.describe('Dashboard smoke', () => {
  test('loads without console errors and renders hero + KPI cards', async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text());
    });
    page.on('pageerror', (err) => consoleErrors.push(err.message));

    await mockBackend(page);
    await page.goto('/');

    // Hero / title
    await expect(
      page.getByRole('heading', { level: 1, name: /dashboard/i }),
    ).toBeVisible();

    // KPI stat cards — Dashboard renders 4 StatCards with these labels
    for (const label of ['Status', 'Uptime', 'Modelos', /Cobertura/i]) {
      await expect(page.getByText(label).first()).toBeVisible();
    }

    // Model status card title
    await expect(page.getByText(/Estado dos Modelos/i)).toBeVisible();

    // No console errors surfaced during load. Ignore benign dev noise (HMR,
    // React devtools suggestion).
    const meaningfulErrors = consoleErrors.filter(
      (e) => !/React DevTools|HMR|hydration/i.test(e),
    );
    expect(meaningfulErrors, meaningfulErrors.join('\n')).toHaveLength(0);
  });
});

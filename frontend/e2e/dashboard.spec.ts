import { test, expect } from '@playwright/test';
import { mockBackend } from './fixtures/mockApi';

test.describe('Dashboard smoke', () => {
  test('renders hero + live chart + main landmark', async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text());
    });
    page.on('pageerror', (err) => consoleErrors.push(err.message));

    await mockBackend(page);
    await page.goto('/');

    // Hero heading — matches both EN and PT (word "Dashboard" is identical)
    await expect(
      page.getByRole('heading', { level: 1, name: /dashboard/i }),
    ).toBeVisible();

    // Main content landmark is present
    await expect(page.getByRole('main')).toBeVisible();

    // At least one chart/image role exists (live HeroChart or Portugal map)
    await expect(page.locator('[role="img"]').first()).toBeVisible();

    // No meaningful console errors
    const meaningful = consoleErrors.filter(
      (e) => !/React DevTools|HMR|hydration/i.test(e),
    );
    expect(meaningful, meaningful.join('\n')).toHaveLength(0);
  });
});

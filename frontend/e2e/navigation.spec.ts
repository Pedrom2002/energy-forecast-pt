import { test, expect } from '@playwright/test';
import { mockBackend } from './fixtures/mockApi';

// 4 main routes (Batch + Explain were merged/embedded into Forecast).
// Labels are matched case-insensitively to support both EN (default) and PT.
const ROUTES: { path: string; label: RegExp }[] = [
  { path: '/', label: /dashboard/i },
  { path: '/predict', label: /(single prediction|previs[aã]o pontual)/i },
  { path: '/forecast', label: /forecast/i },
  { path: '/monitoring', label: /(monitoring|monitoriza[cç][aã]o)/i },
];

test.describe('Sidebar navigation smoke', () => {
  test('navigates through all four main routes without errors', async ({ page }) => {
    const pageErrors: string[] = [];
    page.on('pageerror', (err) => pageErrors.push(err.message));

    await mockBackend(page);
    await page.goto('/');

    // Any <nav> landmark on the page is fine.
    const nav = page.getByRole('navigation').first();
    await expect(nav).toBeVisible();

    for (const { path, label } of ROUTES) {
      await nav.getByRole('link', { name: label }).first().click();
      await expect(page).toHaveURL(new RegExp(`${path === '/' ? '/$' : path + '$'}`));
      await expect(page.getByRole('main')).toBeVisible();
    }

    expect(pageErrors, pageErrors.join('\n')).toHaveLength(0);
  });
});

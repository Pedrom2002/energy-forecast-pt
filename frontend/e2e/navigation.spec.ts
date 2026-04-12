import { test, expect } from '@playwright/test';
import { mockBackend } from './fixtures/mockApi';

const ROUTES: { path: string; label: RegExp }[] = [
  { path: '/', label: /Dashboard/i },
  { path: '/predict', label: /Previsao/i },
  { path: '/batch', label: /Batch/i },
  { path: '/forecast', label: /Forecast/i },
  { path: '/monitoring', label: /Monitoring/i },
  { path: '/explain', label: /Explicabilidade/i },
];

test.describe('Sidebar navigation smoke', () => {
  test('navigates through all six main routes without errors', async ({ page }) => {
    const pageErrors: string[] = [];
    page.on('pageerror', (err) => pageErrors.push(err.message));

    await mockBackend(page);
    await page.goto('/');

    // Confirm the nav landmark is present.
    const nav = page.getByRole('navigation', { name: /Navegacao principal/i });
    await expect(nav).toBeVisible();

    for (const { path, label } of ROUTES) {
      // Click the matching NavLink inside the sidebar.
      await nav.getByRole('link', { name: label }).first().click();
      await expect(page).toHaveURL(new RegExp(`${path === '/' ? '/$' : path}$`));
      // Wait until a page has rendered something (main landmark is always
      // present; we just ensure no pageerror has fired).
      await expect(page.getByRole('main')).toBeVisible();
    }

    expect(pageErrors, pageErrors.join('\n')).toHaveLength(0);
  });
});

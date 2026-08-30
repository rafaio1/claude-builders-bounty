import { test, expect } from '@playwright/test';

test.describe('Smoke tests', () => {
  test('homepage loads and shows main heading', async ({ page }) => {
    await page.goto('/');
    await expect(page).toHaveTitle(/Lilly/);
    const body = page.locator('body');
    await expect(body).toBeVisible();
  });

  test('/docs route loads', async ({ page }) => {
    await page.goto('/docs');
    await expect(page).toHaveURL(/.*docs/);
    const body = page.locator('body');
    await expect(body).toBeVisible();
  });

  test('/app route loads', async ({ page }) => {
    await page.goto('/app');
    await expect(page).toHaveURL(/.*app/);
    const body = page.locator('body');
    await expect(body).toBeVisible();
  });
});

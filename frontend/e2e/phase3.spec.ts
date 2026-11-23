import { expect, test } from '@playwright/test';

const login = async (page: import('@playwright/test').Page) => {
  await page.goto('/workspace/dashboard');
};

test('phase 3 launch readiness workspace renders release gates', async ({ page }) => {
  await login(page);
  await page.goto('/workspace/launch');
  await expect(page.getByText('Enterprise Launch Readiness')).toBeVisible();
  await expect(page.getByText('Final release gate evidence')).toBeVisible();
  await expect(page.getByText('Launch claim boundaries')).toBeVisible();
});

test('phase 3 command palette exposes launch readiness action', async ({ page }) => {
  await login(page);
  await page.keyboard.press(process.platform === 'darwin' ? 'Meta+K' : 'Control+K');
  await page.getByPlaceholder('Search products, vendors, documents, or actions…').fill('launch');
  await expect(page.getByRole('link', { name: 'Launch readiness', exact: true }).first()).toBeVisible();
});

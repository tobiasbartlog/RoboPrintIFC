import { expect, test } from '@playwright/test';

test('Startseite laedt', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'RoboPrintIFC' })).toBeVisible();
});

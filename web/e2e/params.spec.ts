import { expect, test } from '@playwright/test';

/** Druckeinstellungen bei 1280 × 800: Knopf sticky am Seitenleistenrand, kein Überlauf, hell und dunkel. */
test('Druckeinstellungen: Knopf im Bild, kein Überlauf, hell und dunkel', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto('/?fake=ok');
  await page.getByTestId('example-demo').click();
  await page.getByTestId('wall-select-box').check();
  await page.getByTestId('to-decompose').click();

  await page.getByTestId('param-mode').getByText('Alle').click();
  for (const id of ['layer', 'module', 'speed', 'pump', 'motion', 'clearance', 'planning', 'control']) {
    await page.getByTestId(`param-group-${id}`).click();
  }

  for (const scheme of ['light', 'dark'] as const) {
    if ((await page.locator('html').getAttribute('data-mantine-color-scheme')) !== scheme) {
      await page.getByTestId('color-scheme-toggle').click();
    }
    await expect(page.locator('html')).toHaveAttribute('data-mantine-color-scheme', scheme);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
    expect(overflow, `horizontaler Überlauf (${scheme})`).toBe(false);
    await expect(page.getByTestId('start-job')).toBeInViewport();
    // sticky: bleibt auch bei ganz aufgeklapptem Panel am unteren Rand der Seitenleiste
    const bar = await page.getByTestId('start-job-bar').boundingBox();
    expect(bar).not.toBeNull();
    expect(bar!.y + bar!.height).toBeLessThanOrEqual(800);
    expect(bar!.y + bar!.height).toBeGreaterThan(740);
  }
});

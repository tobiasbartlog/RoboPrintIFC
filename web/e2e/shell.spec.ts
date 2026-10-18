import { expect, test } from '@playwright/test';

/**
 * Glückspfad der Shell gegen die Fake-API (Query ?fake=ok: Fixture run_demo, alle Teile machbar).
 * ?fake=1 liefert das Fixture unverändert (Teil nicht machbar).
 */
const shot = (name: string) => `e2e/screenshots/${name}.png`;

test('Glückspfad: Modell, Zerlegen & prüfen, Simulation, Export', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto('/?fake=ok');

  // 1 Modell
  await expect(page.getByTestId('step-model-panel')).toBeVisible();
  await expect(page.getByTestId('step-decompose')).toBeDisabled();
  await expect(page.getByTestId('to-decompose-reason')).toBeVisible();
  await page.getByTestId('example-demo').click();
  await expect(page.getByTestId('wall-row-box')).toBeVisible();
  await expect(page.getByTestId('wall-reason-duenn')).toContainText('24 mm');
  await expect(page.getByTestId('wall-select-duenn')).toBeDisabled();
  await page.getByTestId('wall-select-box').check();
  await expect(page.getByTestId('step-model')).toHaveAttribute('data-status', 'aktuell');
  await page.screenshot({ path: shot('1-modell') });

  // 2 Zerlegen & prüfen
  await page.getByTestId('to-decompose').click();
  await page.getByTestId('params-toggle').click();
  await expect(page.getByTestId('param-assumption-t_tot_s')).toContainText('provisorisch');
  await page.getByTestId('start-job').click();
  await expect(page.getByTestId('job-progress')).toBeVisible();
  await expect(page.getByTestId('part-list')).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId('part-status-P01')).toHaveText('machbar');
  await expect(page.getByTestId('part-dmin-P01')).toContainText('mm');
  await expect(page.getByTestId('samples-count')).toBeVisible();
  await expect(page.getByTestId('step-decompose')).toHaveAttribute('data-status', 'aktuell');
  await page.screenshot({ path: shot('2-zerlegen') });

  // Veraltet-Logik: Parameter ändern markiert Ergebnisse, Zurücksetzen stellt wieder her
  await page.getByTestId('param-v_print_mm_s').fill('120');
  await expect(page.getByTestId('step-export')).toHaveAttribute('data-status', 'veraltet');
  await expect(page.getByTestId('stale-banner')).toBeVisible();
  await page.getByTestId('param-reset-v_print_mm_s').click();
  await expect(page.getByTestId('step-export')).toHaveAttribute('data-status', 'aktuell');

  // 3 Simulation
  await page.getByTestId('to-simulation').click();
  await expect(page.getByTestId('step-simulation-panel')).toBeVisible();
  await expect(page.getByTestId('scene-view')).toBeVisible();
  await expect(page.getByTestId('player-panel')).toBeVisible();
  await page.getByTestId('sim-part-P01').click();
  await expect(page.getByTestId('sim-selected')).toContainText('P01');
  await page.screenshot({ path: shot('3-simulation') });

  // 4 Export
  await page.getByTestId('to-export').click();
  await expect(page.getByTestId('export-dry-run-note')).toContainText('Trockenlauf');
  await expect(page.getByTestId('export-assumptions')).toContainText('Schichthöhe 10 mm');
  const [dl] = await Promise.all([page.waitForEvent('download'), page.getByTestId('download-P01-v2').click()]);
  expect(dl.suggestedFilename()).toMatch(/P01\.v2\.drl$/);
  await page.getByTestId('view-P01-v3').click();
  await expect(page.getByTestId('drl-preview')).toContainText('Dialekt v3');
  await page.screenshot({ path: shot('4-export') });
});

test('Fixture unverändert: nicht machbares Teil zeigt die Ursache', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto('/?fake=1');
  await page.getByTestId('example-demo').click();
  await page.getByTestId('wall-select-box').check();
  await page.getByTestId('to-decompose').click();
  await page.getByTestId('start-job').click();
  await expect(page.getByTestId('part-status-P01')).toHaveText('nicht machbar', { timeout: 15_000 });
  await expect(page.getByTestId('part-cause-P01')).toContainText('Werkzeug');
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
  expect(overflow).toBe(false);
});

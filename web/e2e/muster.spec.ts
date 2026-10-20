import { rmSync } from 'node:fs';
import { join } from 'node:path';
import { expect, test } from '@playwright/test';

/**
 * Musterersteller gegen die echte API (`/api/patterns`): Muster wählen, Regler ziehen, die Vorschau
 * ändert sich, als Muster speichern, SVG exportieren. Der Browser rechnet nichts; er zeichnet die
 * Antwort des Kerns.
 */
const shot = (name: string) => `e2e/screenshots/${name}.png`;

interface Catalog {
  patterns: { name: string; label: string; params: { name: string }[] }[];
}

test('Musterersteller: wählen, ziehen, Vorschau ändert sich, speichern', async ({ page, request }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  const catalog = (await (await request.get('/api/patterns')).json()) as Catalog;
  // Die Fugenwand ist das Hauptmuster; fehlt sie (frühe Stände), genügt das Grundmuster.
  const info = catalog.patterns.find((p) => p.name === 'fugenwand') ?? catalog.patterns[0]!;

  await page.goto('/');
  await expect(page.getByTestId('view-switch')).toBeVisible();
  await page.getByTestId('view-pattern').click();
  await expect(page.getByTestId('pattern-workspace')).toBeVisible();
  await expect(page.getByTestId('pattern-svg')).toBeVisible();

  // Muster wählen
  await page.getByTestId('pattern-select').click();
  await page.getByRole('option', { name: info.label, exact: true }).click();
  await expect(page.getByTestId('pattern-select')).toHaveValue(info.label);
  await expect(page.getByTestId('pattern-svg')).toBeVisible();
  await expect(page.getByTestId('pat-path').first()).toBeVisible();
  await expect(page.getByTestId('pattern-legend')).toBeVisible();
  await expect(page.getByTestId('pat-start')).toBeVisible();
  await expect(page.getByTestId('pat-stat-length')).toContainText(/\d/);

  await expect(page.getByTestId('pattern-busy')).toHaveCount(0);
  await page.screenshot({ path: shot('muster') });

  // Regler ziehen: erster Regler des Musters, sonst die Strangbreite
  const first = info.params[0]?.name ?? 'bead_width_mm';
  const control = page.getByTestId(`pat-param-${first}`);
  await control.scrollIntoViewIfNeeded();
  const input = page.getByTestId(`pat-param-${first}-input`);
  const before = {
    value: await input.inputValue(),
    svg: await page.getByTestId('pattern-svg').innerHTML(),
    length: await page.getByTestId('pat-stat-length').innerText(),
  };
  const thumb = control.getByRole('slider');
  const box = (await thumb.boundingBox())!;
  const track = (await control.locator('.mantine-Slider-root').boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(track.x + track.width * 0.8, box.y + box.height / 2, { steps: 8 });
  await page.mouse.up();
  await expect(input).not.toHaveValue(before.value);
  await expect(page.getByTestId(`pat-param-${first}-reset`)).toBeVisible();
  await expect
    .poll(async () => (await page.getByTestId('pattern-svg').innerHTML()) !== before.svg || (await page.getByTestId('pat-stat-length').innerText()) !== before.length, {
      timeout: 10_000,
    })
    .toBe(true);
  await expect(page.getByTestId('pattern-busy')).toHaveCount(0);
  await expect(page.getByTestId('pattern-timing')).toBeVisible();

  await page.screenshot({ path: shot('muster-regler') });

  // Maße: Modullänge ändern, die Vorschau zeigt den neuen Querschnitt (viewBox = Länge + 2 Rand)
  const widthOf = async () => Number((await page.getByTestId('pattern-svg').getAttribute('viewBox'))!.split(' ')[2]);
  const w600 = await widthOf();
  await page.getByTestId('pattern-length').fill('900');
  await expect.poll(widthOf, { timeout: 10_000 }).toBeCloseTo(w600 + 300, 0);
  await expect(page.getByTestId('pattern-busy')).toHaveCount(0);
  await expect(page.getByTestId('pattern-error')).toHaveCount(0);

  // Server fällt aus: Klartext mit Handlung, letzte Vorschau bleibt, Neu-Anfordern hilft
  await page.route('**/api/patterns/preview*', (route) => route.abort('connectionrefused'));
  await page.getByTestId('pattern-length').fill('800');
  await expect(page.getByTestId('pattern-error')).toHaveAttribute('data-kind', 'server');
  await expect(page.getByTestId('pattern-svg')).toBeVisible();
  await page.unroute('**/api/patterns/preview*');
  await page.getByTestId('pattern-retry').click();
  await expect(page.getByTestId('pattern-error')).toHaveCount(0);
  await expect.poll(widthOf, { timeout: 10_000 }).toBeCloseTo(w600 + 200, 0);
  await page.getByTestId('pattern-length').fill('900');
  await expect.poll(widthOf, { timeout: 10_000 }).toBeCloseTo(w600 + 300, 0);

  // Dunkelmodus bleibt lesbar
  await page.getByTestId('color-scheme-toggle').click();
  await expect(page.getByTestId('pattern-svg')).toBeVisible();
  await page.screenshot({ path: shot('muster-dunkel') });
  await page.getByTestId('color-scheme-toggle').click();

  // Speichern als benanntes Muster
  const name = `E2E Muster ${Date.now()}`;
  await expect(page.getByTestId('pattern-save-button')).toBeDisabled();
  await expect(page.getByTestId('pattern-save-reason')).toBeVisible();
  await page.getByTestId('pattern-save-name').fill(name);
  await page.getByTestId('pattern-save-button').click();
  await expect(page.getByTestId('pattern-saved')).toContainText(name);
  const presets = (await (await request.get('/api/patterns/presets')).json()) as { id: string; source: string; preset: { name: string; pattern: string } }[];
  const mine = presets.find((p) => p.preset.name === name && p.preset.pattern === info.name);
  expect(mine).toBeDefined();
  // Aufräumen: Die API kennt kein Löschen; eigene Presets liegen als <id>.json unter runs/presets.
  if (mine?.source === 'user') rmSync(join(test.info().config.rootDir, '..', '..', 'runs', 'presets', `${mine.id}.json`), { force: true });

  // SVG-Export
  const download = page.waitForEvent('download');
  await page.getByTestId('pattern-export-svg').click();
  expect((await download).suggestedFilename()).toMatch(/^muster-.*\.svg$/);

  // Kein horizontaler Überlauf bei 1280 x 800
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});

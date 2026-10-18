import { expect, test } from '@playwright/test';

/**
 * Player gegen die Fake-API (Fixture run_demo, nicht FK-konsistent): alles außer der
 * Uhr-Invariante. Die Gate-Prüfung mit echten Läufen steht in g6.spec.ts.
 */
test.use({ launchOptions: { args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] } });

test('Direkteinstieg, Timeline, Kollisionsliste, Klick pausiert und hebt hervor', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto('/?fake=1&run=run_demo&part=P01');
  await expect(page.getByTestId('step-simulation-panel')).toBeVisible();
  await expect(page.getByTestId('direct-run')).toContainText('run_demo');
  await page.waitForFunction(() => window.__roboprint?.ready() === true, undefined, { timeout: 60_000 });

  // Timeline: Bereiche statt Punkte
  await expect(page.locator('[data-testid="timeline-status"] > div[data-value="collision"]').first()).toBeAttached();
  await expect(page.locator('[data-testid="timeline-status"] > div[data-value="unreachable"]').first()).toBeAttached();
  await expect(page.locator('[data-testid="timeline-kind"] > div[data-value="print"]').first()).toBeAttached();

  // Debug-Schnittstelle: genau die Felder aus SPEC §9
  const d0 = await page.evaluate(() => window.__roboprint!.debug());
  expect(Object.keys(d0).sort()).toEqual(['highlightedLinks', 'obstacleVisible', 'sampleIndex', 'status', 't', 'tcpArtifact', 'tcpRendered'].sort());
  expect(d0.sampleIndex).toBe(0);
  expect(d0.tcpRendered).toHaveLength(3);

  // Abspielen bewegt die Uhr
  await page.getByTestId('player-play').click();
  await expect.poll(() => page.evaluate(() => window.__roboprint!.debug().t)).toBeGreaterThan(0.3);

  // Kollisionsliste
  await expect(page.getByTestId('collision-title')).toHaveText(/^Kollisionen \([1-9]\d*\)$/);
  const item = page.getByTestId('collision-item-0');
  const link = (await item.getAttribute('data-link'))!;
  const tItem = Number(await item.getAttribute('data-t'));
  await item.click();
  await expect(page.getByTestId('player-play')).toBeVisible();
  const d = await page.evaluate(() => window.__roboprint!.debug());
  expect(d.t).toBeCloseTo(tItem, 6);
  expect(d.status).toBe('collision');
  expect(d.highlightedLinks).toEqual([link]);
  expect(d.obstacleVisible).toBe(true);
  await expect(page.getByTestId('player-status')).toHaveText('Kollision');
  await expect(page.getByTestId('player-distance')).toContainText('mm');

  // seek setzt die Uhr und liefert den neuen Stand
  const ds = await page.evaluate(() => window.__roboprint!.seek(0));
  expect(ds.sampleIndex).toBe(0);
  await page.waitForTimeout(300);
  await item.click();
  await page.waitForTimeout(800);
  await page.screenshot({ path: 'e2e/screenshots/player-kollision.png' });

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
  expect(overflow).toBe(false);
  expect(errors).toEqual([]);
});

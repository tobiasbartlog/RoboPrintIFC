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

/** Druckplatz: Ziehen rastet auf 50 mm ein, Pfeiltasten verschieben, Zurücksetzen führt zum Standard. */
test('Druckplatz: Ziehen, Pfeiltasten, Zurücksetzen', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto('/?fake=ok');
  await page.getByTestId('example-demo').click();
  await page.getByTestId('wall-select-box').check();
  await page.getByTestId('to-decompose').click();
  await page.getByTestId('param-group-module').click();

  const desc = page.getByTestId('spot-desc');
  await expect(desc).toContainText('50 mm vor der Tischmitte, mittig · 535 mm vor der Roboterachse · Standard, empfohlen');
  const field = page.getByTestId('spot-field');
  await field.scrollIntoViewIfNeeded();
  const box = (await field.boundingBox())!;
  // viewBox 1680 × 1330 mm, links oben (−840, 665): Modulmitte (0, −50) um 150 mm nach rechts und 110 mm nach vorn
  const at = (x: number, y: number) => [box.x + (box.width * (x + 840)) / 1680, box.y + (box.height * (665 - y)) / 1330] as const;
  await page.mouse.move(...at(0, -50));
  await page.mouse.down();
  await page.mouse.move(...at(150, -160), { steps: 8 });
  await page.mouse.up();
  await expect(desc).toContainText('150 mm vor der Tischmitte, 150 mm rechts · 635 mm vor der Roboterachse');
  await field.press('ArrowLeft');
  await expect(desc).toContainText('150 mm vor der Tischmitte, 100 mm rechts');
  await expect(page.getByTestId('param-group-changed-module')).toHaveText('1 geändert');
  await page.getByTestId('spot-reset').click();
  await expect(desc).toContainText('Standard, empfohlen');
});

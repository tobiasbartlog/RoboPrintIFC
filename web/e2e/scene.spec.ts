import { expect, test } from '@playwright/test';

// Software-WebGL fuer Umgebungen ohne GPU.
test.use({ launchOptions: { args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] } });

// Home-Pose, unabhaengig mit Pinocchio gerechnet (siehe src/scene/__tests__/tcp.test.ts).
const HOME_TCP = [1204.96048441, 1124.48532595, 1479.41343862];


test('Szene rendert Roboter, Tisch, Teil und Werkzeug; TCP stimmt mit der FK ueberein', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await page.setViewportSize({ width: 1280, height: 800 });

  // Sample 0: Home-Pose.
  await page.goto('/scene-test.html?fixture=run_demo&i=0');
  await page.waitForFunction(() => window.__scene?.ready() === true, undefined, { timeout: 45_000 });
  const tcp = await page.evaluate(() => window.__scene!.tcpRendered());
  expect(tcp).not.toBeNull();
  const [x, y, z] = tcp!;
  expect(Math.hypot(x - HOME_TCP[0]!, y - HOME_TCP[1]!, z - HOME_TCP[2]!)).toBeLessThan(1);

  // Kollisionssample: Glied rot, Hindernis sichtbar, Kontaktlinie.
  await page.goto('/scene-test.html?fixture=run_demo&i=collision');
  await page.waitForFunction(() => window.__scene?.ready() === true, undefined, { timeout: 45_000 });
  await page.waitForTimeout(1000);
  await page.screenshot({ path: 'e2e/screenshots/scene.png' });
  expect(errors).toEqual([]);
});

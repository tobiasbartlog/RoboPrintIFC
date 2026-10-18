import { expect, test, type APIRequestContext, type Page } from '@playwright/test';

/**
 * Gate G6 (SPEC §11) gegen die echte API (kein ?fake) mit den Läufen S1 und S3.
 *
 * - Die Läufe liegen unter `runs/verify/S1` und `runs/verify/S3` (run_id `verify/S1`, `verify/S3`),
 *   erzeugt von `python scripts/verify.py`. Fehlen sie, schlägt G6 mit Meldung fehl (kein Skip).
 *   Zum Entwickeln lassen sich andere Läufe setzen: G6_RUN_S1, G6_RUN_S3.
 * - Glückspfad: Projekt (Beispiel-IFC über die echte API) → Wand → „Zerlegen & prüfen“ → alle
 *   Teile grün → Wiedergabe → Export. Ein echter Job dauert Minuten; deshalb beantwortet der Test
 *   per default nur die beiden Job-Endpunkte selbst (POST …/jobs, GET /api/jobs/…) und verweist
 *   auf den fertigen Lauf S1. Alles andere (Projekt, Wände, Artefakte, Assets, DRL) kommt von
 *   der echten API. Mit G6_REAL_JOB=1 läuft der echte Job (bis 30 min).
 * - Kollisionspfad S3 und Uhr-Invariante nutzen den Direkteinstieg `/?run=<id>&part=<id>`.
 */
const RUN_S1 = process.env.G6_RUN_S1 ?? 'verify/S1';
const RUN_S3 = process.env.G6_RUN_S3 ?? 'verify/S3';
const REAL_JOB = process.env.G6_REAL_JOB === '1';
const shot = (name: string) => `e2e/screenshots/${name}.png`;

test.use({ launchOptions: { args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] } });

interface PartEntry {
  part_id: string;
  status: string;
  n_collision: number;
}
interface Traj {
  t_s: number[];
  status: string[];
  tcp: number[][];
}

async function requireRun(request: APIRequestContext, runId: string): Promise<PartEntry[]> {
  const res = await request.get('/api/runs');
  expect(res.ok(), 'API /api/runs nicht erreichbar').toBe(true);
  const runs = (await res.json()) as string[];
  expect(
    runs,
    `G6 braucht den echten Lauf "${runId}" unter runs/${runId} (erst "python scripts/verify.py" laufen lassen). ` +
      `Vorhanden: ${runs.length ? runs.join(', ') : 'keine Läufe'}`,
  ).toContain(runId);
  const summary = (await (await request.get(`/api/runs/${runId}/summary.json`)).json()) as { parts: PartEntry[] };
  expect(summary.parts.length, `Lauf ${runId} hat keine Teile`).toBeGreaterThan(0);
  return summary.parts;
}

async function loadTraj(request: APIRequestContext, runId: string, partId: string): Promise<Traj> {
  return (await (await request.get(`/api/runs/${runId}/parts/${partId}/trajectory.json`)).json()) as Traj;
}

async function waitReady(page: Page) {
  await page.waitForFunction(() => window.__roboprint?.ready() === true, undefined, { timeout: 60_000 });
}

/** Unabhängige Referenz zur binären Suche im Viewer: letztes i mit t_s[i] ≤ t. */
function linearIndex(tS: number[], t: number): number {
  let i = 0;
  for (let k = 0; k < tS.length; k++) if ((tS[k] ?? Infinity) <= t) i = k;
  return i;
}

/** Deterministischer Zufall (mulberry32), damit Fehlschläge reproduzierbar sind. */
function rng(seed: number) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let x = Math.imul(a ^ (a >>> 15), 1 | a);
    x = (x + Math.imul(x ^ (x >>> 7), 61 | x)) ^ x;
    return ((x ^ (x >>> 14)) >>> 0) / 4294967296;
  };
}

test('G6 Glückspfad: Projekt → Wand → Zerlegen & prüfen → alle Teile grün → Wiedergabe → Export', async ({ page, request }) => {
  test.setTimeout(REAL_JOB ? 1_900_000 : 180_000);
  if (!REAL_JOB) await requireRun(request, RUN_S1);
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await page.setViewportSize({ width: 1280, height: 800 });

  if (!REAL_JOB) {
    await page.route('**/api/projects/*/jobs', (route) =>
      route.request().method() === 'POST' ? route.fulfill({ status: 202, json: { job_id: 'g6s1' } }) : route.fallback(),
    );
    let polls = 0;
    await page.route('**/api/jobs/g6s1', (route) => {
      polls++;
      const done = polls >= 2;
      return route.fulfill({
        json: done
          ? { state: 'done', progress: 1, stage: 'Prüfen', message: null, run_id: RUN_S1 }
          : { state: 'running', progress: 0.5, stage: 'Planen', message: 'Teil 1', run_id: null },
      });
    });
  }

  await page.goto('/');
  // 1 Modell: Beispiel-IFC über die echte API
  const ifc = page.locator('[data-testid^="example-"]', { hasText: 'Building-Architecture' }).first();
  await ifc.click();
  await expect(page.getByTestId('wall-list')).toBeVisible({ timeout: 60_000 });
  const eligible = page.locator('[data-testid^="wall-row-"][data-eligible="true"]').first();
  await expect(eligible, 'Das Beispiel-IFC hat keine geeignete Wand').toBeVisible();
  await eligible.locator('[data-testid^="wall-select-"]').check();
  await expect(page.getByTestId('step-model')).toHaveAttribute('data-status', 'aktuell');
  await page.screenshot({ path: shot('g6-1-modell') });

  // 2 Zerlegen & prüfen
  await page.getByTestId('to-decompose').click();
  await page.getByTestId('start-job').click();
  await expect(page.getByTestId('part-list')).toBeVisible({ timeout: REAL_JOB ? 1_800_000 : 30_000 });
  const statuses = page.locator('[data-testid^="part-status-"]');
  const n = await statuses.count();
  expect(n).toBeGreaterThan(0);
  for (let k = 0; k < n; k++) await expect(statuses.nth(k)).toHaveText('machbar');
  await expect(page.getByTestId('step-decompose')).toHaveAttribute('data-status', 'aktuell');
  await page.screenshot({ path: shot('g6-2-zerlegen') });

  // 3 Wiedergabe
  await page.getByTestId('to-simulation').click();
  await waitReady(page);
  await expect(page.getByTestId('collision-title')).toHaveText('Kollisionen (0)');
  await page.getByTestId('player-speed').click();
  await page.getByRole('option', { name: '10×' }).click();
  await page.getByTestId('player-play').click();
  await expect.poll(async () => (await page.evaluate(() => window.__roboprint!.debug().t)), { timeout: 10_000 }).toBeGreaterThan(1);
  await page.getByTestId('player-pause').click();
  const st = await page.evaluate(() => window.__roboprint!.debug().status);
  expect(['ok', 'warn']).toContain(st);
  await page.screenshot({ path: shot('g6-3-wiedergabe') });

  // 4 Export
  await page.getByTestId('to-export').click();
  const first = page.locator('[data-testid^="download-"][data-testid$="-v2"]').first();
  const [dl] = await Promise.all([page.waitForEvent('download'), first.click()]);
  expect(dl.suggestedFilename()).toMatch(/\.v2\.drl$/);
  await page.locator('[data-testid^="view-"][data-testid$="-v3"]').first().click();
  await expect(page.getByTestId('drl-preview')).not.toBeEmpty();
  await page.screenshot({ path: shot('g6-4-export') });
  expect(errors).toEqual([]);
});

test('G6 Kollisionspfad S3: Liste, Klick pausiert, Glied hervorgehoben, Hindernis sichtbar', async ({ page, request }) => {
  const parts = await requireRun(request, RUN_S3);
  const part = parts.find((p) => p.n_collision > 0);
  expect(part, `Lauf ${RUN_S3} meldet keine Kollision`).toBeTruthy();
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto(`/?run=${encodeURIComponent(RUN_S3)}&part=${part!.part_id}`);
  await waitReady(page);

  const title = page.getByTestId('collision-title');
  await expect(title).toHaveText(/^Kollisionen \(\d+\)$/);
  const count = Number(/\((\d+)\)/.exec((await title.textContent()) ?? '')?.[1]);
  expect(count).toBeGreaterThan(0);

  // Abspielen, dann Klick auf den ersten Eintrag: pausiert bei t des kritischsten Samples.
  await page.getByTestId('player-play').click();
  const item = page.getByTestId('collision-item-0');
  const link = (await item.getAttribute('data-link'))!;
  const tItem = Number(await item.getAttribute('data-t'));
  await item.click();
  await expect(page.getByTestId('player-play')).toBeVisible();
  await waitReady(page);
  const d = await page.evaluate(() => window.__roboprint!.debug());
  expect(d.t).toBeCloseTo(tItem, 6);
  expect(d.status).toBe('collision');
  expect(d.highlightedLinks).toContain(link);
  expect(d.obstacleVisible).toBe(true);
  await page.waitForTimeout(500);
  await page.screenshot({ path: shot('g6-s3-kollision') });
  // Bleibt pausiert.
  await page.waitForTimeout(300);
  expect(await page.evaluate(() => window.__roboprint!.debug().t)).toBeCloseTo(tItem, 6);
});

test('G6 Uhr-Invariante: 50 Zufalls-t, |tcpRendered − tcpArtifact| ≤ 1 mm, Status passt zum Sample', async ({ page, request }) => {
  for (const runId of [RUN_S3, RUN_S1]) {
    const parts = await requireRun(request, runId);
    const partId = parts[0]!.part_id;
    const tr = await loadTraj(request, runId, partId);
    await page.goto(`/?run=${encodeURIComponent(runId)}&part=${partId}`);
    await waitReady(page);
    const end = tr.t_s[tr.t_s.length - 1] ?? 0;
    const rand = rng(runId.length * 7919 + 6);
    let checkedTcp = 0;
    for (let k = 0; k < 50; k++) {
      const t = rand() * end;
      const d = await page.evaluate((tq) => window.__roboprint!.seek(tq), t);
      const i = linearIndex(tr.t_s, t);
      expect(d.sampleIndex, `${runId} t=${t}`).toBe(i);
      expect(d.status, `${runId} t=${t}`).toBe(tr.status[i]);
      await expect(page.getByTestId('player-readout')).toHaveAttribute('data-status', tr.status[i]!);
      expect(d.tcpArtifact).toEqual(tr.tcp[i]!.slice(0, 3));
      // Bei `unreachable` trägt q nur die letzte gültige Lösung zur Anzeige (ARTEFAKTE.md);
      // tcp ist dort die Sollpose, die FK-Gleichheit gilt nicht.
      if (tr.status[i] === 'unreachable') continue;
      expect(d.tcpRendered, `${runId} t=${t}: Szene nicht bereit`).not.toBeNull();
      const [a, b] = [d.tcpRendered!, d.tcpArtifact!];
      const err = Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
      expect(err, `${runId} t=${t.toFixed(3)} Sample ${i}: |tcpRendered − tcpArtifact| = ${err.toFixed(3)} mm`).toBeLessThanOrEqual(1);
      checkedTcp++;
    }
    expect(checkedTcp, `${runId}: zu wenige erreichbare Samples geprüft`).toBeGreaterThan(25);
  }
  await page.screenshot({ path: shot('g6-uhr') });
});

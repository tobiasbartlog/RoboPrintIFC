import { execFileSync } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { expect, test, type Page } from '@playwright/test';

/**
 * Musterwahl im Ablauf („Zerlegen & prüfen“) gegen die echte API und den echten Kern.
 *
 * - Die Wahl in der Oberfläche geht als Jobparameter an `POST /api/projects/{id}/jobs`. Der Test fängt
 *   den Aufruf ab, rechnet mit genau diesen Parametern einen kleinen Quader (600 × 200 × 60 mm) über
 *   `python -m roboprint run-scenario` und beantwortet den Job mit diesem Lauf (ein echter Job für
 *   S1 dauert Minuten, wie in g6.spec.ts). Kennzahlen, Schichtvorschau und 3D-Ansicht kommen von
 *   der echten API aus dem echten Lauf.
 * - Der Preset-Pfad (`pattern_preset` als id) geht ohne Abfangen an die API; der Job wird gleich
 *   danach abgebrochen.
 */
const shot = (name: string) => `e2e/screenshots/${name}.png`;
const python = process.env.ROBOPRINT_PYTHON ?? '/opt/fgc-venv/bin/python';
const REPO = resolve('..');
const RUN_DIR = join(REPO, 'runs', 'muster', 'viewer_ablauf');
const RUN_ID = 'muster/viewer_ablauf';

test.use({ launchOptions: { args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] } });

/** Quader-Szenario mit den Jobparametern der Oberfläche rechnen; Laufordner `runs/muster/viewer_ablauf`. */
function computeRun(params: Record<string, unknown>): void {
  const base = JSON.parse(readFileSync(join(REPO, 'spec', 'scenarios', 'S1_modul_referenz.json'), 'utf8')) as Record<string, unknown>;
  const scenario = {
    ...base,
    id: 'muster_viewer_ablauf',
    beschreibung: 'Quader 600 x 200 x 60 mm mit den Jobparametern des Playwright-Tests muster-ablauf.spec.ts',
    source: { kind: 'box', size_mm: [600, 200, 60] },
    params,
    expect: {},
    limits: { wall_time_s: 600 },
  };
  mkdirSync(join(REPO, 'runs', 'muster'), { recursive: true });
  const file = join(REPO, 'runs', 'muster', 'viewer_ablauf.scenario.json');
  writeFileSync(file, JSON.stringify(scenario, null, 2));
  rmSync(RUN_DIR, { recursive: true, force: true });
  execFileSync(python, ['-m', 'roboprint', 'run-scenario', file, '--out', RUN_DIR, '--jobs', '1'], {
    cwd: REPO,
    env: { ...process.env, PYTHONPATH: join(REPO, 'core', 'src') },
    timeout: 600_000,
    stdio: 'pipe',
  });
  expect(existsSync(join(RUN_DIR, 'summary.json'))).toBe(true);
}

async function openBox(page: Page) {
  await page.goto('/');
  await page.getByTestId('example-S1_modul_referenz').click();
  await expect(page.getByTestId('wall-list')).toBeVisible({ timeout: 60_000 });
  await page.getByTestId('wall-select-box').check();
  await page.getByTestId('to-decompose').click();
  await expect(page.getByTestId('pattern-choice')).toBeVisible();
}

async function choose(page: Page, label: string) {
  await page.getByTestId('pattern-choice-select').click();
  await page.getByRole('option', { name: label, exact: true }).click();
  await expect(page.getByTestId('pattern-choice-select')).toHaveValue(label);
}

test('Musterwahl im Ablauf: Sinus-Infill wählen, rechnen, Kennzahlen, Schichtvorschau, 3D-Legende', async ({ page, request }) => {
  test.setTimeout(420_000);
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await page.setViewportSize({ width: 1280, height: 800 });

  let body: { wall_id: string; params: Record<string, unknown> } | null = null;
  await page.route('**/api/projects/*/jobs', async (route) => {
    if (route.request().method() !== 'POST') return route.fallback();
    body = route.request().postDataJSON() as typeof body;
    computeRun(body!.params);
    return route.fulfill({ status: 202, json: { job_id: 'musterablauf' } });
  });
  await page.route('**/api/jobs/musterablauf', (route) =>
    route.fulfill({ json: { state: 'done', progress: 1, stage: 'Prüfen', message: null, run_id: RUN_ID } }),
  );

  await openBox(page);
  // Standard: kein Muster, nichts geändert
  await expect(page.getByTestId('pattern-choice-select')).toHaveValue('Kein Muster (Standard)');
  await expect(page.getByTestId('pattern-choice-changed')).toHaveCount(0);
  // Der Katalog der API bietet die Muster an
  const catalog = (await (await request.get('/api/patterns')).json()) as { patterns: { name: string; label: string; role: string }[] };
  const sinus = catalog.patterns.find((p) => p.name === 'sinus');
  expect(sinus, 'Der Kern liefert kein Muster „sinus“').toBeTruthy();
  await choose(page, sinus!.label);
  await page.getByTestId('pattern-choice-order').getByText('wechselnd', { exact: true }).click();
  await expect(page.getByTestId('pattern-choice-changed')).toContainText('2 geändert');
  await expect(page.getByTestId('pattern-choice-summary')).toContainText('Schichtfolge wechselnd');
  await page.screenshot({ path: shot('muster-ablauf-wahl') });

  await page.getByTestId('start-job').click();
  await expect(page.getByTestId('part-list')).toBeVisible({ timeout: 360_000 });
  expect(body!.params).toMatchObject({ infill_pattern: 'sinus', layer_order: 'alternate' });
  expect(body!.params).not.toHaveProperty('pattern_preset');
  await expect(page.getByTestId('step-decompose')).toHaveAttribute('data-status', 'aktuell');

  // Kennzahlen aus der API
  const stats = page.locator('[data-testid^="pattern-stats-"][data-has-pattern]');
  await expect(stats).toBeVisible();
  await expect(stats).toHaveAttribute('data-has-pattern', 'true');
  await expect(stats).toContainText('Sinuswelle');
  await expect(stats).toContainText('wechselnd');
  await expect(stats).toContainText('ein Strang (kein Absetzen)');
  await expect(stats).toContainText('5 senkrecht');
  await expect(stats.locator('[data-testid*="-kind-"][data-testid$="-infill"]')).toContainText('%');

  // Schichtvorschau: Pfad nach Segmentart, Richtung, Start/Ende, Nachbarschicht blass
  const svg = page.getByTestId('layer-preview-svg');
  await expect(svg).toBeVisible();
  await expect(svg).toHaveAttribute('data-layer', '0');
  await expect(page.getByTestId('layer-label')).toContainText('Schicht 1 von 6');
  await expect(page.getByTestId('layer-start')).toBeVisible();
  await expect(page.getByTestId('layer-end')).toBeVisible();
  await expect(page.getByTestId('layer-neighbor')).toBeAttached();
  await expect(page.locator('[data-testid="layer-path"] [data-kind="infill"]').first()).toBeAttached();
  await expect(page.locator('[data-testid="layer-path"] [data-kind="outer"]').first()).toBeAttached();
  await expect(page.getByTestId('layer-kind-infill')).toContainText('Infill');
  const pathOf = async () => page.locator('[data-testid="layer-path"] [data-kind]').evaluateAll((els) => els.map((e) => e.getAttribute('data-kind')));
  const kinds0 = await pathOf();
  await page.getByTestId('layer-next').click();
  await expect(svg).toHaveAttribute('data-layer', '1');
  await expect(page.getByTestId('layer-label')).toContainText('Schicht 2 von 6');
  // alternate: jede zweite Schicht ist die Umkehrung, die Segmente stehen in umgekehrter Reihenfolge
  expect(await pathOf()).toEqual([...kinds0].reverse());
  await page.getByTestId('layer-slider').focus();
  await page.keyboard.press('End');
  await expect(svg).toHaveAttribute('data-layer', '5');
  await page.keyboard.press('Home');
  await expect(svg).toHaveAttribute('data-layer', '0');
  await page.getByTestId('layer-preview').scrollIntoViewIfNeeded();
  await page.screenshot({ path: shot('muster-ablauf-ergebnis') });
  await page.getByTestId('layer-preview').screenshot({ path: shot('muster-schicht') });

  // 3D: Legende mit den Musterarten
  await page.getByTestId('to-simulation').click();
  await page.waitForFunction(() => window.__roboprint?.ready() === true, undefined, { timeout: 90_000 });
  await expect(page.getByTestId('scene-legend')).toBeVisible();
  await expect(page.getByTestId('scene-legend-infill')).toContainText('Infill');
  await expect(page.getByTestId('scene-legend-shells')).toContainText('Schalen');
  await page.getByTestId('player-speed').click();
  await page.getByRole('option', { name: '25×', exact: true }).click();
  await page.getByTestId('player-play').click();
  await expect.poll(async () => page.evaluate(() => window.__roboprint!.debug().t), { timeout: 20_000 }).toBeGreaterThan(20);
  await page.getByTestId('player-pause').click();
  await page.waitForTimeout(500);
  await page.screenshot({ path: shot('muster-3d') });
  expect(errors).toEqual([]);
});

test('Für Lauf verwenden: Muster aus dem Musterersteller landet in „Zerlegen & prüfen“', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto('/?view=muster');
  await expect(page.getByTestId('pattern-svg')).toBeVisible();
  await page.getByTestId('pattern-select').click();
  await page.getByRole('option', { name: 'Sinuswelle', exact: true }).click();
  await expect(page.getByTestId('pattern-select')).toHaveValue('Sinuswelle');
  await expect(page.getByTestId('pattern-svg')).toBeVisible();
  // Ohne Modell: Hinweis nennt den nächsten Schritt, der Knopf führt in den Schritt „Modell“
  await expect(page.getByTestId('pattern-use-hint')).toContainText('Modell und eine Wand');
  await page.screenshot({ path: shot('muster-fuer-lauf') });
  await page.getByTestId('pattern-use-for-run').click();
  await expect(page.getByTestId('view-flow')).toHaveAttribute('aria-selected', 'true');
  await expect(page.getByTestId('example-S1_modul_referenz')).toBeVisible();
  await page.getByTestId('example-S1_modul_referenz').click();
  await expect(page.getByTestId('wall-list')).toBeVisible({ timeout: 60_000 });
  await page.getByTestId('wall-select-box').check();
  await page.getByTestId('to-decompose').click();
  await expect(page.getByTestId('pattern-choice-select')).toHaveValue('Sinuswelle');
  await expect(page.getByTestId('pattern-choice-summary')).toContainText('Sinuswelle');
  await expect(page.getByTestId('pattern-choice-changed')).toBeVisible();

  // Mit Modell springt der Knopf direkt in „Zerlegen & prüfen“
  await page.getByTestId('view-pattern').click();
  await page.getByTestId('pattern-select').click();
  await page.getByRole('option', { name: 'Fugenwand (Sollbruchstellen)', exact: true }).click();
  await expect(page.getByTestId('pattern-use-hint')).toContainText('Zerlegen & prüfen');
  await page.getByTestId('pattern-use-for-run').click();
  await expect(page.getByTestId('pattern-choice-select')).toHaveValue(/Fugenwand/);
  await expect(page.getByTestId('start-job')).toBeVisible();
});

test('Gespeichertes Muster (Preset-id) geht als Jobparameter an die echte API', async ({ page, request }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  const presets = (await (await request.get('/api/patterns/presets')).json()) as { id: string; preset: { name: string } }[];
  const preset = presets.find((p) => p.id === 'fugenwand') ?? presets[0];
  expect(preset, 'Der Kern liefert kein Preset').toBeTruthy();
  await openBox(page);
  await choose(page, `${preset!.preset.name} (Vorlage)`);
  let jobId = '';
  const posted = page.waitForResponse((r) => /\/projects\/[^/]+\/jobs$/.test(r.url()) && r.request().method() === 'POST');
  const req = page.waitForRequest((r) => /\/projects\/[^/]+\/jobs$/.test(r.url()) && r.method() === 'POST');
  await page.getByTestId('start-job').click();
  const sent = (await req).postDataJSON() as { params: Record<string, unknown> };
  expect(sent.params).toMatchObject({ pattern_preset: preset!.id });
  const res = await posted;
  expect(res.status(), await res.text()).toBe(202);
  jobId = ((await res.json()) as { job_id: string }).job_id;
  // Der Server hat die id in eine Datei aufgelöst; der Job läuft an und wird abgebrochen.
  await expect(page.getByTestId('job-progress')).toBeVisible();
  await page.getByTestId('job-cancel').click();
  await expect.poll(async () => ((await (await request.get(`/api/jobs/${jobId}`)).json()) as { state: string }).state, { timeout: 30_000 }).toBe('cancelled');
});

test('Unbekanntes Muster: die API lehnt den Job mit 422 und Klartext ab', async ({ request }) => {
  const created = await request.post('/api/projects', { data: { example_path: 'spec/scenarios/S1_modul_referenz.json' } });
  const pid = ((await created.json()) as { project_id: string }).project_id;
  const res = await request.post(`/api/projects/${pid}/jobs`, { data: { wall_id: 'box', params: { pattern_preset: 'gibt_es_nicht' } } });
  expect(res.status()).toBe(422);
  expect(((await res.json()) as { detail: string }).detail).toContain('gibt_es_nicht');
});

import { createFakeApi } from './fakeApi';
import { createAppStore, isJobRunning, selectStatuses } from './store';

async function until(cond: () => boolean, ms = 3000) {
  const t0 = Date.now();
  while (!cond()) {
    if (Date.now() - t0 > ms) throw new Error('Zeitüberschreitung');
    await new Promise((r) => setTimeout(r, 5));
  }
}

async function ready(mode: 'fixture' | 'ok' = 'ok', polls = 3) {
  const store = createAppStore(createFakeApi({ mode, polls }), { pollMs: 1 });
  await store.getState().openExample('fixture/run_demo');
  store.getState().selectWall('box');
  return store;
}

describe('Store gegen Fake-API', () => {
  it('Projekt öffnen liefert Wände inklusive ungeeigneter mit Grund', async () => {
    const store = await ready();
    const walls = store.getState().project?.walls ?? [];
    expect(walls.map((w) => w.eligible)).toEqual([true, false]);
    expect(walls[1]?.reason).toMatch(/dick/);
  });

  it('Job läuft über Stufen bis zum Lauf; Status danach aktuell', async () => {
    const store = await ready();
    expect(selectStatuses(store.getState()).decompose).toBe('fehlt');
    const p = store.getState().startJob();
    await until(() => isJobRunning(store.getState()));
    await p;
    await until(() => store.getState().run !== null);
    const s = store.getState();
    expect(s.run?.summary.parts[0]?.status).toBe('machbar');
    expect(s.partId).toBe('P01');
    expect(selectStatuses(s)).toMatchObject({ model: 'aktuell', decompose: 'aktuell', export: 'aktuell' });
  });

  it('Fixture-Modus: Teil nicht machbar mit Ursache', async () => {
    const store = await ready('fixture');
    await store.getState().startJob();
    await until(() => store.getState().run !== null);
    const run = store.getState().run;
    expect(run?.summary.parts[0]?.status).toBe('nicht machbar');
    expect(run?.parts.P01?.cause?.message).toBeTruthy();
  });

  it('Wand- oder Parameteränderung macht Ergebnisse veraltet', async () => {
    const store = await ready();
    await store.getState().startJob();
    await until(() => store.getState().run !== null);
    store.getState().setParam('v_print_mm_s', 120);
    expect(selectStatuses(store.getState()).export).toBe('veraltet');
    store.getState().resetParam('v_print_mm_s');
    expect(selectStatuses(store.getState()).export).toBe('aktuell');
    store.getState().selectWall('duenn');
    expect(selectStatuses(store.getState()).simulation).toBe('veraltet');
  });

  it('Abbrechen beendet den Job ohne Lauf', async () => {
    const store = createAppStore(createFakeApi({ polls: 50 }), { pollMs: 1 });
    await store.getState().openExample('fixture/run_demo');
    store.getState().selectWall('box');
    const p = store.getState().startJob();
    await until(() => store.getState().job.jobId !== null);
    await store.getState().cancelJob();
    await p;
    await until(() => store.getState().job.state?.state === 'cancelled');
    expect(store.getState().run).toBeNull();
  });

  it('neues Projekt verwirft den Lauf', async () => {
    const store = await ready();
    await store.getState().startJob();
    await until(() => store.getState().run !== null);
    await store.getState().openExample('fixture/run_demo');
    expect(store.getState().run).toBeNull();
    expect(store.getState().wallId).toBeNull();
  });
});

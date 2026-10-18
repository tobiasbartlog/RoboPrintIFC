import { collisionRanges } from '../player/clock';
import { createFakeApi } from './fakeApi';
import { createAppStore, selectStatuses } from './store';

async function until(cond: () => boolean, ms = 3000) {
  const t0 = Date.now();
  while (!cond()) {
    if (Date.now() - t0 > ms) throw new Error('Zeitüberschreitung');
    await new Promise((r) => setTimeout(r, 5));
  }
}

describe('Wiedergabe im Store', () => {
  it('Direkteinstieg öffnet Lauf und Teil, springt in die Simulation, nichts ist veraltet', async () => {
    const store = createAppStore(createFakeApi());
    await store.getState().openRun('run_demo', 'P01');
    const s = store.getState();
    expect(s.step).toBe('simulation');
    expect(s.partId).toBe('P01');
    expect(s.playback?.trajectory.t_s.length).toBeGreaterThan(10);
    expect(s.playback?.loaded.parts.P01?.stlUrl).toBe('/fixtures/run_demo/parts/P01/part.stl');
    expect(s.assetBase).toBe('/dev-assets');
    expect(selectStatuses(s)).toMatchObject({ simulation: 'aktuell', export: 'aktuell' });
  });

  it('unbekannter Lauf meldet einen Fehler in Nutzersprache', async () => {
    const api = createFakeApi();
    const store = createAppStore({ ...api, loadRun: async () => Promise.reject(new Error('HTTP 404')) });
    await store.getState().openRun('gibt/es/nicht');
    expect(store.getState().runError).toMatch(/konnte nicht geöffnet werden/);
    expect(store.getState().runErrorDetail).toBe('HTTP 404');
  });

  it('Job-Ende lädt die Wiedergabe des ersten Teils', async () => {
    const store = createAppStore(createFakeApi({ mode: 'ok', polls: 2 }), { pollMs: 1 });
    await store.getState().openExample('fixture/run_demo');
    store.getState().selectWall('box');
    await store.getState().startJob();
    await until(() => store.getState().playback !== null);
    expect(store.getState().playback?.partId).toBe('P01');
  });

  it('Kollisionseintrag pausiert beim kritischsten Sample und hebt das Glied hervor', async () => {
    const store = createAppStore(createFakeApi());
    await store.getState().openRun('run_demo', 'P01');
    const tr = store.getState().playback!.trajectory;
    const ranges = collisionRanges(tr);
    expect(ranges.length).toBeGreaterThan(0);
    store.getState().play();
    expect(store.getState().playing).toBe(true);
    const c = ranges[0]!;
    store.getState().selectCollision(c);
    const s = store.getState();
    expect(s.playing).toBe(false);
    expect(s.t).toBe(c.tMin);
    expect(s.highlightedLinks).toEqual([c.link]);
    expect(s.showObstacle).toBe(true);
    expect(s.focus?.seq).toBe(1);
    // Nutzer verschiebt den Scrubber: Hervorhebung weg, Zeit geklemmt.
    s.scrub(1e9);
    expect(store.getState().highlightedLinks).toEqual([]);
    expect(store.getState().t).toBe(tr.t_s[tr.t_s.length - 1]);
    // Am Ende startet Abspielen von vorn.
    store.getState().play();
    expect(store.getState().t).toBe(0);
  });
});

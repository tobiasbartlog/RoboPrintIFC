import { describe, expect, it, vi } from 'vitest';
import { createFakePatternApi } from './fakePatternApi';
import { createPatternStore } from './patternStore';

describe('patternStore', () => {
  it('lädt den Katalog und rechnet danach die erste Vorschau', async () => {
    const api = createFakePatternApi();
    const store = createPatternStore(api, { debounceMs: 0 });
    await store.getState().loadCatalog();
    await vi.waitFor(() => expect(store.getState().preview).not.toBeNull());
    expect(store.getState().catalog?.patterns.map((p) => p.name)).toEqual(['schalen', 'fugenwand']);
    expect(api.requests).toHaveLength(1);
    expect(api.requests[0]?.outline).toEqual({ length_mm: 600, thickness_mm: 200 });
  });

  it('entprellt schnelle Regleränderungen zu einer Anfrage mit dem letzten Wert', async () => {
    vi.useFakeTimers();
    try {
      const api = createFakePatternApi();
      const store = createPatternStore(api, { debounceMs: 100 });
      await store.getState().loadCatalog();
      await vi.advanceTimersByTimeAsync(0);
      const n = api.requests.length;
      for (const v of [31, 32, 33, 34]) {
        store.getState().setParam('bead_width_mm', v);
        await vi.advanceTimersByTimeAsync(20);
      }
      expect(api.requests.length).toBe(n);
      expect(store.getState().busy).toBe(true);
      await vi.advanceTimersByTimeAsync(150);
      expect(api.requests.length).toBe(n + 1);
      expect(api.requests.at(-1)?.params).toEqual({ bead_width_mm: 34 });
      expect(store.getState().preview?.params.bead_width_mm).toBe(34);
      expect(store.getState().busy).toBe(false);
    } finally {
      vi.useRealTimers();
    }
  });

  it('Mustertausch behält Kernregler und verwirft musterspezifische', async () => {
    const store = createPatternStore(createFakePatternApi(), { debounceMs: 0 });
    await store.getState().loadCatalog();
    store.getState().setParam('bead_width_mm', 40);
    store.getState().setParam('field_length_mm', 200);
    store.getState().selectPattern('fugenwand');
    expect(store.getState().params).toEqual({ bead_width_mm: 40 });
    store.getState().resetParams();
    expect(store.getState().params).toEqual({});
  });

  it('zeigt Serverfehler als Text und behält die letzte gültige Vorschau', async () => {
    const api = createFakePatternApi();
    const store = createPatternStore(api, { debounceMs: 0 });
    await store.getState().loadCatalog();
    await vi.waitFor(() => expect(store.getState().preview).not.toBeNull());
    const good = store.getState().preview;
    api.preview = async () => {
      throw new Error('Strangbreite darf höchstens 60 sein');
    };
    store.getState().setParam('bead_width_mm', 59);
    await vi.waitFor(() => expect(store.getState().previewError).toContain('höchstens 60'));
    expect(store.getState().preview).toBe(good);
    expect(store.getState().busy).toBe(false);
  });

  it('speichert Muster, Standardwerte, Änderungen und Querschnitt als Preset', async () => {
    const api = createFakePatternApi();
    const store = createPatternStore(api, { debounceMs: 0 });
    await store.getState().loadCatalog();
    store.getState().selectPattern('fugenwand');
    store.getState().setParam('bead_width_mm', 36);
    store.getState().setOutline({ length_mm: 900 });
    expect(await store.getState().save('Meine Wand', 'Test')).toBe(true);
    expect(api.presets[0]?.preset).toMatchObject({
      name: 'Meine Wand',
      pattern: 'fugenwand',
      params: { field_length_mm: 240, bead_width_mm: 36 },
      outline: { length_mm: 900, thickness_mm: 200 },
    });
    expect(store.getState().catalog?.presets.map((p) => p.id)).toEqual([api.presets[0]?.id]);
    // Preset laden stellt Muster, Regler und Maße wieder her
    store.getState().selectPattern('schalen');
    store.getState().selectPreset(api.presets[0]!.id);
    expect(store.getState().pattern).toBe('fugenwand');
    expect(store.getState().params).toMatchObject({ field_length_mm: 240, bead_width_mm: 36 });
    expect(store.getState().outline.length_mm).toBe(900);
  });

  it('unterscheidet Eingabefehler (422) von Serverfehlern und fordert auf Wunsch neu an', async () => {
    const api = createFakePatternApi();
    const store = createPatternStore(api, { debounceMs: 0 });
    await store.getState().loadCatalog();
    await vi.waitFor(() => expect(store.getState().preview).not.toBeNull());
    const original = api.preview.bind(api);
    api.preview = async () => {
      throw Object.assign(new Error('Feldlänge zu kurz'), { status: 422 });
    };
    store.getState().setParam('bead_width_mm', 40);
    await vi.waitFor(() => expect(store.getState().previewErrorStatus).toBe(422));
    api.preview = async () => {
      throw new TypeError('Failed to fetch');
    };
    store.getState().refresh();
    await vi.waitFor(() => expect(store.getState().previewError).toBe('Failed to fetch'));
    expect(store.getState().previewErrorStatus).toBeNull();
    api.preview = original;
    store.getState().refresh();
    await vi.waitFor(() => expect(store.getState().previewError).toBeNull());
    expect(store.getState().previewErrorStatus).toBeNull();
    expect(store.getState().preview?.params.bead_width_mm).toBe(40);
  });

  it('refresh ersetzt eine noch entprellte Anfrage statt sie doppelt zu senden', async () => {
    vi.useFakeTimers();
    try {
      const api = createFakePatternApi();
      const store = createPatternStore(api, { debounceMs: 100 });
      await store.getState().loadCatalog();
      await vi.advanceTimersByTimeAsync(0);
      const n = api.requests.length;
      store.getState().setParam('bead_width_mm', 33);
      store.getState().refresh();
      await vi.advanceTimersByTimeAsync(300);
      expect(api.requests.length).toBe(n + 1);
    } finally {
      vi.useRealTimers();
    }
  });

  it('lädt den Katalog nach einem Fehler erneut', async () => {
    const api = createFakePatternApi();
    const getCatalog = api.getCatalog.bind(api);
    api.getCatalog = async () => {
      throw new TypeError('Failed to fetch');
    };
    const store = createPatternStore(api, { debounceMs: 0 });
    await store.getState().loadCatalog();
    expect(store.getState().catalogError).toBe('Failed to fetch');
    api.getCatalog = getCatalog;
    await store.getState().loadCatalog();
    expect(store.getState().catalogError).toBeNull();
    expect(store.getState().catalog).not.toBeNull();
  });
});

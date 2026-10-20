import '@testing-library/jest-dom/vitest';

// Mantine braucht matchMedia und ResizeObserver, die jsdom nicht liefert.
window.matchMedia ??= ((query: string) => ({
  matches: false,
  media: query,
  onchange: null,
  addEventListener: () => {},
  removeEventListener: () => {},
  addListener: () => {},
  removeListener: () => {},
  dispatchEvent: () => false,
})) as typeof window.matchMedia;

globalThis.ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
};

// Mantine-Auswahllisten scrollen den aktiven Eintrag ins Bild; jsdom kennt scrollIntoView nicht.
Element.prototype.scrollIntoView ??= () => {};

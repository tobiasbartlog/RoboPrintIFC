import { createContext, useContext, type ReactNode } from 'react';
import { useStore } from 'zustand';
import type { PatternState, PatternStore } from './patternStore';

const Ctx = createContext<PatternStore | null>(null);

export function PatternStoreProvider({ store, children }: { store: PatternStore; children: ReactNode }) {
  return <Ctx.Provider value={store}>{children}</Ctx.Provider>;
}

export function usePatternStoreApi(): PatternStore {
  const store = useContext(Ctx);
  if (!store) throw new Error('PatternStoreProvider fehlt');
  return store;
}

export function usePatternStore<T>(selector: (s: PatternState) => T): T {
  const store = useContext(Ctx);
  if (!store) throw new Error('PatternStoreProvider fehlt');
  return useStore(store, selector);
}

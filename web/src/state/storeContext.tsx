import { createContext, useContext, useMemo, type ReactNode } from 'react';
import { useStore } from 'zustand';
import type { AppState, AppStore } from './store';
import { stepBlockedReason, stepStatuses, type StepId, type StepStatus } from './stepper';

const Ctx = createContext<AppStore | null>(null);

export function StoreProvider({ store, children }: { store: AppStore; children: ReactNode }) {
  return <Ctx.Provider value={store}>{children}</Ctx.Provider>;
}

export function useAppStore<T>(selector: (s: AppState) => T): T {
  const store = useContext(Ctx);
  if (!store) throw new Error('StoreProvider fehlt');
  return useStore(store, selector);
}

export function useAppStoreApi(): AppStore {
  const store = useContext(Ctx);
  if (!store) throw new Error('StoreProvider fehlt');
  return store;
}

/** Stepper-Zustand: Status und Sperrgrund je Schritt. */
export function useSteps(): { status: Record<StepId, StepStatus>; blocked: (s: StepId) => string | null } {
  const projectId = useAppStore((s) => s.project?.project_id ?? null);
  const wallId = useAppStore((s) => s.wallId);
  const params = useAppStore((s) => s.params);
  const runBasis = useAppStore((s) => s.run?.basis ?? null);
  return useMemo(() => {
    const inputs = { projectId, wallId, params, runBasis };
    return { status: stepStatuses(inputs), blocked: (s: StepId) => stepBlockedReason(s, inputs) };
  }, [projectId, wallId, params, runBasis]);
}

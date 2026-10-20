import { ActionIcon, AppShell, Box, Button, Group, MantineProvider, Stack, Text, Title, createTheme, useComputedColorScheme, useMantineColorScheme } from '@mantine/core';
import { useEffect, useMemo, useRef, useState } from 'react';
import { DecomposeStep } from './components/DecomposeStep';
import { ExportStep } from './components/ExportStep';
import { JobBar } from './components/JobBar';
import { ModelStep } from './components/ModelStep';
import { SimulationStep } from './components/SimulationStep';
import { StepperBar } from './components/StepperBar';
import { realPatternApi } from './api/patternClient';
import { PatternPanel } from './pattern/PatternPanel';
import { PatternWorkspace } from './pattern/PatternWorkspace';
import { PlayerScene } from './player/PlayerScene';
import { WallPreview } from './scene/WallPreview';
import type { ApiPort } from './state/apiPort';
import { selectApi } from './state/apiSelect';
import type { PatternApi } from './state/patternApi';
import { PatternStoreProvider, usePatternStoreApi } from './state/patternContext';
import { createPatternStore, type PatternStore } from './state/patternStore';
import { createAppStore, type AppStore } from './state/store';
import { StoreProvider, useAppStore, useAppStoreApi } from './state/storeContext';

const theme = createTheme({ primaryColor: 'blue', defaultRadius: 'md' });

function ColorSchemeToggle() {
  const { setColorScheme } = useMantineColorScheme();
  const computed = useComputedColorScheme('light');
  return (
    <ActionIcon
      variant="default"
      aria-label="Hell- und Dunkelmodus wechseln"
      onClick={() => setColorScheme(computed === 'light' ? 'dark' : 'light')}
      data-testid="color-scheme-toggle"
    >
      {computed === 'light' ? '☾' : '☀'}
    </ActionIcon>
  );
}

function StepPanel() {
  const step = useAppStore((s) => s.step);
  switch (step) {
    case 'model':
      return <ModelStep />;
    case 'decompose':
      return <DecomposeStep />;
    case 'simulation':
      return <SimulationStep />;
    case 'export':
      return <ExportStep />;
  }
}

/** Leerzustand der 3D-Ansicht: sagt, wann dort etwas erscheint. */
function SceneEmptyHint() {
  const hasRun = useAppStore((s) => s.run !== null);
  const preview = useAppStore((s) => s.step === 'model' && s.project !== null);
  if (hasRun || preview) return null;
  return (
    <Box
      data-testid="scene-empty-hint"
      style={{ position: 'absolute', top: 16, left: 16, right: 16, pointerEvents: 'none', display: 'flex', justifyContent: 'center' }}
    >
      <Text size="sm" c="dimmed" ta="center" maw={520}>
        Hier erscheinen nach „Zerlegen & prüfen“ der Roboter am Doosantisch und das gewählte Modul.
      </Text>
    </Box>
  );
}

/**
 * Wandvorschau über der Szene: in Schritt 1 alle Wände des Projekts (Auswahl synchron zur Liste),
 * in Schritt 2 die gewählte Wand, solange noch kein Lauf vorliegt.
 */
function WallPreviewLayer() {
  const step = useAppStore((s) => s.step);
  const project = useAppStore((s) => s.project);
  const wallId = useAppStore((s) => s.wallId);
  const hasRun = useAppStore((s) => s.run !== null);
  const selectWall = useAppStore((s) => s.selectWall);
  const meshUrl = useAppStore((s) => s.wallMeshUrl);
  const contextMeshUrl = useAppStore((s) => s.contextMeshUrl);
  const wallView = useAppStore((s) => s.wallView);
  const setWallView = useAppStore((s) => s.setWallView);
  const size = project?.building_mm;
  const house = useMemo(() => (size ? { size, contextUrl: contextMeshUrl() } : null), [size, contextMeshUrl]);
  if (!project) return null;
  if (step === 'model') {
    return <WallPreview walls={project.walls} wallId={wallId} meshUrl={meshUrl} onSelect={selectWall} house={house} view={wallView} onViewChange={setWallView} />;
  }
  if (step === 'decompose' && !hasRun && wallId) return <WallPreview walls={project.walls} wallId={wallId} meshUrl={meshUrl} onSelect={selectWall} onlySelected />;
  return null;
}

/** Direkteinstieg: `/?run=<run_id>&part=<part_id>` öffnet die Simulation eines vorhandenen Laufs. */
function useDirectEntry() {
  const store = useAppStoreApi();
  const done = useRef(false);
  useEffect(() => {
    if (done.current) return;
    done.current = true;
    const q = new URLSearchParams(window.location.search);
    const runId = q.get('run');
    if (runId) void store.getState().openRun(runId, q.get('part'));
  }, [store]);
}

export type View = 'flow' | 'pattern';

/** Ansicht aus der URL (`?view=muster`), sonst der Ablauf. */
export function viewFromSearch(search: string): View {
  return new URLSearchParams(search).get('view') === 'muster' ? 'pattern' : 'flow';
}

/**
 * Umschalter zwischen dem Ablauf (vier Schritte) und dem Mustererstellers. Das Muster ist kein
 * fünfter Schritt: Es braucht weder Modell noch Lauf und ist ein eigenes Werkzeug mit eigener
 * Vorschau; ein Reiter in der Kopfzeile ist von jedem Schritt aus erreichbar.
 */
function ViewSwitch({ view, onChange }: { view: View; onChange: (v: View) => void }) {
  return (
    <Group gap={4} wrap="nowrap" role="tablist" aria-label="Ansicht" data-testid="view-switch">
      <Button role="tab" aria-selected={view === 'flow'} size="xs" variant={view === 'flow' ? 'filled' : 'default'} onClick={() => onChange('flow')} data-testid="view-flow">
        Ablauf
      </Button>
      <Button role="tab" aria-selected={view === 'pattern'} size="xs" variant={view === 'pattern' ? 'filled' : 'default'} onClick={() => onChange('pattern')} data-testid="view-pattern">
        Muster
      </Button>
    </Group>
  );
}

function Shell({ initialView }: { initialView: View }) {
  useDirectEntry();
  const [view, setView] = useState<View>(initialView);
  const patternStore = usePatternStoreApi();
  useEffect(() => {
    if (view === 'pattern' && patternStore.getState().catalog === null) void patternStore.getState().loadCatalog();
  }, [view, patternStore]);
  return (
    <AppShell header={{ height: 56 }} aside={{ width: { base: 340, lg: 440 }, breakpoint: 'sm' }} padding="md">
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between" wrap="nowrap">
          <Title order={1} size="h3">
            RoboPrintIFC
          </Title>
          <Group gap="md" wrap="nowrap">
            <ViewSwitch view={view} onChange={setView} />
            <JobBar />
            <ColorSchemeToggle />
          </Group>
        </Group>
      </AppShell.Header>
      <AppShell.Main>
        <Stack gap="md" h="calc(100vh - 56px - 2 * var(--mantine-spacing-md))" style={{ minWidth: 0 }}>
          {view === 'pattern' ? (
            <Box style={{ flex: 1, minHeight: 0 }}>
              <PatternWorkspace />
            </Box>
          ) : (
            <>
              <StepperBar />
              <Box style={{ flex: 1, minHeight: 0, position: 'relative' }}>
                <PlayerScene />
                <WallPreviewLayer />
                <SceneEmptyHint />
              </Box>
            </>
          )}
        </Stack>
      </AppShell.Main>
      <AppShell.Aside p="md">
        {/* Nur senkrecht scrollen: breite Inhalte (DRL-Vorschau) scrollen in ihrem eigenen Kasten. */}
        <Box h="100%" data-testid="side-panel" style={{ overflowY: 'auto', overflowX: 'hidden', paddingRight: 4 }}>
          {view === 'pattern' ? <PatternPanel /> : <StepPanel />}
        </Box>
      </AppShell.Aside>
    </AppShell>
  );
}

/** `api` und `store` sind für Tests austauschbar; ohne Angabe wählt `selectApi` (Query ?fake=1|ok). */
export function App({ api, store, patternApi, patternStore, initialView }: { api?: ApiPort; store?: AppStore; patternApi?: PatternApi; patternStore?: PatternStore; initialView?: View } = {}) {
  const s = useMemo(() => store ?? createAppStore(api ?? selectApi()), [api, store]);
  const ps = useMemo(() => patternStore ?? createPatternStore(patternApi ?? realPatternApi), [patternApi, patternStore]);
  return (
    <MantineProvider theme={theme} defaultColorScheme="light">
      <StoreProvider store={s}>
        <PatternStoreProvider store={ps}>
          <Shell initialView={initialView ?? viewFromSearch(window.location.search)} />
        </PatternStoreProvider>
      </StoreProvider>
    </MantineProvider>
  );
}

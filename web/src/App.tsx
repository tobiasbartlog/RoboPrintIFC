import { ActionIcon, AppShell, Box, Group, MantineProvider, ScrollArea, Stack, Title, createTheme, useComputedColorScheme, useMantineColorScheme } from '@mantine/core';
import { useMemo } from 'react';
import { DecomposeStep } from './components/DecomposeStep';
import { ExportStep } from './components/ExportStep';
import { JobBar } from './components/JobBar';
import { ModelStep } from './components/ModelStep';
import { SimulationStep } from './components/SimulationStep';
import { StepperBar } from './components/StepperBar';
import { SceneView } from './scene/SceneView';
import type { ApiPort } from './state/apiPort';
import { selectApi } from './state/apiSelect';
import { createAppStore, type AppStore } from './state/store';
import { StoreProvider, useAppStore } from './state/storeContext';

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

function Shell() {
  return (
    <AppShell header={{ height: 56 }} aside={{ width: { base: 340, lg: 440 }, breakpoint: 'sm' }} padding="md">
      <AppShell.Header>
        <Group h="100%" px="md" justify="space-between" wrap="nowrap">
          <Title order={1} size="h3">
            RoboPrintIFC
          </Title>
          <Group gap="md" wrap="nowrap">
            <JobBar />
            <ColorSchemeToggle />
          </Group>
        </Group>
      </AppShell.Header>
      <AppShell.Main>
        <Stack gap="md" h="calc(100vh - 56px - 2 * var(--mantine-spacing-md))" style={{ minWidth: 0 }}>
          <StepperBar />
          <Box style={{ flex: 1, minHeight: 0 }}>
            {/* Verdrahtung mit Store und Player folgt in A3.4. */}
            <SceneView run={null} partId={null} sample={null} highlightedLinks={[]} obstacleVisible={false} />
          </Box>
        </Stack>
      </AppShell.Main>
      <AppShell.Aside p="md">
        <ScrollArea h="100%" data-testid="side-panel">
          <StepPanel />
        </ScrollArea>
      </AppShell.Aside>
    </AppShell>
  );
}

/** `api` und `store` sind für Tests austauschbar; ohne Angabe wählt `selectApi` (Query ?fake=1|ok). */
export function App({ api, store }: { api?: ApiPort; store?: AppStore } = {}) {
  const s = useMemo(() => store ?? createAppStore(api ?? selectApi()), [api, store]);
  return (
    <MantineProvider theme={theme} defaultColorScheme="light">
      <StoreProvider store={s}>
        <Shell />
      </StoreProvider>
    </MantineProvider>
  );
}

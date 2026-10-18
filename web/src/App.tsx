import { MantineProvider, Title } from '@mantine/core';

export function App() {
  return (
    <MantineProvider defaultColorScheme="light">
      <Title order={1} p="md">
        RoboPrintIFC
      </Title>
    </MantineProvider>
  );
}

import { Center, Stack, Text } from '@mantine/core';

/** Platzhalter für die 3D-Szene (A3.3: Roboter, Tisch, Teil mit Schnittebene, Werkzeug, Kamera). */
export function SceneView() {
  return (
    <Center data-testid="scene-view" h="100%" mih={320} bg="var(--mantine-color-default-hover)" style={{ borderRadius: 8 }}>
      <Stack gap={4} align="center">
        <Text fw={600}>3D-Ansicht</Text>
        <Text size="sm" c="dimmed">
          Hier erscheint die Szene mit Roboter, Tisch und Modul.
        </Text>
      </Stack>
    </Center>
  );
}

import { Alert, Collapse, Text, UnstyledButton } from '@mantine/core';
import { useState } from 'react';
import type { StepStatus } from '../state/stepper';

export const STATUS_COLOR: Record<StepStatus, string> = { aktuell: 'green', veraltet: 'yellow', fehlt: 'gray' };

/** Fehler in Nutzersprache, rohe Meldung ausklappbar. */
export function ErrorNote({ message, detail, testid }: { message: string; detail?: string | null; testid: string }) {
  const [open, setOpen] = useState(false);
  return (
    <Alert color="red" title="Das hat nicht geklappt" data-testid={testid}>
      <Text size="sm">{message}</Text>
      {detail ? (
        <>
          <UnstyledButton onClick={() => setOpen((o) => !o)} data-testid={`${testid}-toggle`}>
            <Text size="xs" c="dimmed" td="underline">
              {open ? 'Details ausblenden' : 'Details anzeigen'}
            </Text>
          </UnstyledButton>
          <Collapse in={open}>
            <Text size="xs" ff="monospace" data-testid={`${testid}-detail`}>
              {detail}
            </Text>
          </Collapse>
        </>
      ) : null}
    </Alert>
  );
}

/** Deaktivierter Knopf nennt seinen Grund sichtbar daneben. */
export function Reason({ text, testid }: { text: string | null; testid: string }) {
  if (!text) return null;
  return (
    <Text size="xs" c="dimmed" data-testid={testid}>
      {text}
    </Text>
  );
}

export function StaleBanner({ show }: { show: boolean }) {
  if (!show) return null;
  return (
    <Alert color="yellow" title="Veraltet" data-testid="stale-banner">
      Wand oder Parameter wurden nach der letzten Rechnung geändert. Bitte neu zerlegen & prüfen.
    </Alert>
  );
}

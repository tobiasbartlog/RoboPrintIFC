import { Badge, Group, Paper, Text, UnstyledButton } from '@mantine/core';
import { STEP_IDS, STEP_LABELS } from '../state/stepper';
import { useAppStore, useSteps } from '../state/storeContext';
import { STATUS_COLOR } from './common';

/** Stepper: je Schritt genau einer von "fehlt", "veraltet", "aktuell". Grün nur für "aktuell". */
export function StepperBar() {
  const step = useAppStore((s) => s.step);
  const setStep = useAppStore((s) => s.setStep);
  const { status, blocked } = useSteps();
  return (
    <Group gap="xs" wrap="wrap" data-testid="stepper">
      {STEP_IDS.map((id, i) => {
        const reason = blocked(id);
        const active = step === id;
        return (
          <UnstyledButton
            key={id}
            disabled={reason !== null}
            onClick={() => setStep(id)}
            data-testid={`step-${id}`}
            data-status={status[id]}
            data-active={active}
            aria-current={active ? 'step' : undefined}
            style={{ opacity: reason ? 0.7 : 1 }}
          >
            <Paper withBorder p="xs" px="sm" style={{ borderWidth: active ? 2 : 1, borderColor: active ? 'var(--mantine-primary-color-filled)' : undefined }}>
              <Group gap="xs" wrap="nowrap">
                <Text fw={600} size="sm">
                  {i + 1}. {STEP_LABELS[id]}
                </Text>
                <Badge size="sm" color={STATUS_COLOR[status[id]]} variant={status[id] === 'aktuell' ? 'filled' : 'light'} data-testid={`step-${id}-status`}>
                  {status[id]}
                </Badge>
              </Group>
              {reason ? (
                <Text size="xs" c="dimmed" data-testid={`step-${id}-reason`}>
                  {reason}
                </Text>
              ) : null}
            </Paper>
          </UnstyledButton>
        );
      })}
    </Group>
  );
}

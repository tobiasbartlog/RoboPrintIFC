import { Badge, Group, Stack, Text, UnstyledButton } from '@mantine/core';
import { useState, type ReactNode } from 'react';
import type { PartGroup } from '../state/partGroups';

interface Props {
  group: PartGroup;
  partId: string | null;
  onSelect: (partId: string) => void;
  testid: string;
  /** Steht in derselben Zeile vor der Anzahl (z. B. der Knopf des Repräsentanten). */
  children?: ReactNode;
}

/**
 * Zeile einer Gruppe gleicher Geometrie. Bei Kopien folgen die Anzahl und „Details anzeigen“, das die
 * Module der Gruppe auflistet; ein Klick auf eines wählt es.
 */
export function GroupMembers({ group, partId, onSelect, testid, children }: Props) {
  const [open, setOpen] = useState(false);
  const n = group.members.length;
  return (
    <Stack gap={4} data-testid={testid}>
      <Group gap="xs">
        {children}
        {n > 1 ? (
          <>
            <Text size="xs" c="dimmed" data-testid={`${testid}-count`}>
              {n} Module gleicher Geometrie
            </Text>
            <UnstyledButton onClick={() => setOpen((o) => !o)} aria-expanded={open} data-testid={`${testid}-toggle`}>
              <Text size="xs" c="dimmed" td="underline">
                {open ? 'Details ausblenden' : 'Details anzeigen'}
              </Text>
            </UnstyledButton>
          </>
        ) : null}
      </Group>
      {n > 1 && open ? (
        <Group gap={4} data-testid={`${testid}-members`}>
          {group.members.map((m) => (
            <UnstyledButton key={m.part_id} onClick={() => onSelect(m.part_id)} data-testid={`${testid}-member-${m.part_id}`} data-selected={m.part_id === partId}>
              <Badge size="sm" tt="none" variant={m.part_id === partId ? 'filled' : 'default'}>
                {m.part_id}
              </Badge>
            </UnstyledButton>
          ))}
        </Group>
      ) : null}
    </Stack>
  );
}

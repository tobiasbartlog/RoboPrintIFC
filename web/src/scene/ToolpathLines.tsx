import { useMemo } from 'react';
import { BufferAttribute, BufferGeometry } from 'three';
import type { Toolpath } from '../contracts';
import { ringSegments } from './math';

interface ToolpathLinesProps {
  toolpath: Toolpath;
  /** Anzahl fertiger Schichten k; null = alles als gedruckt. */
  layer: number | null;
  doneColor: string;
  todoColor: string;
}

function geometryOf(positions: Float32Array): BufferGeometry {
  const g = new BufferGeometry();
  g.setAttribute('position', new BufferAttribute(positions, 3));
  return g;
}

/** Druckbahnen (Frame W, mm): fertige Schichten kraeftig, die uebrigen blass. */
export function ToolpathLines({ toolpath, layer, doneColor, todoColor }: ToolpathLinesProps) {
  const k = layer ?? Infinity;
  const done = useMemo(() => geometryOf(ringSegments(toolpath, (l) => l < k)), [toolpath, k]);
  const todo = useMemo(() => geometryOf(ringSegments(toolpath, (l) => l >= k)), [toolpath, k]);
  return (
    <group name="toolpath">
      <lineSegments geometry={done}>
        <lineBasicMaterial color={doneColor} />
      </lineSegments>
      <lineSegments geometry={todo}>
        <lineBasicMaterial color={todoColor} transparent opacity={0.5} />
      </lineSegments>
    </group>
  );
}

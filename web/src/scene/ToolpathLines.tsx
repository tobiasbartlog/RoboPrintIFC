import { useThree } from '@react-three/fiber';
import { useEffect, useLayoutEffect, useMemo } from 'react';
import { BufferAttribute, BufferGeometry } from 'three';
import type { Toolpath } from '../contracts';
import { layeredRingSegments } from './math';

interface ToolpathLinesProps {
  toolpath: Toolpath;
  /** Anzahl fertiger Schichten k; null = alles als gedruckt. */
  layer: number | null;
  doneColor: string;
  todoColor: string;
}

/**
 * Druckbahnen (Frame W, mm): fertige Schichten kraeftig, die uebrigen blass. Die Punkte liegen
 * einmal nach Schicht sortiert im Speicher; ein Schichtwechsel verschiebt nur die drawRanges.
 */
export function ToolpathLines({ toolpath, layer, doneColor, todoColor }: ToolpathLinesProps) {
  const invalidate = useThree((s) => s.invalidate);
  const { done, todo, splitAt, count } = useMemo(() => {
    const segs = layeredRingSegments(toolpath);
    const attr = new BufferAttribute(segs.positions, 3);
    const done = new BufferGeometry();
    done.setAttribute('position', attr);
    const todo = new BufferGeometry();
    todo.setAttribute('position', attr);
    return { done, todo, splitAt: segs.splitAt, count: segs.positions.length / 3 };
  }, [toolpath]);
  useEffect(
    () => () => {
      done.dispose();
      todo.dispose();
    },
    [done, todo],
  );
  const split = layer === null ? count : splitAt(layer);
  useLayoutEffect(() => {
    done.setDrawRange(0, split);
    todo.setDrawRange(split, count - split);
    invalidate();
  }, [done, todo, split, count, invalidate]);
  return (
    <group name="toolpath">
      <lineSegments geometry={done} frustumCulled={false}>
        <lineBasicMaterial color={doneColor} />
      </lineSegments>
      <lineSegments geometry={todo} frustumCulled={false}>
        <lineBasicMaterial color={todoColor} transparent opacity={0.5} />
      </lineSegments>
    </group>
  );
}

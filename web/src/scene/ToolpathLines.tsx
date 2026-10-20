import { useThree } from '@react-three/fiber';
import { useEffect, useLayoutEffect, useMemo } from 'react';
import { BufferAttribute, BufferGeometry } from 'three';
import type { PrintedState } from './progress';
import { cutStart, linesDone, strandCut, strandLines, type StrandLayout } from './strand';

interface ToolpathLinesProps {
  layout: StrandLayout;
  /** Druckfortschritt; null = alles als gedruckt. */
  printed: PrintedState | null;
  doneColor: string;
  todoColor: string;
}

/**
 * Bahn (Frame W, mm) in Druckreihenfolge mit Verbindern: Gedrucktes kraeftig bis genau zur Duese,
 * der Rest blass. Die Punkte liegen einmal im Speicher; ein Uhrschritt verschiebt nur die
 * drawRanges und setzt die Spitze (ein Linienstueck vom letzten Wegpunkt bis zum Schnitt).
 */
export function ToolpathLines({ layout, printed, doneColor, todoColor }: ToolpathLinesProps) {
  const invalidate = useThree((s) => s.invalidate);
  const { done, todo, tip, start, count } = useMemo(() => {
    const lines = strandLines(layout);
    const attr = new BufferAttribute(lines.positions, 3);
    const done = new BufferGeometry();
    done.setAttribute('position', attr);
    const todo = new BufferGeometry();
    todo.setAttribute('position', attr);
    const tip = new BufferGeometry();
    tip.setAttribute('position', new BufferAttribute(new Float32Array(6), 3));
    return { done, todo, tip, start: lines.start, count: lines.positions.length / 3 };
  }, [layout]);
  useEffect(
    () => () => {
      done.dispose();
      todo.dispose();
      tip.dispose();
    },
    [done, todo, tip],
  );

  const pos = printed ? printed.pos : null;
  useLayoutEffect(() => {
    const cut = pos === null ? null : strandCut(layout, pos);
    const split = cut ? Math.min(linesDone(start, cut), count) : count;
    done.setDrawRange(0, split);
    todo.setDrawRange(split, count - split);
    const a = cut ? cutStart(layout, cut) : null;
    const b = cut?.tip ?? null;
    if (a && b) {
      const attr = tip.getAttribute('position') as BufferAttribute;
      attr.set([...a, ...b]);
      attr.needsUpdate = true;
      tip.computeBoundingSphere();
    }
    tip.setDrawRange(0, a && b ? 2 : 0);
    invalidate();
  }, [layout, pos, done, todo, tip, start, count, invalidate]);

  return (
    <group name="toolpath">
      <lineSegments geometry={done} frustumCulled={false}>
        <lineBasicMaterial color={doneColor} />
      </lineSegments>
      <lineSegments geometry={tip} frustumCulled={false}>
        <lineBasicMaterial color={doneColor} />
      </lineSegments>
      <lineSegments geometry={todo} frustumCulled={false}>
        <lineBasicMaterial color={todoColor} transparent opacity={0.5} />
      </lineSegments>
    </group>
  );
}

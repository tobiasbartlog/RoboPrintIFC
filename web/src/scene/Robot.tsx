import { createPortal, useThree } from '@react-three/fiber';
import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { Color, Matrix4 } from 'three';
import type { URDFRobot } from 'urdf-loader';
import { loadRobot, anchorOf, applyQ, tintLinks } from './urdf';
import { TransformGroup } from './TransformGroup';

interface RobotProps {
  urdfUrl: string;
  packageBase: string;
  /** T_WB in mm (Zeilen -> Matrix4). */
  T_WB: Matrix4;
  /** Gelenkwinkel in Doosan-Konvention (= URDF), rad. */
  q: readonly number[];
  /** Glieder, die eingefaerbt werden (Name -> Farbe). */
  tint: ReadonlyMap<string, Color>;
  onRobot: (robot: URDFRobot | null) => void;
  onError?: (e: Error) => void;
  /** Wird in den Flansch-Anker gerendert (mm, Flansch-Frame): Werkzeug, TCP-Marke. */
  children?: ReactNode;
}

const TO_MM = new Matrix4().makeScale(1000, 1000, 1000);

export function Robot({ urdfUrl, packageBase, T_WB, q, tint, onRobot, onError, children }: RobotProps) {
  const [robot, setRobot] = useState<URDFRobot | null>(null);
  const invalidate = useThree((s) => s.invalidate);

  useEffect(() => {
    const ac = new AbortController();
    loadRobot(urdfUrl, packageBase, ac.signal).then(
      (r) => {
        setRobot(r);
        onRobot(r);
      },
      (e: Error) => {
        if (!ac.signal.aborted) onError?.(e);
      },
    );
    return () => {
      ac.abort();
      setRobot(null);
      onRobot(null);
    };
  }, [urdfUrl, packageBase, onRobot, onError]);

  // Pose und Einfaerbung gehoeren zur Uhr: sie werden bei jedem neuen Sample gesetzt.
  useEffect(() => {
    if (robot) {
      applyQ(robot, q);
      invalidate();
    }
  }, [robot, q, invalidate]);
  useEffect(() => {
    if (robot) {
      tintLinks(robot, tint);
      invalidate();
    }
  }, [robot, tint, invalidate]);

  const matrix = useMemo(() => T_WB.clone().multiply(TO_MM), [T_WB]);
  const anchor = robot ? anchorOf(robot) : undefined;

  return (
    <TransformGroup matrix={matrix} name="robot_root">
      {robot && <primitive object={robot} />}
      {anchor && createPortal(<>{children}</>, anchor)}
    </TransformGroup>
  );
}

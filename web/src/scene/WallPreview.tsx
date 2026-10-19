import { Html, OrbitControls } from '@react-three/drei';
import { Canvas } from '@react-three/fiber';
import { useCallback, useMemo } from 'react';
import { BoxGeometry, DoubleSide, EdgesGeometry, type BufferGeometry } from 'three';
import type { WallEntry } from '../contracts';
import { useStl } from './assets';
import { useScenePalette, type ScenePalette } from './palette';

/** Breite einer Reihe der Anordnung (mm); danach beginnt die nächste Reihe weiter oben. */
const ROW_WIDTH_MM = 9000;
const GAP_MM = 500;

export interface WallSlot {
  wall: WallEntry;
  /** Ecke (x, z) der Wand in der gemeinsamen Ansicht (mm). */
  x: number;
  z: number;
}

/**
 * Wandansicht: Alle Wände stehen als Aufriss nebeneinander (jede in ihrem Frame L, Länge in X,
 * Höhe in Z), in Reihen umbrochen. Reine Funktion der Wandliste, damit sie testbar bleibt.
 */
export function layoutWalls(walls: readonly WallEntry[]): { slots: WallSlot[]; width: number; height: number } {
  const slots: WallSlot[] = [];
  let x = 0;
  let z = 0;
  let rowH = 0;
  let width = 0;
  for (const wall of walls) {
    if (x > 0 && x + wall.length_mm > ROW_WIDTH_MM) {
      z += rowH + GAP_MM;
      x = 0;
      rowH = 0;
    }
    slots.push({ wall, x, z });
    x += wall.length_mm + GAP_MM;
    rowH = Math.max(rowH, wall.height_mm);
    width = Math.max(width, x - GAP_MM);
  }
  return { slots, width, height: z + rowH };
}

function wallColor(p: ScenePalette, selected: boolean, eligible: boolean): string {
  if (selected) return p.accent;
  return eligible ? p.ghost : p.danger;
}

interface WallMeshProps {
  slot: WallSlot;
  selected: boolean;
  palette: ScenePalette;
  url: string;
  onSelect: (id: string) => void;
  interactive: boolean;
}

function WallMesh({ slot, selected, palette, url, onSelect, interactive }: WallMeshProps) {
  const { wall } = slot;
  const loaded = useStl(url);
  // Solange das Netz lädt (oder fehlt), steht ein Quader mit den Maßen aus der Wandliste da.
  const geometry: BufferGeometry = useMemo(
    () =>
      loaded ??
      new BoxGeometry(wall.length_mm, wall.thickness_mm, wall.height_mm).translate(wall.length_mm / 2, wall.thickness_mm / 2, wall.height_mm / 2),
    [loaded, wall.length_mm, wall.thickness_mm, wall.height_mm],
  );
  const edges = useMemo(() => new EdgesGeometry(geometry, 30), [geometry]);
  const color = wallColor(palette, selected, wall.eligible);
  const click = interactive && wall.eligible ? () => onSelect(wall.wall_id) : undefined;
  return (
    <group position={[slot.x, 0, slot.z]}>
      <mesh geometry={geometry} onClick={click} name={`wall_${wall.wall_id}`}>
        <meshStandardMaterial color={color} roughness={0.85} side={DoubleSide} transparent={!wall.eligible} opacity={wall.eligible ? 1 : 0.55} />
      </mesh>
      <lineSegments geometry={edges}>
        <lineBasicMaterial color={selected ? palette.toolpathDone : palette.table} />
      </lineSegments>
      <Html position={[wall.length_mm / 2, 0, wall.height_mm + 150]} center zIndexRange={[5, 0]}>
        <button
          type="button"
          data-testid={`wall-label-${wall.wall_id}`}
          data-selected={selected}
          disabled={!interactive || !wall.eligible}
          onClick={() => onSelect(wall.wall_id)}
          style={{
            font: '600 12px sans-serif',
            whiteSpace: 'nowrap',
            padding: '2px 8px',
            borderRadius: 6,
            cursor: interactive && wall.eligible ? 'pointer' : 'default',
            color: 'var(--mantine-color-text)',
            background: 'var(--mantine-color-body)',
            border: `2px solid ${selected ? 'var(--mantine-color-blue-6)' : 'var(--mantine-color-default-border)'}`,
            opacity: wall.eligible ? 1 : 0.7,
          }}
        >
          {wall.name}
        </button>
      </Html>
    </group>
  );
}

interface WallPreviewProps {
  walls: readonly WallEntry[];
  wallId: string | null;
  /** URL des Wandmeshes (STL, Frame L, mm). */
  meshUrl: (wallId: string) => string;
  onSelect: (wallId: string) => void;
  /** Nur die gewählte Wand zeigen (Schritt „Zerlegen & prüfen“ vor dem ersten Lauf). */
  onlySelected?: boolean;
}

/** Eigene 3D-Ansicht der Wände (Schritt 1): Auswahl per Klick auf Wand oder Namensschild, synchron zur Liste. */
export function WallPreview({ walls, wallId, meshUrl, onSelect, onlySelected = false }: WallPreviewProps) {
  const palette = useScenePalette();
  const shown = useMemo(() => (onlySelected ? walls.filter((w) => w.wall_id === wallId) : walls), [walls, wallId, onlySelected]);
  const { slots, width, height } = useMemo(() => layoutWalls(shown), [shown]);
  const cx = width / 2;
  const cz = height / 2;
  // Abstand so, dass die Anordnung ins Bild passt (fov 38°).
  const dist = Math.max(width * 0.95, height * 1.6, 3000);
  const camera = useMemo(
    () => ({
      position: [cx + dist * 0.08, -dist, cz + dist * 0.1] as [number, number, number],
      up: [0, 0, 1] as [number, number, number],
      fov: 38,
      near: 20,
      far: 100000,
    }),
    [cx, cz, dist],
  );
  const onSelectStable = useCallback((id: string) => onSelect(id), [onSelect]);
  return (
    <div
      style={{ position: 'absolute', inset: 0, background: 'var(--mantine-color-body)' }}
      data-testid="wall-preview"
      data-selected-wall={wallId ?? ''}
      data-wall-count={slots.length}
    >
      <Canvas
        key={`${slots.length}-${Math.round(width)}-${Math.round(height)}`}
        camera={camera}
        gl={{ preserveDrawingBuffer: true, antialias: true }}
      >
        <color attach="background" args={[palette.background]} />
        <hemisphereLight args={['#ffffff', '#667788', 0.9]} position={[0, 0, 1]} />
        <directionalLight position={[3000, -4000, 6000]} intensity={1.5} />
        <directionalLight position={[-3000, 2000, 1500]} intensity={0.4} />
        <gridHelper args={[Math.max(width, 6000) * 2, 40, palette.table, palette.floor]} rotation={[Math.PI / 2, 0, 0]} position={[cx, 0, 0]} />
        {slots.map((slot) => (
          <WallMesh
            key={slot.wall.wall_id}
            slot={slot}
            selected={slot.wall.wall_id === wallId}
            palette={palette}
            url={meshUrl(slot.wall.wall_id)}
            onSelect={onSelectStable}
            interactive={!onlySelected}
          />
        ))}
        <OrbitControls makeDefault target={[cx, 0, cz]} />
      </Canvas>
      <div style={{ position: 'absolute', left: 16, bottom: 12, pointerEvents: 'none', fontSize: 12, color: 'var(--mantine-color-dimmed)' }}>
        {onlySelected ? 'Gewählte Wand (Frame L)' : 'Wand anklicken oder in der Liste wählen. Rot: ungeeignet.'}
      </div>
    </div>
  );
}

import { Html, OrbitControls } from '@react-three/drei';
import { Canvas } from '@react-three/fiber';
import { SegmentedControl } from '@mantine/core';
import { useCallback, useMemo } from 'react';
import { BoxGeometry, DoubleSide, EdgesGeometry, type BufferGeometry } from 'three';
import type { WallEntry } from '../contracts';
import type { WallFrame } from '../state/apiPort';
import type { WallView } from '../state/store';
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

type Vec3 = [number, number, number];

/** Kamera der Hausansicht: schräg von vorne oben auf das ganze Gebäude (Ausdehnung in mm, Z oben). */
export function houseCamera(size: readonly number[]): { position: Vec3; target: Vec3 } {
  const [sx = 0, sy = 0, sz = 0] = size;
  const target: Vec3 = [sx / 2, sy / 2, sz / 3];
  const dist = Math.max(Math.hypot(sx, sy, sz) * 1.75, 3000);
  return { position: [target[0] - dist * 0.45, target[1] - dist * 0.75, target[2] + dist * 0.5], target };
}

function wallColor(p: ScenePalette, selected: boolean, eligible: boolean): string {
  if (selected) return p.accent;
  return eligible ? p.ghost : p.danger;
}

interface WallLabelProps {
  wall: WallEntry;
  selected: boolean;
  interactive: boolean;
  onSelect: (id: string) => void;
  position: Vec3;
}

function WallLabel({ wall, selected, interactive, onSelect, position }: WallLabelProps) {
  return (
    <Html position={position} center zIndexRange={[5, 0]}>
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
  );
}

interface WallBodyProps {
  wall: WallEntry;
  geometry: BufferGeometry;
  selected: boolean;
  palette: ScenePalette;
  onClick?: () => void;
}

function WallBody({ wall, geometry, selected, palette, onClick }: WallBodyProps) {
  const edges = useMemo(() => new EdgesGeometry(geometry, 30), [geometry]);
  return (
    <>
      <mesh geometry={geometry} onClick={onClick} name={`wall_${wall.wall_id}`}>
        <meshStandardMaterial
          color={wallColor(palette, selected, wall.eligible)}
          roughness={0.85}
          side={DoubleSide}
          transparent={!wall.eligible}
          opacity={wall.eligible ? 1 : 0.55}
        />
      </mesh>
      <lineSegments geometry={edges}>
        <lineBasicMaterial color={selected ? palette.toolpathDone : palette.table} />
      </lineSegments>
    </>
  );
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
  const click = interactive && wall.eligible ? () => onSelect(wall.wall_id) : undefined;
  return (
    <group position={[slot.x, 0, slot.z]}>
      <WallBody wall={wall} geometry={geometry} selected={selected} palette={palette} onClick={click} />
      <WallLabel wall={wall} selected={selected} interactive={interactive} onSelect={onSelect} position={[wall.length_mm / 2, 0, wall.height_mm + 150]} />
    </group>
  );
}

interface HouseWallProps {
  wall: WallEntry;
  selected: boolean;
  palette: ScenePalette;
  url: string;
  onSelect: (id: string) => void;
}

/** Wand in Gebäudelage: Das Netz liegt schon richtig, das Schild steht über seiner Mitte. */
function HouseWall({ wall, selected, palette, url, onSelect }: HouseWallProps) {
  const geometry = useStl(url);
  const labelAt = useMemo((): Vec3 | null => {
    if (!geometry) return null;
    geometry.computeBoundingBox();
    const b = geometry.boundingBox;
    return b ? [(b.min.x + b.max.x) / 2, (b.min.y + b.max.y) / 2, b.max.z + 150] : null;
  }, [geometry]);
  if (!geometry || !labelAt) return null;
  return (
    <group>
      <WallBody wall={wall} geometry={geometry} selected={selected} palette={palette} onClick={wall.eligible ? () => onSelect(wall.wall_id) : undefined} />
      <WallLabel wall={wall} selected={selected} interactive onSelect={onSelect} position={labelAt} />
    </group>
  );
}

/** Übrige Bauteile (Decken, Dach, ...) als graue Hülle; fängt keine Klicks ab, damit die Wände wählbar bleiben. */
function HouseContext({ url, palette }: { url: string; palette: ScenePalette }) {
  const geometry = useStl(url);
  if (!geometry) return null;
  return (
    <mesh geometry={geometry} raycast={() => undefined} name="house_context">
      <meshStandardMaterial color={palette.table} transparent opacity={0.22} depthWrite={false} side={DoubleSide} />
    </mesh>
  );
}

export interface HouseInfo {
  /** Ausdehnung des Gebäudes (x, y, z) in mm, aus `ProjectInfo.building_mm`. */
  size: readonly number[];
  contextUrl: string;
}

interface WallPreviewProps {
  walls: readonly WallEntry[];
  wallId: string | null;
  /** URL des Wandmeshes (STL, mm): Frame L für das Raster, `building` für die Hausansicht. */
  meshUrl: (wallId: string, frame?: WallFrame) => string;
  onSelect: (wallId: string) => void;
  /** Nur die gewählte Wand zeigen (Schritt „Zerlegen & prüfen“ vor dem ersten Lauf). */
  onlySelected?: boolean;
  /** Hausansicht verfügbar (IFC-Gebäude); ohne sie gibt es nur das Raster. */
  house?: HouseInfo | null;
  view?: WallView;
  onViewChange?: (view: WallView) => void;
}

/** Eigene 3D-Ansicht der Wände (Schritt 1): Auswahl per Klick auf Wand oder Namensschild, synchron zur Liste. */
export function WallPreview({ walls, wallId, meshUrl, onSelect, onlySelected = false, house = null, view = 'raster', onViewChange }: WallPreviewProps) {
  const palette = useScenePalette();
  const shown = useMemo(() => (onlySelected ? walls.filter((w) => w.wall_id === wallId) : walls), [walls, wallId, onlySelected]);
  const asHouse = house !== null && view === 'haus' && !onlySelected;
  const { slots, width, height } = useMemo(() => layoutWalls(shown), [shown]);
  const cx = width / 2;
  const cz = height / 2;
  // Abstand so, dass die Anordnung ins Bild passt (fov 38°).
  const dist = Math.max(width * 0.95, height * 1.6, 3000);
  const houseView = useMemo(() => (house ? houseCamera(house.size) : null), [house]);
  const target: Vec3 = asHouse && houseView ? houseView.target : [cx, 0, cz];
  const camera = useMemo(
    () => ({
      position: asHouse && houseView ? houseView.position : ([cx + dist * 0.08, -dist, cz + dist * 0.1] as Vec3),
      up: [0, 0, 1] as Vec3,
      fov: 38,
      near: 20,
      far: 100000,
    }),
    [asHouse, houseView, cx, cz, dist],
  );
  const gridSize = asHouse && house ? Math.max(house.size[0] ?? 0, house.size[1] ?? 0, 6000) * 2 : Math.max(width, 6000) * 2;
  const gridAt: Vec3 = asHouse ? [target[0], target[1], 0] : [cx, 0, 0];
  const onSelectStable = useCallback((id: string) => onSelect(id), [onSelect]);
  return (
    <div
      style={{ position: 'absolute', inset: 0, background: 'var(--mantine-color-body)' }}
      data-testid="wall-preview"
      data-selected-wall={wallId ?? ''}
      data-wall-count={slots.length}
      data-view={asHouse ? 'haus' : 'raster'}
    >
      <Canvas
        key={`${asHouse ? 'haus' : 'raster'}-${slots.length}-${Math.round(width)}-${Math.round(height)}`}
        camera={camera}
        gl={{ preserveDrawingBuffer: true, antialias: true }}
      >
        <color attach="background" args={[palette.background]} />
        <hemisphereLight args={['#ffffff', '#667788', 0.9]} position={[0, 0, 1]} />
        <directionalLight position={[3000, -4000, 6000]} intensity={1.5} />
        <directionalLight position={[-3000, 2000, 1500]} intensity={0.4} />
        <gridHelper args={[gridSize, 40, palette.table, palette.floor]} rotation={[Math.PI / 2, 0, 0]} position={gridAt} />
        {asHouse && house
          ? (
              <>
                {shown.map((wall) => (
                  <HouseWall
                    key={wall.wall_id}
                    wall={wall}
                    selected={wall.wall_id === wallId}
                    palette={palette}
                    url={meshUrl(wall.wall_id, 'building')}
                    onSelect={onSelectStable}
                  />
                ))}
                <HouseContext url={house.contextUrl} palette={palette} />
              </>
            )
          : slots.map((slot) => (
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
        <OrbitControls makeDefault target={target} />
      </Canvas>
      {house && onViewChange && !onlySelected ? (
        <SegmentedControl
          size="xs"
          value={asHouse ? 'haus' : 'raster'}
          onChange={(v) => onViewChange(v === 'haus' ? 'haus' : 'raster')}
          data={[
            { label: 'Wände nebeneinander', value: 'raster' },
            { label: 'Haus', value: 'haus' },
          ]}
          style={{ position: 'absolute', top: 12, left: 16 }}
          data-testid="wall-view-toggle"
        />
      ) : null}
      <div style={{ position: 'absolute', left: 16, bottom: 12, pointerEvents: 'none', fontSize: 12, color: 'var(--mantine-color-dimmed)' }}>
        {onlySelected
          ? 'Gewählte Wand (Frame L)'
          : `Wand anklicken oder in der Liste wählen. Rot: ungeeignet.${asHouse ? ' Grau: übrige Bauteile.' : ''}`}
      </div>
    </div>
  );
}

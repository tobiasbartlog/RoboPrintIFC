import { ActionIcon, Box, Group, Text, Tooltip, VisuallyHidden } from '@mantine/core';
import { useRef, useState, type KeyboardEvent, type PointerEvent } from 'react';
import { DEFAULT_PARAMS, spotOf, type ParamValues } from '../state/params';
import {
  describeSpot,
  distanceBeforeRobot,
  moveSpot,
  ROBOT_AXIS_S,
  ROBOT_BASE_R_MM,
  snapSpot,
  SPOT_STEP_MM,
  spotGrid,
  TABLE_S,
  type Spot,
} from '../state/spot';
import { useAppStore } from '../state/storeContext';
import { ResetIcon } from './ParamIcons';

/**
 * Druckplatz als Draufsicht auf den Doosantisch: Roboter oben, vorn unten, +x nach rechts. Ziehen, Klicken oder
 * Pfeiltasten rasten auf das 50-mm-Raster ein. Alle Module eines Laufs stehen dort; eine Änderung macht die
 * Zerlegung veraltet wie jeder andere Parameter.
 */

/** Modulbreite höchstens (`b_max_mm` der Zerlegung), für den gezeichneten Umriss. */
const MODULE_W_MAX = 600;
const PAD = 40;
// SVG-Koordinaten: u = x_S, v = -y_S (Roboter oben, vorn unten).
const VB = { u: TABLE_S.x0 - PAD, v: -(TABLE_S.y1 + PAD), w: TABLE_S.x1 - TABLE_S.x0 + 2 * PAD, h: TABLE_S.y1 - TABLE_S.y0 + 2 * PAD };
const GRID = spotGrid();
const KEYS: Record<string, [number, number]> = {
  ArrowLeft: [-1, 0],
  ArrowRight: [1, 0],
  ArrowUp: [0, 1],
  ArrowDown: [0, -1],
};

const DEFAULT_SPOT: Spot = spotOf(DEFAULT_PARAMS);
const same = (a: Spot, b: Spot) => a.x === b.x && a.y === b.y;

export function SpotPicker({ values }: { values: ParamValues }) {
  const setParam = useAppStore((s) => s.setParam);
  const resetParam = useAppStore((s) => s.resetParam);
  const project = useAppStore((s) => s.project);
  const wallId = useAppStore((s) => s.wallId);
  const svgRef = useRef<SVGSVGElement>(null);
  const [dragging, setDragging] = useState(false);

  const spot = spotOf(values);
  const changed = !same(spot, DEFAULT_SPOT);
  const wall = project?.walls.find((w) => w.wall_id === wallId);
  const modW = Math.min(wall?.length_mm ?? MODULE_W_MAX, MODULE_W_MAX);
  const modT = wall?.thickness_mm ?? 200;

  function set(s: Spot) {
    if (s.x !== spot.x) setParam('spot_x_mm', s.x);
    if (s.y !== spot.y) setParam('spot_y_mm', s.y);
  }

  function fromPointer(e: PointerEvent<SVGSVGElement>): Spot | null {
    const r = svgRef.current?.getBoundingClientRect();
    if (!r || !r.width || !r.height || !Number.isFinite(e.clientX) || !Number.isFinite(e.clientY)) return null;
    const u = VB.u + ((e.clientX - r.left) / r.width) * VB.w;
    const v = VB.v + ((e.clientY - r.top) / r.height) * VB.h;
    return snapSpot(u, -v);
  }

  function onPointerDown(e: PointerEvent<SVGSVGElement>) {
    // Fokus für die Pfeiltasten, aber ohne Scrollen: Sonst springt das Feld beim Ziehen unter dem Zeiger weg.
    e.preventDefault();
    e.currentTarget.focus({ preventScroll: true });
    e.currentTarget.setPointerCapture?.(e.pointerId);
    setDragging(true);
    const s = fromPointer(e);
    if (s) set(s);
  }

  function onPointerMove(e: PointerEvent<SVGSVGElement>) {
    if (!dragging) return;
    const s = fromPointer(e);
    if (s) set(s);
  }

  function onKeyDown(e: KeyboardEvent<SVGSVGElement>) {
    const step = KEYS[e.key];
    if (step) set(moveSpot(spot, step[0], step[1]));
    else if (e.key === 'Home') set(DEFAULT_SPOT);
    else return;
    e.preventDefault();
  }

  return (
    <Box data-testid="spot-picker" data-changed={changed}>
      <Group gap={6} wrap="nowrap" align="center" justify="space-between">
        <Group gap={4} wrap="nowrap">
          <Box
            component="span"
            style={{
              display: 'inline-block',
              width: 6,
              height: 6,
              borderRadius: '50%',
              background: changed ? 'var(--mantine-primary-color-filled)' : 'transparent',
            }}
          >
            {changed ? <VisuallyHidden component="span">geändert</VisuallyHidden> : null}
          </Box>
          <Text id="spot-label" fz={{ base: 'xs', lg: 'sm' }} fw={changed ? 700 : 400}>
            Druckplatz
          </Text>
        </Group>
        <Box w={22} style={{ flexShrink: 0 }}>
          {changed ? (
            <Tooltip label="Auf Standard zurücksetzen" withArrow>
              <ActionIcon
                size="sm"
                variant="subtle"
                aria-label="Druckplatz auf Standard zurücksetzen"
                onClick={() => {
                  resetParam('spot_x_mm');
                  resetParam('spot_y_mm');
                }}
                data-testid="spot-reset"
              >
                <ResetIcon />
              </ActionIcon>
            </Tooltip>
          ) : null}
        </Box>
      </Group>
      <svg
        ref={svgRef}
        viewBox={`${VB.u} ${VB.v} ${VB.w} ${VB.h}`}
        style={{ width: '100%', aspectRatio: `${VB.w} / ${VB.h}`, display: 'block', touchAction: 'none', cursor: dragging ? 'grabbing' : 'pointer' }}
        role="group"
        aria-roledescription="Rastfeld"
        aria-labelledby="spot-label"
        aria-describedby="spot-desc"
        tabIndex={0}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={() => setDragging(false)}
        onPointerCancel={() => setDragging(false)}
        onKeyDown={onKeyDown}
        data-testid="spot-field"
      >
        <rect
          x={TABLE_S.x0}
          y={-TABLE_S.y1}
          width={TABLE_S.x1 - TABLE_S.x0}
          height={TABLE_S.y1 - TABLE_S.y0}
          rx={12}
          fill="var(--mantine-color-default-hover)"
          stroke="var(--mantine-color-default-border)"
          strokeWidth={6}
        />
        <path d="M -40 0 H 40 M 0 -40 V 40" stroke="var(--mantine-color-dimmed)" strokeWidth={5} />
        <circle
          cx={ROBOT_AXIS_S.x}
          cy={-ROBOT_AXIS_S.y}
          r={ROBOT_BASE_R_MM}
          fill="var(--mantine-color-dimmed)"
          fillOpacity={0.45}
          stroke="var(--mantine-color-dimmed)"
          strokeWidth={4}
        />
        <circle cx={ROBOT_AXIS_S.x} cy={-ROBOT_AXIS_S.y} r={14} fill="var(--mantine-color-text)" />
        <text x={150} y={-ROBOT_AXIS_S.y + 12} fontSize={44} fill="var(--mantine-color-dimmed)">
          Roboter
        </text>
        <text x={0} y={TABLE_S.y1 + 34} fontSize={34} textAnchor="middle" fill="var(--mantine-color-dimmed)">
          vorn
        </text>
        {GRID.map((g) => (
          <circle key={`${g.x}_${g.y}`} cx={g.x} cy={-g.y} r={9} fill="var(--mantine-color-dimmed)" fillOpacity={0.7} />
        ))}
        <circle cx={DEFAULT_SPOT.x} cy={-DEFAULT_SPOT.y} r={24} fill="none" stroke="var(--mantine-color-dimmed)" strokeWidth={5} />
        <rect
          x={spot.x - modW / 2}
          y={-spot.y - modT / 2}
          width={modW}
          height={modT}
          rx={6}
          fill="var(--mantine-primary-color-light)"
          stroke="var(--mantine-primary-color-filled)"
          strokeWidth={8}
          data-testid="spot-module"
        />
        <circle cx={spot.x} cy={-spot.y} r={16} fill="var(--mantine-primary-color-filled)" />
      </svg>
      <Text size="xs" c="dimmed" pl={10} id="spot-desc" aria-live="polite" data-testid="spot-desc">
        {describeSpot(spot)} · {distanceBeforeRobot(spot).toLocaleString('de-DE')} mm vor der Roboterachse
        {changed ? '' : ' · Standard, empfohlen'}
      </Text>
      <Text size="xs" c="dimmed" pl={10}>
        Ziehen oder Pfeiltasten, rastet auf {SPOT_STEP_MM} mm ein. Alle Module stehen hier, die lange
        Seite zum Roboter.
      </Text>
    </Box>
  );
}

import type { ReactNode } from 'react';
import type { ParamGroupId } from '../state/params';

/** Schlichte Strich-Icons (24er Raster, `currentColor`), damit keine Icon-Bibliothek nötig ist. */
function Svg({ size = 18, children }: { size?: number; children: ReactNode }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      style={{ flexShrink: 0, display: 'block' }}
    >
      {children}
    </svg>
  );
}

const GROUP_PATHS: Record<ParamGroupId, ReactNode> = {
  // Schichten übereinander
  layer: (
    <>
      <path d="M12 4l8 4l-8 4l-8 -4z" />
      <path d="M4 12l8 4l8 -4" />
      <path d="M4 16l8 4l8 -4" />
    </>
  ),
  // Modul als Quader
  module: (
    <>
      <path d="M12 3l8 4.5v9l-8 4.5l-8 -4.5v-9z" />
      <path d="M4 7.5l8 4.5l8 -4.5" />
      <path d="M12 12v9" />
    </>
  ),
  // Tacho
  speed: (
    <>
      <path d="M4 16a8 8 0 1 1 16 0" />
      <path d="M12 16l4 -5" />
      <circle cx="12" cy="16" r="1" />
    </>
  ),
  // Tropfen
  pump: <path d="M12 3c-3 4 -6 7.5 -6 11a6 6 0 0 0 12 0c0 -3.5 -3 -7 -6 -11z" />,
  // Bahn mit Pfeil
  motion: (
    <>
      <path d="M4 19c0 -6 6 -4 8 -8s4 -5 8 -5" />
      <path d="M16 4l4 2l-2 4" />
    </>
  ),
  // Abstand zwischen zwei Kanten
  clearance: (
    <>
      <path d="M4 5v14" />
      <path d="M20 5v14" />
      <path d="M7 12h10" />
      <path d="M10 9l-3 3l3 3" />
      <path d="M14 9l3 3l-3 3" />
    </>
  ),
  // Stützpunkte einer Bahn
  planning: (
    <>
      <path d="M5 18l5 -6l4 3l5 -8" />
      <circle cx="5" cy="18" r="1.5" />
      <circle cx="10" cy="12" r="1.5" />
      <circle cx="14" cy="15" r="1.5" />
      <circle cx="19" cy="7" r="1.5" />
    </>
  ),
  // Ausgabe
  control: (
    <>
      <path d="M12 4v11" />
      <path d="M8 8l4 -4l4 4" />
      <path d="M5 14v5h14v-5" />
    </>
  ),
};

export function GroupIcon({ id }: { id: ParamGroupId }) {
  return <Svg>{GROUP_PATHS[id]}</Svg>;
}

export function ResetIcon() {
  return (
    <Svg size={14}>
      <path d="M4 12a8 8 0 1 0 2.5 -5.8" />
      <path d="M4 4v4h4" />
    </Svg>
  );
}

export function SearchIcon() {
  return (
    <Svg size={14}>
      <circle cx="10.5" cy="10.5" r="6.5" />
      <path d="M20 20l-4.8 -4.8" />
    </Svg>
  );
}

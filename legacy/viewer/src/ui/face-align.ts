/**
 * Face-Align: reine Positionier-Mathematik für den Endeffektor-Konfigurator
 * (Issue #52) — **three.js-frei**, damit sie per vitest prüfbar ist.
 *
 * Statt ein Mesh per Frei-Drag-Gizmo auszurichten (dessen World/Local-Rückrechnung
 * am `matrixAutoUpdate=false`-Flansch ein kaputtes TCP erzeugte, #28/#52), wählt
 * der Nutzer eine **Fläche** des Endeffektors. Aus deren Normale + Zentroid
 * (Mesh-lokale Koordinaten) rechnen wir die Flansch-lokalen Transforms **direkt**:
 *
 *  - `mountFaceToFlange` legt die Fläche bündig auf die Flanschebene, ihre
 *    Außennormale zeigt in den Arm (−Flansch-z), der Körper ragt weg (+z); das
 *    Flächen-Zentroid landet im Flansch-Ursprung. Ein Winkel dreht zusätzlich um
 *    die Flansch-z-Achse.
 *  - `autoTcpAlongFlangeZ` setzt den TCP auf den entlang +Flansch-z am weitesten
 *    entfernten Mesh-Punkt (die Spitze).
 *  - `planarRegionCentroid` wächst um ein angeklicktes Dreieck die
 *    zusammenhängende ebene Fläche und liefert ihren Mittelpunkt — TCP per
 *    Klick auf die Extruderöffnung (Issue #54); `tcpAtPosition` für die freie
 *    x/y/z-Eingabe relativ zum Flansch.
 *
 * Konvention (ADR-006): Millimeter, Einheitsquaternion **[w, x, y, z]**.
 */

export type Vec3 = [number, number, number];
export type Quat = [number, number, number, number]; // [w, x, y, z]

export interface Frame {
  pos_mm: Vec3;
  quat: Quat;
}

const EPS = 1e-9;

function dot(a: Vec3, b: Vec3): number {
  return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}
function cross(a: Vec3, b: Vec3): Vec3 {
  return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
}
function length(a: Vec3): number {
  return Math.hypot(a[0], a[1], a[2]);
}
function normalize(a: Vec3): Vec3 {
  const n = length(a) || 1;
  return [a[0] / n, a[1] / n, a[2] / n];
}

/** Quaternion [w,x,y,z] aus Einheitsachse + Winkel (rad). */
export function quatFromAxisAngle(axis: Vec3, angleRad: number): Quat {
  const a = normalize(axis);
  const h = angleRad / 2;
  const s = Math.sin(h);
  return [Math.cos(h), a[0] * s, a[1] * s, a[2] * s];
}

/** Hamilton-Produkt: `mul(a, b)` wendet erst `b`, dann `a` an (Rotationen komponieren). */
export function quatMul(a: Quat, b: Quat): Quat {
  const [aw, ax, ay, az] = a;
  const [bw, bx, by, bz] = b;
  return [
    aw * bw - ax * bx - ay * by - az * bz,
    aw * bx + ax * bw + ay * bz - az * by,
    aw * by - ax * bz + ay * bw + az * bx,
    aw * bz + ax * by - ay * bx + az * bw,
  ];
}

/** Dreht einen Vektor mit dem Quaternion (v' = q · v · q⁻¹). */
export function quatRotate(q: Quat, v: Vec3): Vec3 {
  const u: Vec3 = [q[1], q[2], q[3]];
  const t = cross(u, v);
  const t2: Vec3 = [2 * t[0], 2 * t[1], 2 * t[2]];
  const c = cross(u, t2);
  return [v[0] + q[0] * t2[0] + c[0], v[1] + q[0] * t2[1] + c[1], v[2] + q[0] * t2[2] + c[2]];
}

/**
 * Kürzeste Rotation, die `from` auf `to` dreht (beide beliebig lang). Behandelt
 * den Antiparallel-Fall (180°) mit einer stabilen senkrechten Achse.
 */
export function quatBetween(from: Vec3, to: Vec3): Quat {
  const f = normalize(from);
  const t = normalize(to);
  const d = dot(f, t);
  if (d >= 1 - EPS) return [1, 0, 0, 0]; // schon gleich
  if (d <= -1 + EPS) {
    // Antiparallel: 180° um eine beliebige Achse ⟂ f.
    let axis = cross(f, [1, 0, 0]);
    if (length(axis) < EPS) axis = cross(f, [0, 1, 0]);
    return quatFromAxisAngle(normalize(axis), Math.PI);
  }
  const axis = normalize(cross(f, t));
  return quatFromAxisAngle(axis, Math.acos(Math.max(-1, Math.min(1, d))));
}

/**
 * Düsen-/Extrusionsrichtung → TCP-Quaternion (Issue #58): dreht die TCP-z-Achse
 * `[0,0,1]` per kürzester Rotation auf die **nach außen orientierte
 * Öffnungsnormale**. Damit ist die TCP-z-Achse = Extrusions-/Düsenachse, und die
 * kanonische Druck-Orientierung (NOZZLE_DOWN, Core) führt die echte Düse
 * senkrecht nach unten statt der Flanschachse. Der Klick auf die Öffnungsfläche
 * (`planarRegionCentroid`) liefert die Normale; sie muss vor dem Aufruf in
 * Flansch-Koordinaten gedreht sein (Rotation der Montage-Lage).
 *
 * Golden: `+x ⇒ 90° um y` (`[√½,0,√½,0]`), `+y ⇒ −90° um x` (`[√½,−√½,0,0]`),
 * `+z ⇒ Identität`, `−z ⇒ 180° um y` (`[0,0,1,0]`).
 */
export function nozzleQuatFromNormal(normal: Vec3): Quat {
  return quatBetween([0, 0, 1], normal);
}

/**
 * Mesh-Transform (Flansch-lokal), der die gewählte Fläche bündig an den Flansch
 * legt: die **Außennormale** der Fläche zeigt in den Arm (−z), der Körper ragt
 * weg (+z), das Flächen-Zentroid landet im Flansch-Ursprung. `rotationDeg` dreht
 * zusätzlich um die Flansch-z-Achse (Feinausrichtung).
 *
 * `faceNormal`/`faceCentroid` sind in **Mesh-lokalen** Koordinaten (Rohgeometrie,
 * vor jedem Transform).
 */
export function mountFaceToFlange(
  faceNormal: Vec3,
  faceCentroid: Vec3,
  rotationDeg = 0,
): Frame {
  // Außennormale der Montagefläche zeigt in den Arm (−Flansch-z).
  const align = quatBetween(faceNormal, [0, 0, -1]);
  const spin = quatFromAxisAngle([0, 0, 1], (rotationDeg * Math.PI) / 180);
  const q = quatMul(spin, align); // erst ausrichten, dann um z drehen
  // Zentroid → Flansch-Ursprung: pos = −(R · centroid).
  const rc = quatRotate(q, faceCentroid);
  return { pos_mm: [-rc[0], -rc[1], -rc[2]], quat: q };
}

/**
 * Platziert die **Roboterbasis auf einer Fläche** (Workstation-Editor, Issue #78) —
 * das Vorzeichen-gedrehte Gegenstück zu {@link mountFaceToFlange}: statt ein
 * Werkzeug unter den Flansch zu hängen (Normale → −z, Körper unter dem Flansch)
 * *stellt* diese Funktion die Basis **oben auf** die gewählte Fläche: die
 * Basis-+z-Achse zeigt entlang der (nach außen/oben zeigenden) Flächennormale, der
 * Basis-Ursprung sitzt im gewählten Flächenpunkt (Mittelpunkt oder erkanntes
 * Bohrbild-Zentrum), `rotationDeg` dreht zusätzlich um diese Normale.
 *
 * `faceNormal`/`facePoint` sind in **Workstation-/Mesh-lokalen** Koordinaten. Das
 * Ergebnis ist der `robot_base_frame` (Basis relativ zum Mesh-Ursprung). Die
 * Konvention ist bit-gleich zum Core-Matcher (`fgc.geometry.holes.base_mount_to_frame`):
 * `q = spin ∘ align`, Quaternion [w, x, y, z].
 */
export function mountBaseToSurface(
  faceNormal: Vec3,
  facePoint: Vec3,
  rotationDeg = 0,
): Frame {
  const align = quatBetween([0, 0, 1], faceNormal); // Basis-+z → Flächennormale
  const spin = quatFromAxisAngle(faceNormal, (rotationDeg * Math.PI) / 180); // Drehung um die Normale
  const q = quatMul(spin, align); // erst ausrichten, dann um die Normale drehen
  return { pos_mm: [facePoint[0], facePoint[1], facePoint[2]], quat: q };
}

/**
 * Verschiebt einen Frame um einen **Flansch-lokalen** Versatz (Feinjustage der
 * Montage, #67): die Translation wird direkt addiert, die Rotation bleibt
 * unverändert. Damit lässt sich ein asymmetrischer Flächen-Mittelpunkt — dessen
 * flächengewichtetes Zentroid nicht auf der Flanschmitte liegt — nachträglich
 * unter den Flansch schieben, ohne die bündige Ausrichtung zu verlieren
 * (x/y in der Flanschebene, z entlang der Flansch-Achse).
 */
export function offsetFrame(frame: Frame, offsetMm: Vec3): Frame {
  return {
    pos_mm: [
      frame.pos_mm[0] + offsetMm[0],
      frame.pos_mm[1] + offsetMm[1],
      frame.pos_mm[2] + offsetMm[2],
    ],
    quat: frame.quat,
  };
}

/** Wendet einen Frame (Rotation + Translation) auf einen Mesh-Punkt an. */
export function applyFrame(frame: Frame, v: Vec3): Vec3 {
  const r = quatRotate(frame.quat, v);
  return [r[0] + frame.pos_mm[0], r[1] + frame.pos_mm[1], r[2] + frame.pos_mm[2]];
}

/**
 * TCP-Frame (Flansch-lokal): der entlang +Flansch-z am weitesten entfernte
 * Mesh-Punkt nach Anwendung von `meshTransform` — die Spitze. Orientierung
 * identisch (Einheitsquaternion); die Druck-Orientierung sitzt im Ziel (#51).
 * Wirft bei leerer Vertex-Liste.
 */
export function autoTcpAlongFlangeZ(vertices: Vec3[], meshTransform: Frame): Frame {
  if (vertices.length === 0) throw new Error("autoTcpAlongFlangeZ: keine Vertices");
  let tip = applyFrame(meshTransform, vertices[0]);
  for (let i = 1; i < vertices.length; i++) {
    const p = applyFrame(meshTransform, vertices[i]);
    if (p[2] > tip[2]) tip = p;
  }
  return { pos_mm: tip, quat: [1, 0, 0, 0] };
}

/** TCP rein über einen Abstand entlang der Flansch-z-Achse (Zahlenfeld-Justage). */
export function tcpAtDistance(distanceMm: number): Frame {
  return { pos_mm: [0, 0, distanceMm], quat: [1, 0, 0, 0] };
}

/** TCP aus frei eingegebenen Flansch-Koordinaten (Issue #54); leere Achse = 0. */
export function tcpAtPosition(x: number, y: number, z: number): Frame {
  return { pos_mm: [x || 0, y || 0, z || 0], quat: [1, 0, 0, 0] };
}

/** Ergebnis von {@link planarRegionCentroid}: Mittelpunkt + Normale der Fläche. */
export interface PlanarFace {
  /** Flächen-Mittelpunkt (flächengewichtet), im Koordinatenraum der Eingabe. */
  centroid: Vec3;
  /** Normale des Start-Dreiecks (Einheitsvektor). */
  normal: Vec3;
  /** Anzahl Dreiecke der gewachsenen Region (Diagnose/Tests). */
  triangleCount: number;
}

/** Eine zusammenhängende ebene Fläche: Mittelpunkt, Normale, Dreiecks-Indizes. */
export interface PlanarRegion {
  centroid: Vec3;
  normal: Vec3;
  /** Indizes der Region-Dreiecke in der Soup (für die Hover-Hervorhebung, #55). */
  triangles: number[];
}

/** Max. Winkel (°) zwischen Dreiecksnormalen derselben ebenen Fläche. */
const REGION_NORMAL_TOL_DEG = 5;
/** Max. Abstand (mm) eines Region-Vertex von der Ebene des Start-Dreiecks. */
const REGION_PLANE_TOL_MM = 0.5;
/** Rundung (mm) für den Vertex-Schlüssel — STL-Soup dupliziert Eckpunkte. */
const VERTEX_KEY_QUANTUM_MM = 1e-3;

function triNormalAndArea(a: Vec3, b: Vec3, c: Vec3): { normal: Vec3; area: number } {
  const ab: Vec3 = [b[0] - a[0], b[1] - a[1], b[2] - a[2]];
  const ac: Vec3 = [c[0] - a[0], c[1] - a[1], c[2] - a[2]];
  const n = cross(ab, ac);
  const len = length(n);
  return { normal: len > EPS ? [n[0] / len, n[1] / len, n[2] / len] : [0, 0, 0], area: len / 2 };
}

function vertexKey(v: Vec3): string {
  const q = VERTEX_KEY_QUANTUM_MM;
  return `${Math.round(v[0] / q)},${Math.round(v[1] / q)},${Math.round(v[2] / q)}`;
}

/**
 * Region-Growing über eine Dreiecks-Soup (`positions`, 3 Einträge je Dreieck,
 * mesh-lokal mm) — findet die **zusammenhängende ebene Fläche** um ein
 * Start-Dreieck (Issue #54/#55, Montage-Zentrierung + TCP auf der
 * Extruderöffnung): Nachbarn teilen mindestens einen (quantisierten)
 * Eckpunkt, ihre Normale weicht ≤ 5° von der Start-Normale ab und alle
 * Eckpunkte liegen ≤ 0.5 mm neben der Start-Ebene. Getrennte koplanare
 * Flächen (z. B. die Gegenseite eines Rings) wachsen nicht mit.
 *
 * Die Nachbarschaftskarte wird **einmal** beim Bau berechnet, gefundene
 * Regionen werden für **alle** ihre Mitglieds-Dreiecke gecacht — so bleibt
 * das Hover über eine große Fläche (#55) nach dem ersten Treffer kostenlos.
 */
export class PlanarRegionIndex {
  private readonly byVertex = new Map<string, number[]>();
  private readonly regionByTriangle = new Map<number, PlanarRegion>();
  private readonly triCount: number;

  constructor(private readonly positions: Vec3[]) {
    this.triCount = Math.floor(positions.length / 3);
    for (let i = 0; i < this.triCount; i++) {
      for (const v of this.tri(i)) {
        const key = vertexKey(v);
        const list = this.byVertex.get(key);
        if (list) list.push(i);
        else this.byVertex.set(key, [i]);
      }
    }
  }

  private tri(i: number): [Vec3, Vec3, Vec3] {
    return [this.positions[i * 3], this.positions[i * 3 + 1], this.positions[i * 3 + 2]];
  }

  /** Ebene Fläche um `startTriangle` — flächengewichteter Mittelpunkt, gecacht. */
  regionAt(startTriangle: number): PlanarRegion {
    if (startTriangle < 0 || startTriangle >= this.triCount) {
      throw new Error(`PlanarRegionIndex: Start-Dreieck ${startTriangle} von ${this.triCount}`);
    }
    const cached = this.regionByTriangle.get(startTriangle);
    if (cached) return cached;

    const [sa] = this.tri(startTriangle);
    const start = triNormalAndArea(...this.tri(startTriangle));
    const cosTol = Math.cos((REGION_NORMAL_TOL_DEG * Math.PI) / 180);
    const inRegion = (i: number): boolean => {
      const [a, b, c] = this.tri(i);
      const { normal } = triNormalAndArea(a, b, c);
      if (dot(normal, start.normal) < cosTol) return false;
      for (const v of [a, b, c]) {
        const d: Vec3 = [v[0] - sa[0], v[1] - sa[1], v[2] - sa[2]];
        if (Math.abs(dot(d, start.normal)) > REGION_PLANE_TOL_MM) return false;
      }
      return true;
    };

    const visited = new Set<number>([startTriangle]);
    const queue = [startTriangle];
    let areaSum = 0;
    const weighted: Vec3 = [0, 0, 0];
    while (queue.length > 0) {
      const i = queue.pop() as number;
      const [a, b, c] = this.tri(i);
      const { area } = triNormalAndArea(a, b, c);
      areaSum += area;
      weighted[0] += ((a[0] + b[0] + c[0]) / 3) * area;
      weighted[1] += ((a[1] + b[1] + c[1]) / 3) * area;
      weighted[2] += ((a[2] + b[2] + c[2]) / 3) * area;
      for (const v of [a, b, c]) {
        for (const j of this.byVertex.get(vertexKey(v)) ?? []) {
          if (visited.has(j)) continue;
          if (!inRegion(j)) continue;
          visited.add(j);
          queue.push(j);
        }
      }
    }

    const s = areaSum > EPS ? areaSum : 1;
    const region: PlanarRegion = {
      centroid: [weighted[0] / s, weighted[1] / s, weighted[2] / s],
      normal: start.normal,
      triangles: [...visited],
    };
    for (const i of region.triangles) this.regionByTriangle.set(i, region);
    return region;
  }
}

/** Einmal-Aufruf ohne Index-Wiederverwendung (Tests/kleine Soups, Issue #54). */
export function planarRegionCentroid(positions: Vec3[], startTriangle: number): PlanarFace {
  const region = new PlanarRegionIndex(positions).regionAt(startTriangle);
  return {
    centroid: region.centroid,
    normal: region.normal,
    triangleCount: region.triangles.length,
  };
}

/**
 * Mesh-Transform, der die **Bounding-Box-Mitte** des Mesh in den Flansch-Ursprung
 * legt (Identitäts-Rotation). Default beim Upload (Issue #52): der Endeffektor
 * sitzt sofort **am Flansch** statt an seinem Geometrie-Ursprung wegzuschweben —
 * bis der Nutzer die Montagefläche anklickt (`mountFaceToFlange`).
 */
export function centerAtFlange(vertices: Vec3[]): Frame {
  if (vertices.length === 0) return { pos_mm: [0, 0, 0], quat: [1, 0, 0, 0] };
  const mn: Vec3 = [...vertices[0]];
  const mx: Vec3 = [...vertices[0]];
  for (const v of vertices) {
    for (let i = 0; i < 3; i++) {
      if (v[i] < mn[i]) mn[i] = v[i];
      if (v[i] > mx[i]) mx[i] = v[i];
    }
  }
  return {
    pos_mm: [-(mn[0] + mx[0]) / 2, -(mn[1] + mx[1]) / 2, -(mn[2] + mx[2]) / 2],
    quat: [1, 0, 0, 0],
  };
}

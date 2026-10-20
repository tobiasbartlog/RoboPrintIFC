import { Color, Group, Mesh, MeshStandardMaterial, type Material, type Object3D } from 'three';
import URDFLoader, { type URDFRobot } from 'urdf-loader';
import { FLANGE_LINK } from './tcp';

export const JOINT_NAMES = ['joint_1', 'joint_2', 'joint_3', 'joint_4', 'joint_5', 'joint_6'] as const;
export const ANCHOR_NAME = 'flange_anchor';

export interface ParseOptions {
  /** Basis-URL des Pakets `dsr_description2` (Ordner mit `meshes/`). */
  packageBase: string;
  /** Ersatz fuer das Mesh-Laden (Tests); Default ist der Mesh-Lader von urdf-loader. */
  loadMesh?: (url: string, done: (mesh: Object3D, err?: Error) => void) => void;
}

/**
 * URDF-Text nach Roboter-Objekt (Einheiten der URDF: m). Haengt am Flansch-Glied einen Anker
 * mit Skalierung 1/1000 an: Kinder des Ankers (Werkzeug, TCP-Marke) sind in mm bezogen auf den
 * Flansch, wenn der Roboter unter einer Gruppe mit Skalierung 1000 haengt.
 */
export function parseRobot(urdfText: string, opts: ParseOptions): URDFRobot {
  const loader = new URDFLoader();
  loader.packages = () => opts.packageBase;
  const stub = opts.loadMesh;
  if (stub) {
    loader.loadMeshCb = (url, _manager, _material, done) => stub(url, done);
  }
  const robot = loader.parse(urdfText);
  const flange = robot.links[FLANGE_LINK];
  if (flange) {
    const anchor = new Group();
    anchor.name = ANCHOR_NAME;
    anchor.scale.setScalar(0.001);
    flange.add(anchor);
  }
  return robot;
}

export async function loadRobot(urdfUrl: string, packageBase: string, signal?: AbortSignal): Promise<URDFRobot> {
  const res = await fetch(urdfUrl, { signal });
  if (!res.ok) throw new Error(`URDF nicht ladbar (${res.status}): ${urdfUrl}`);
  return parseRobot(await res.text(), { packageBase });
}

/** Gelenkwinkel in Doosan-Konvention (= URDF) setzen und Matrizen aktualisieren. */
export function applyQ(robot: URDFRobot, q: readonly number[]): void {
  JOINT_NAMES.forEach((name, i) => {
    robot.joints[name]?.setJointValue(q[i] ?? 0);
  });
  robot.updateMatrixWorld(true);
}

export function flangeOf(robot: URDFRobot): Object3D | undefined {
  return robot.links[FLANGE_LINK];
}

export function anchorOf(robot: URDFRobot): Object3D | undefined {
  return flangeOf(robot)?.getObjectByName(ANCHOR_NAME);
}

/** Meshes der sichtbaren Geometrie eines Glieds (ohne die Kind-Glieder). */
function visualMeshes(link: Object3D): Mesh[] {
  const out: Mesh[] = [];
  for (const child of link.children) {
    if ((child as { isURDFVisual?: boolean }).isURDFVisual) {
      child.traverse((o) => {
        if ((o as Mesh).isMesh) out.push(o as Mesh);
      });
    }
  }
  return out;
}

interface TintData {
  base: Material | Material[];
  tinted: MeshStandardMaterial;
}

/** Faerbt Glieder (Name -> Farbe) ein; alle anderen Glieder erhalten ihr Original zurueck. */
export function tintLinks(robot: URDFRobot, colors: ReadonlyMap<string, Color>): void {
  for (const [name, link] of Object.entries(robot.links)) {
    const color = colors.get(name);
    for (const mesh of visualMeshes(link)) {
      const data = mesh.userData as { tint?: TintData };
      if (color) {
        if (!data.tint) {
          data.tint = { base: mesh.material, tinted: new MeshStandardMaterial({ roughness: 0.6 }) };
        }
        data.tint.tinted.color.copy(color);
        data.tint.tinted.emissive.copy(color).multiplyScalar(0.35);
        mesh.material = data.tint.tinted;
      } else if (data.tint) {
        mesh.material = data.tint.base;
      }
    }
  }
}

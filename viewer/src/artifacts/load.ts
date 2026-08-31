/**
 * Laufordner laden — zwei Wege, beide zustandslos:
 * 1. Ordner-Picker / Drag&Drop (FileList mit webkitdirectory)
 * 2. ?run=<url-basis> für Dev/Automation (fetch über den Vite-Server)
 *
 * Die binäre Modell-glTF (model.glb, Issue #6) wird hier nicht geparst, sondern
 * nur als URL durchgereicht — der GLTFLoader lädt sie im Renderpfad. Im
 * FileList-Fall wird dazu eine Objekt-URL erzeugt, im URL-Fall der /@fs-Pfad.
 */

import type { BuildingContext, Candidates, ModelMap, RunData, Toolpath, Trajectory, WallSpec } from "./types";

const WALLSPEC = "wallspec.json";
const TOOLPATH = "toolpath.json";
const CONTEXT = "context.json";
const MODEL_MAP = "model_map.json";
const MODEL_GLB = "model.glb";
const CANDIDATES = "candidates.json";
const TRAJECTORY = "trajectory.json";

export async function loadFromFileList(files: FileList): Promise<RunData> {
  let wallspecFile: File | null = null;
  let toolpathFile: File | null = null;
  let contextFile: File | null = null;
  let modelMapFile: File | null = null;
  let modelGlbFile: File | null = null;
  let candidatesFile: File | null = null;
  let trajectoryFile: File | null = null;
  let folderName = "";

  for (const file of Array.from(files)) {
    const rel = file.webkitRelativePath || file.name;
    if (!folderName && rel.includes("/")) folderName = rel.split("/")[0];
    if (file.name === WALLSPEC) wallspecFile = file;
    if (file.name === TOOLPATH) toolpathFile = file;
    if (file.name === CONTEXT) contextFile = file;
    if (file.name === MODEL_MAP) modelMapFile = file;
    if (file.name === MODEL_GLB) modelGlbFile = file;
    if (file.name === CANDIDATES) candidatesFile = file;
    if (file.name === TRAJECTORY) trajectoryFile = file;
  }

  const [wallspec, toolpath, context, modelMap, candidates, trajectory] = await Promise.all([
    wallspecFile ? (JSON.parse(await wallspecFile.text()) as WallSpec) : null,
    toolpathFile ? (JSON.parse(await toolpathFile.text()) as Toolpath) : null,
    contextFile ? (JSON.parse(await contextFile.text()) as BuildingContext) : null,
    modelMapFile ? (JSON.parse(await modelMapFile.text()) as ModelMap) : null,
    candidatesFile ? (JSON.parse(await candidatesFile.text()) as Candidates) : null,
    trajectoryFile ? (JSON.parse(await trajectoryFile.text()) as Trajectory) : null,
  ]);
  // GLB nur zeigen, wenn auch die Zuordnung vorliegt (sonst keine Einfärbung).
  const modelGlbUrl = modelMap && modelGlbFile ? URL.createObjectURL(modelGlbFile) : null;
  return {
    folderName: folderName || "(Auswahl)",
    wallspec,
    toolpath,
    context,
    modelMap,
    modelGlbUrl,
    candidates,
    trajectory,
  };
}

export async function loadFromUrl(base: string): Promise<RunData> {
  const root = base.replace(/\/$/, "");
  const fetchJson = async <T>(name: string): Promise<T | null> => {
    const res = await fetch(`${root}/${name}`);
    // Vite beantwortet fehlende /@fs-Dateien mit der index.html und Status 200
    // (SPA-Fallback) — ein fehlendes Artefakt ist daher nur am Content-Type
    // erkennbar. Kein Lauftyp besitzt alle Artefakte (slice ohne model_map/
    // candidates, walls-list ohne wallspec/toolpath/context).
    if (!res.ok) return null;
    if (!res.headers.get("content-type")?.includes("json")) return null;
    return (await res.json()) as T;
  };
  const [wallspec, toolpath, context, modelMap, candidates, trajectory] = await Promise.all([
    fetchJson<WallSpec>(WALLSPEC),
    fetchJson<Toolpath>(TOOLPATH),
    fetchJson<BuildingContext>(CONTEXT),
    fetchJson<ModelMap>(MODEL_MAP),
    fetchJson<Candidates>(CANDIDATES),
    fetchJson<Trajectory>(TRAJECTORY),
  ]);
  return {
    folderName: root.split("/").filter(Boolean).pop() ?? base,
    wallspec,
    toolpath,
    context,
    modelMap,
    modelGlbUrl: modelMap ? `${root}/${modelMap.mesh_file || MODEL_GLB}` : null,
    candidates,
    trajectory,
  };
}

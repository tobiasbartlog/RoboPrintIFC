import { Canvas, useThree } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Color, Vector3, type PerspectiveCamera } from 'three';
import type { OrbitControls as OrbitControlsImpl } from 'three-stdlib';
import type { URDFRobot } from 'urdf-loader';
import { ContactOverlay } from './ContactOverlay';
import { Part } from './Part';
import { Robot } from './Robot';
import { Tool } from './Tool';
import { ToolpathLines } from './ToolpathLines';
import { Workstation } from './Workstation';
import { DEFAULT_ASSET_BASE, assetUrl, packageBase, urdfUrl } from './assets';
import { mat4FromRows } from './math';
import { useScenePalette } from './palette';
import { tcpFromScene } from './tcp';
import { JOINT_NAMES, flangeOf } from './urdf';
import type { Pose7, SceneApi, SceneSample, SceneViewProps } from './types';

/** Home-Pose (0, 0, 90, 0, 90, 0) Grad in Doosan-Konvention, falls noch kein Sample vorliegt. */
const HOME_Q = [0, 0, Math.PI / 2, 0, Math.PI / 2, 0] as const;

/** Startansicht: schraeg von vorn (Tischseite), Z oben; Ziel zwischen Arbeitsflaeche und Roboter. */
const START_TARGET = new Vector3(780, 850, 1150);
const START_POSITION = new Vector3(2300, -500, 2100);

const FLOOR_NAMES = new Set(['floor']);
const TOOL_NAMES = new Set(['tool_body', 'nozzle_tip']);

function CameraRig({ onFocus }: { onFocus: (fn: (p: readonly [number, number, number]) => void) => void }) {
  const camera = useThree((s) => s.camera);
  const controls = useThree((s) => s.controls) as OrbitControlsImpl | null;
  useEffect(() => {
    onFocus((p) => {
      const target = new Vector3(p[0], p[1], p[2]);
      const offset = camera.position.clone().sub(controls?.target ?? START_TARGET);
      offset.setLength(Math.min(Math.max(offset.length(), 500), 900));
      camera.position.copy(target).add(offset);
      controls?.target.copy(target);
      controls?.update();
    });
  }, [camera, controls, onFocus]);
  return null;
}

function Lights() {
  return (
    <>
      <hemisphereLight args={['#ffffff', '#667788', 0.9]} position={[0, 0, 1]} />
      <directionalLight position={[2500, -1500, 4000]} intensity={1.6} />
      <directionalLight position={[-2000, 2500, 1500]} intensity={0.5} />
    </>
  );
}

/**
 * 3D-Szene (mm, Z oben): Roboter aus der URDF, Doosantisch, Teil mit Schnittebene, Werkzeug am
 * Flansch, Kontaktanzeige. Alles ist eine reine Funktion der Props; die Uhr liegt ausserhalb.
 */
export function SceneView({
  run,
  partId,
  sample,
  highlightedLinks,
  obstacleVisible,
  assetBase = DEFAULT_ASSET_BASE,
  showToolpath = false,
  onApi,
}: SceneViewProps) {
  const palette = useScenePalette();
  const robotRef = useRef<URDFRobot | null>(null);
  const focusRef = useRef<(p: readonly [number, number, number]) => void>(() => {});
  const [robotReady, setRobotReady] = useState(false);
  const [tableReady, setTableReady] = useState(false);
  const [toolReady, setToolReady] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const scene = run?.scene ?? null;
  const loaded = partId && run ? (run.parts[partId] ?? null) : null;
  const ready = robotReady && tableReady && toolReady;

  const T_WB = useMemo(() => (scene ? mat4FromRows(scene.workstation.T_WB) : null), [scene]);
  const q = sample?.q ?? HOME_Q;
  const tintActive = sample && (sample.status === 'collision' || sample.status === 'warn');
  const contactColor = sample?.status === 'collision' ? palette.danger : palette.warn;
  const obstacle = obstacleVisible && tintActive ? (sample.pair?.[1] ?? null) : null;
  const contactLink = tintActive ? (sample.pair?.[0] ?? null) : null;

  const tint = useMemo(() => {
    const m = new Map<string, Color>();
    if (contactLink) m.set(contactLink, new Color(contactColor));
    for (const l of highlightedLinks) m.set(l, new Color(palette.danger));
    return m;
  }, [contactLink, contactColor, highlightedLinks, palette.danger]);
  const toolHit = [...tint.keys()].some((l) => TOOL_NAMES.has(l));

  const onRobot = useCallback((r: URDFRobot | null) => {
    robotRef.current = r;
    setRobotReady(r !== null);
  }, []);
  const onTable = useCallback(() => setTableReady(true), []);
  const onTool = useCallback(() => setToolReady(true), []);
  const onError = useCallback((e: Error) => setError(e.message), []);
  const onFocus = useCallback((fn: (p: readonly [number, number, number]) => void) => {
    focusRef.current = fn;
  }, []);

  // Debug-/Test-Schnittstelle: die gerenderte TCP-Pose kommt aus dem Szenengraphen.
  const tFtRef = useRef(scene?.tool.T_FT);
  tFtRef.current = scene?.tool.T_FT;
  const readyRef = useRef(false);
  readyRef.current = ready;
  useEffect(() => {
    if (!onApi) return;
    const api: SceneApi = {
      tcpRendered: (): Pose7 | null => {
        const flange = robotRef.current && flangeOf(robotRef.current);
        const tFt = tFtRef.current;
        return flange && tFt ? tcpFromScene(flange, tFt) : null;
      },
      jointValues: () => {
        const r = robotRef.current;
        return r ? JOINT_NAMES.map((n) => r.joints[n]?.angle ?? Number.NaN) : null;
      },
      ready: () => readyRef.current,
      focusOn: (p) => focusRef.current(p),
    };
    onApi(api);
    return () => onApi(null);
  }, [onApi]);

  const floorHit = obstacle !== null && FLOOR_NAMES.has(obstacle);

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%', minHeight: 240 }} data-testid="scene-view">
      <Canvas
        frameloop="demand"
        camera={{ position: START_POSITION.toArray(), up: [0, 0, 1], fov: 38, near: 20, far: 30000 }}
        gl={{ preserveDrawingBuffer: true, antialias: true }}
        onCreated={({ gl, camera }) => {
          gl.localClippingEnabled = true;
          camera.up.set(0, 0, 1);
          (camera as PerspectiveCamera).lookAt(START_TARGET);
        }}
      >
        <color attach="background" args={[palette.background]} />
        <Lights />
        <gridHelper
          args={[4000, 40, palette.table, palette.floor]}
          rotation={[Math.PI / 2, 0, 0]}
          position={[790, 615, -1]}
        />
        {floorHit && (
          <mesh position={[790, 615, -2]} name="floor_hit">
            <planeGeometry args={[4000, 4000]} />
            <meshBasicMaterial color={contactColor} transparent opacity={0.25} />
          </mesh>
        )}
        {scene && T_WB && (
          <>
            <Workstation
              meshUrl={assetUrl(assetBase, scene.workstation.mesh)}
              color={palette.table}
              highlight={obstacle === 'table' ? contactColor : null}
              onLoaded={onTable}
              onError={onError}
            />
            <Robot
              urdfUrl={urdfUrl(assetBase)}
              packageBase={packageBase(assetBase)}
              T_WB={T_WB}
              q={q}
              tint={tint}
              onRobot={onRobot}
              onError={onError}
            >
              <Tool
                tool={scene.tool}
                meshUrl={assetUrl(assetBase, scene.tool.mesh)}
                color={palette.accent}
                highlight={toolHit ? contactColor : null}
                onLoaded={onTool}
                onError={onError}
              />
            </Robot>
            {loaded && (
              <Part
                part={loaded.part}
                stlUrl={loaded.stlUrl}
                layerHeightMm={scene.params.layer_height_mm}
                layer={sample ? sample.layer : null}
                color={palette.part}
                ghostColor={palette.ghost}
                highlight={obstacle === 'printed' ? contactColor : null}
                onError={onError}
              />
            )}
            {loaded?.toolpath && showToolpath && (
              <ToolpathLines
                toolpath={loaded.toolpath}
                layer={sample ? sample.layer : null}
                doneColor={palette.toolpathDone}
                todoColor={palette.toolpathTodo}
              />
            )}
          </>
        )}
        <ContactOverlay sample={sample as SceneSample | null} color={contactColor} />
        <OrbitControls makeDefault target={START_TARGET.toArray()} maxPolarAngle={Math.PI * 0.55} />
        <CameraRig onFocus={onFocus} />
      </Canvas>
      {error && (
        <div role="alert" style={{ position: 'absolute', left: 12, bottom: 12, right: 12, color: palette.danger }}>
          Die 3D-Ansicht konnte nicht vollstaendig geladen werden: {error}
        </div>
      )}
    </div>
  );
}

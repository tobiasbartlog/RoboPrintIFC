import { useFrame, useThree } from '@react-three/fiber';
import { useEffect, useRef } from 'react';

/**
 * Rendert die Szene selbst (useFrame mit Prioritaet 1 ersetzt das automatische Rendern) und
 * haelt hoechstens einen Frame bei der GPU in Arbeit: Ist der letzte Frame laut WebGL2-Fence noch
 * nicht fertig, wird dieser Frame ausgelassen und im naechsten Animationsframe erneut geprueft.
 * Gezeichnet wird dann immer der neueste Stand der Uhr; Zwischenstaende entfallen.
 *
 * Ohne diese Drosselung stapeln schnelle Uhrspruenge (Scrubben, Tests mit vielen `seek`) auf
 * langsamer GPU (Software-WebGL: ueber 1 s je Frame) Dutzende Frames auf, die Navigation und
 * Screenshots danach abarbeiten muessen. Ohne WebGL2 wird ungedrosselt gerendert.
 */
export function PacedRender() {
  const gl = useThree((s) => s.gl);
  const fence = useRef<WebGLSync | null>(null);

  useFrame((state) => {
    const ctx = state.gl.getContext();
    const gl2 = typeof WebGL2RenderingContext !== 'undefined' && ctx instanceof WebGL2RenderingContext ? ctx : null;
    if (gl2 && fence.current) {
      if (gl2.getSyncParameter(fence.current, gl2.SYNC_STATUS) === gl2.UNSIGNALED) {
        state.invalidate();
        return;
      }
      gl2.deleteSync(fence.current);
      fence.current = null;
    }
    state.gl.render(state.scene, state.camera);
    if (gl2) {
      fence.current = gl2.fenceSync(gl2.SYNC_GPU_COMMANDS_COMPLETE, 0);
      gl2.flush();
    }
  }, 1);

  useEffect(
    () => () => {
      const ctx = gl.getContext();
      if (fence.current && typeof WebGL2RenderingContext !== 'undefined' && ctx instanceof WebGL2RenderingContext) {
        ctx.deleteSync(fence.current);
      }
      fence.current = null;
    },
    [gl],
  );
  return null;
}

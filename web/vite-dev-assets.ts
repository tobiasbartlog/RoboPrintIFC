import { createReadStream, existsSync, statSync } from 'node:fs';
import { extname, resolve, sep } from 'node:path';
import type { Plugin } from 'vite';

const ROOT = resolve(__dirname, '..');
const ALLOWED = ['third_party', 'tools', 'workstations'];
const TYPES: Record<string, string> = {
  '.urdf': 'application/xml',
  '.dae': 'model/vnd.collada+xml',
  '.stl': 'application/octet-stream',
  '.json': 'application/json',
};

/**
 * Nur fuer die Entwicklung ohne API: liefert `third_party/`, `tools/` und `workstations/` der
 * Repo-Wurzel unter `/dev-assets/<pfad>` aus (`/dev-assets/robot.urdf` ist die Roboter-URDF).
 * Die echte API (`/api/assets`) bleibt davon unberuehrt.
 */
export function devAssets(): Plugin {
  const prefix = '/dev-assets/';
  return {
    name: 'dev-assets',
    apply: 'serve',
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const url = (req.url ?? '').split('?')[0] ?? '';
        if (!url.startsWith(prefix)) return next();
        let rel = decodeURIComponent(url.slice(prefix.length));
        if (rel === 'robot.urdf') rel = 'third_party/doosan_m1013/urdf/m1013.white.urdf';
        const file = resolve(ROOT, rel);
        const allowed = ALLOWED.some((d) => file.startsWith(resolve(ROOT, d) + sep));
        if (!allowed || !existsSync(file) || !statSync(file).isFile()) {
          res.statusCode = 404;
          res.end('not found');
          return;
        }
        res.setHeader('Content-Type', TYPES[extname(file)] ?? 'application/octet-stream');
        createReadStream(file).pipe(res);
      });
    },
  };
}

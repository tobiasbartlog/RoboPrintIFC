// Erzeugt web/src/contracts/*.ts aus den JSON-Schemas in web/src/contracts/schemas/.
// Die Schemas schreibt `roboprint export-contracts web/src/contracts/schemas`.
// Fehlt der Schemaordner, tut das Skript nichts.
import { existsSync, mkdirSync, readdirSync, writeFileSync } from 'node:fs';
import { basename, dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { compileFromFile } from 'json-schema-to-typescript';

const root = join(dirname(fileURLToPath(import.meta.url)), '..', 'src', 'contracts');
const schemaDir = join(root, 'schemas');

if (!existsSync(schemaDir)) {
  console.log('gen:contracts: kein Schemaordner, nichts zu tun');
  process.exit(0);
}

const files = readdirSync(schemaDir).filter((f) => f.endsWith('.json'));
mkdirSync(root, { recursive: true });
for (const file of files) {
  const ts = await compileFromFile(join(schemaDir, file), {
    bannerComment: '/* Automatisch erzeugt (npm run gen:contracts), nicht von Hand aendern. */',
    additionalProperties: false,
  });
  writeFileSync(join(root, basename(file, '.json') + '.ts'), ts);
  console.log(`gen:contracts: ${file}`);
}

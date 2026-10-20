// Erzeugt web/src/contracts/<Name>.ts aus web/src/contracts/schemas/<Name>.schema.json.
// Die Schemas schreibt `roboprint export-contracts web/src/contracts/schemas`.
// Fehlt der Schemaordner, tut das Skript nichts. index.ts ist statisch.
import { existsSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { compile } from 'json-schema-to-typescript';

const root = join(dirname(fileURLToPath(import.meta.url)), '..', 'src', 'contracts');
const dir = join(root, 'schemas');

if (!existsSync(dir)) {
  console.log('gen:contracts: kein Schemaordner, nichts zu tun');
  process.exit(0);
}

for (const f of readdirSync(dir).filter((f) => f.endsWith('.schema.json')).sort()) {
  const name = f.replace('.schema.json', '');
  const schema = JSON.parse(readFileSync(join(dir, f), 'utf8'));
  const ts = await compile(schema, name, {
    bannerComment:
      '/* eslint-disable */\n/**\n * GENERIERT aus schemas/' + f + ' (npm run gen:contracts). Nicht von Hand ändern.\n */',
    additionalProperties: false,
    cwd: dir,
  });
  writeFileSync(join(root, name + '.ts'), ts);
  console.log(`gen:contracts: ${f}`);
}

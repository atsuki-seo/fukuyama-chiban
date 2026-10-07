// G3-6: sw.js VERSION must equal APP.version in index.html.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');

export function versions(root = ROOT) {
  const html = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
  const sw = fs.readFileSync(path.join(root, 'sw.js'), 'utf8');
  const app = html.match(/const APP = \{\s*version: '([^']+)'/);
  const worker = sw.match(/^const VERSION = '([^']+)';$/m);
  return { app: app && app[1], sw: worker && worker[1] };
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const v = versions();
  if (!v.app || !v.sw || v.app !== v.sw) {
    console.error(`Version mismatch: index.html APP.version=${v.app}, sw.js VERSION=${v.sw}`);
    process.exit(1);
  }
  console.log(`OK: ${v.app}`);
}

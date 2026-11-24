/**
 * Baut die Svelte-UI (../webmail/web) und legt das Ergebnis nach ./dist,
 * von wo der Worker sie als statische Assets ausliefert.
 *
 *   node build.mjs        (oder: pnpm build / npm run build)
 */
import { execFileSync } from 'node:child_process';
import { cp, mkdir, rm } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const webDir = path.resolve(here, '..', 'webmail', 'web');
const distDir = path.resolve(here, 'dist');

function run(command, args, cwd) {
  console.log(`\n$ ${command} ${args.join(' ')}   (${cwd})`);
  execFileSync(command, args, { cwd, stdio: 'inherit', shell: process.platform === 'win32' });
}

run('corepack', ['pnpm', 'install', '--frozen-lockfile'], webDir);
run('corepack', ['pnpm', 'build'], webDir);

await rm(distDir, { recursive: true, force: true });
await mkdir(distDir, { recursive: true });
await cp(path.join(webDir, 'build'), distDir, { recursive: true });

console.log(`\nUI gebaut -> ${distDir}`);
console.log('Weiter mit:  npx wrangler deploy');

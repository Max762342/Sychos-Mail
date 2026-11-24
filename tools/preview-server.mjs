/**
 * Lokale Vorschau ohne Cloudflare: spielt den Worker (src/index.js) mit den
 * gebauten Assets aus ./dist und proxied /api/* an einen echten Mailserver.
 *
 *   node tools/preview-server.mjs            (Port 3100, API -> $API_ORIGIN)
 *   API_ORIGIN=http://127.0.0.1:18080 PORT=3100 node tools/preview-server.mjs
 *
 * Damit laesst sich die komplette Kette testen, die auch auf Cloudflare laeuft:
 * statische UI + /api-Proxy inklusive Cookies.
 */
import { createServer } from 'node:http';
import { readFile, stat } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import worker from '../worker/src/index.js';

const here = path.dirname(fileURLToPath(import.meta.url));
const distDir = path.resolve(here, '..', 'worker', 'dist');
const port = Number(process.env.PORT || 3100);
const apiOrigin = process.env.API_ORIGIN || 'http://127.0.0.1:18080';

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.webmanifest': 'application/manifest+json',
  '.txt': 'text/plain; charset=utf-8',
  '.ico': 'image/x-icon',
  '.woff2': 'font/woff2',
};

/** Minimaler Ersatz fuer die Cloudflare-Bindung env.ASSETS. */
const env = {
  ASSETS: {
    async fetch(request) {
      const url = new URL(request.url);
      const rel = decodeURIComponent(url.pathname);
      const file = path.join(distDir, rel === '/' ? 'index.html' : rel);
      if (!file.startsWith(distDir)) return new Response('forbidden', { status: 403 });
      try {
        const info = await stat(file);
        if (info.isDirectory()) throw new Error('dir');
        const body = await readFile(file);
        return new Response(body, {
          headers: {
            'content-type': MIME[path.extname(file)] || 'application/octet-stream',
          },
        });
      } catch {
        return new Response('nicht gefunden', { status: 404 });
      }
    },
  },
  API_ORIGIN: apiOrigin,
  APP_NAME: 'Sychos Mail (Vorschau)',
};

function toRequest(req, body) {
  const url = new URL(req.url, `http://127.0.0.1:${port}`);
  const headers = new Headers();
  for (const [name, value] of Object.entries(req.headers)) {
    if (name.toLowerCase() === 'host') continue;
    if (Array.isArray(value)) headers.set(name, value.join(', '));
    else if (value) headers.set(name, value);
  }
  const init = { method: req.method, headers };
  if (!['GET', 'HEAD'].includes(req.method) && body.length) init.body = body;
  return new Request(url, init);
}

createServer(async (req, res) => {
  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  const body = Buffer.concat(chunks);

  let response;
  try {
    response = await worker.fetch(toRequest(req, body), env);
  } catch (error) {
    response = new Response(`Vorschau-Fehler: ${error}`, { status: 500 });
  }

  res.statusCode = response.status;
  for (const [name, value] of response.headers) {
    if (name === 'set-cookie') continue;
    res.setHeader(name, value);
  }
  const cookies = response.headers.getSetCookie?.() ?? [];
  if (cookies.length) res.setHeader('set-cookie', cookies);
  res.end(Buffer.from(await response.arrayBuffer()));
}).listen(port, () => {
  console.log(`Vorschau: http://127.0.0.1:${port}   API -> ${env.API_ORIGIN}`);
});

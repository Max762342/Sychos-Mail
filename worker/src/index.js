/**
 * Sychos Mail — Cloudflare Worker
 *
 *   sychos.de, www.sychos.de   -> diese Datei
 *     /            statische Svelte-UI aus ./dist (Workers Assets)
 *     /api/*       Reverse-Proxy zum Mailserver (Cloudflare Tunnel,
 *                  Default-Ziel: https://origin.sychos.de)
 *     /healthz     kleiner Statuscheck
 *
 * Warum so: die Oberfläche liegt damit an der Cloudflare-Edge (schnell, auch
 * wenn der Heimserver schläft) — nur die API-Aufrufe gehen zum Server.
 * Cookies bleiben same-origin (sychos.de), weil die API unter demselben Host
 * ausgeliefert wird.
 */

const HOP_BY_HOP = new Set([
  'connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization',
  'te', 'trailer', 'transfer-encoding', 'upgrade', 'host',
]);

const SECURITY_HEADERS = {
  'x-content-type-options': 'nosniff',
  'referrer-policy': 'strict-origin-when-cross-origin',
  'x-frame-options': 'DENY',
  'permissions-policy': 'geolocation=(), microphone=(), camera=(), payment=()',
  'strict-transport-security': 'max-age=31536000; includeSubDomains',
  'x-robots-tag': 'noindex, nofollow',
};

function withSecurityHeaders(headers) {
  for (const [name, value] of Object.entries(SECURITY_HEADERS)) {
    headers.set(name, value);
  }
  return headers;
}

function json(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: withSecurityHeaders(new Headers({
      'content-type': 'application/json; charset=utf-8',
      'cache-control': 'no-store',
    })),
  });
}

function apiOrigin(env) {
  return new URL(env.API_ORIGIN || 'https://origin.sychos.de');
}

function copyResponseHeaders(upstream) {
  const headers = new Headers();
  for (const [name, value] of upstream.headers) {
    if (!HOP_BY_HOP.has(name.toLowerCase())) headers.set(name, value);
  }
  // Alle Set-Cookie-Werte erhalten (Mehrfach-Header).
  const cookies = typeof upstream.headers.getSetCookie === 'function'
    ? upstream.headers.getSetCookie()
    : (upstream.headers.get('set-cookie') ? [upstream.headers.get('set-cookie')] : []);
  if (cookies.length) {
    headers.delete('set-cookie');
    for (const cookie of cookies) headers.append('set-cookie', cookie);
  }
  headers.set('cache-control', 'no-store');
  headers.set('x-proxied-by', 'sychos-worker');
  return headers;
}

/** /api/* -> Mailserver (Tunnel). Cookies, CSRF-Header und Streams (SSE) laufen mit. */
async function proxyApi(request, env, url) {
  const origin = apiOrigin(env);
  const target = new URL(url.pathname + url.search, origin);

  const headers = new Headers();
  for (const [name, value] of request.headers) {
    const key = name.toLowerCase();
    if (HOP_BY_HOP.has(key) || key === 'origin' || key === 'referer') continue;
    headers.set(key, value);
  }
  // Herkunft auf das Tunnel-Ziel umschreiben, damit der Server nie denkt,
  // der Aufruf käme von einer fremden Seite.
  headers.set('origin', origin.origin);
  const referer = request.headers.get('referer');
  if (referer) {
    const ref = new URL(referer);
    headers.set('referer', origin.origin + ref.pathname + ref.search);
  }
  headers.set('x-forwarded-proto', 'https');
  headers.set('x-forwarded-host', url.host);
  const clientIp = request.headers.get('cf-connecting-ip');
  if (clientIp) headers.set('x-forwarded-for', clientIp);

  const init = { method: request.method, headers, redirect: 'manual' };
  if (request.method !== 'GET' && request.method !== 'HEAD') init.body = request.body;

  let upstream;
  try {
    upstream = await fetch(target, init);
  } catch (error) {
    return json({
      error: 'mailserver_unreachable',
      message: 'Der Mailserver ist gerade nicht erreichbar.',
      detail: String(error),
    }, 502);
  }
  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: copyResponseHeaders(upstream),
  });
}

async function serveAssets(request, env) {
  let assetResponse = await env.ASSETS.fetch(request);

  // SPA-Fallback: unbekannte Pfade (z. B. /mail?f=INBOX) bekommen index.html,
  // auch wenn die Assets-Auslieferung selbst 404 meldet.
  const acceptsHtml = (request.headers.get('accept') || '').includes('text/html');
  if (assetResponse.status === 404 && acceptsHtml && request.method === 'GET') {
    const indexUrl = new URL('/index.html', request.url);
    assetResponse = await env.ASSETS.fetch(new Request(indexUrl, request));
  }

  const headers = withSecurityHeaders(new Headers(assetResponse.headers));
  if ((headers.get('content-type') || '').includes('text/html')) {
    headers.set('cache-control', 'no-cache');
  }
  return new Response(assetResponse.body, {
    status: assetResponse.status,
    statusText: assetResponse.statusText,
    headers,
  });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // www -> ohne www
    if (url.hostname.startsWith('www.')) {
      const target = new URL(url.toString());
      target.hostname = url.hostname.slice(4);
      return Response.redirect(target.toString(), 308);
    }

    if (url.pathname === '/healthz') {
      return json({
        ok: true,
        app: env.APP_NAME || 'Sychos Mail',
        api: apiOrigin(env).origin,
        time: new Date().toISOString(),
      });
    }

    if (url.pathname === '/api' || url.pathname.startsWith('/api/')) {
      return proxyApi(request, env, url);
    }

    return serveAssets(request, env);
  },
};

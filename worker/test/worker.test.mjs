/**
 * Tests für den Sychos-Mail-Worker (ohne Cloudflare, nur Node).
 *   cd worker && node --test test/
 */
import assert from 'node:assert/strict';
import test from 'node:test';

import worker from '../src/index.js';

const INDEX_HTML = '<!doctype html><html><head><title>Sychos Mail</title></head></html>';

function makeEnv(overrides = {}) {
  return {
    ASSETS: {
      fetch: async () => new Response(INDEX_HTML, {
        status: 200,
        headers: { 'content-type': 'text/html; charset=utf-8' },
      }),
    },
    API_ORIGIN: 'https://origin.sychos.de',
    APP_NAME: 'Sychos Mail',
    ...overrides,
  };
}

/** Ersetzt globales fetch und zeichnet die Aufrufe auf. */
function mockFetch(handler) {
  const calls = [];
  const original = globalThis.fetch;
  globalThis.fetch = async (url, init = {}) => {
    calls.push({ url: String(url), init });
    return handler(String(url), init);
  };
  return {
    calls,
    restore() {
      globalThis.fetch = original;
    },
  };
}

const upstreamOk = () => new Response('{"email":"admin@sychos.de","csrf":"tok"}', {
  status: 200,
  headers: {
    'content-type': 'application/json',
    'set-cookie': 'wm_session=abc123; Path=/; Secure; HttpOnly; SameSite=Strict',
  },
});

test('liefert die UI mit Sicherheits-Headern', async () => {
  const res = await worker.fetch(new Request('https://sychos.de/'), makeEnv());
  const html = await res.text();
  assert.equal(res.status, 200);
  assert.match(html, /Sychos Mail/);
  assert.equal(res.headers.get('x-content-type-options'), 'nosniff');
  assert.equal(res.headers.get('x-frame-options'), 'DENY');
  assert.match(res.headers.get('strict-transport-security') ?? '', /max-age/);
  assert.equal(res.headers.get('cache-control'), 'no-cache');
});

test('unbekannte Pfade gehen an die SPA-Auslieferung', async () => {
  const seen = [];
  const env = makeEnv({
    ASSETS: {
      fetch: async (request) => {
        seen.push(new URL(request.url).pathname);
        return new Response(INDEX_HTML, { headers: { 'content-type': 'text/html' } });
      },
    },
  });
  const res = await worker.fetch(new Request('https://sychos.de/mail?f=INBOX'), env);
  assert.equal(res.status, 200);
  assert.deepEqual(seen, ['/mail']);
});

test('404 der Assets wird auf index.html umgebogen (SPA-Fallback)', async () => {
  const requested = [];
  const env = makeEnv({
    ASSETS: {
      fetch: async (request) => {
        const path = new URL(request.url).pathname;
        requested.push(path);
        if (path === '/index.html') {
          return new Response(INDEX_HTML, { headers: { 'content-type': 'text/html' } });
        }
        return new Response('nicht gefunden', { status: 404 });
      },
    },
  });
  const res = await worker.fetch(
    new Request('https://sychos.de/tief/verschachtelt', { headers: { accept: 'text/html' } }),
    env,
  );
  assert.equal(res.status, 200);
  assert.deepEqual(requested, ['/tief/verschachtelt', '/index.html']);
  assert.equal(res.headers.get('cache-control'), 'no-cache');
});

test('proxied /api/* zum Mailserver und reicht Cookies mit', async () => {
  const mock = mockFetch(upstreamOk);
  try {
    const res = await worker.fetch(
      new Request('https://sychos.de/api/config', {
        headers: { cookie: 'wm_session=abc123', 'cf-connecting-ip': '203.0.113.7' },
      }),
      makeEnv(),
    );
    const call = mock.calls[0];
    assert.equal(call.url, 'https://origin.sychos.de/api/config');
    assert.equal(call.init.headers.get('cookie'), 'wm_session=abc123');
    assert.equal(call.init.headers.get('x-forwarded-host'), 'sychos.de');
    assert.equal(call.init.headers.get('x-forwarded-for'), '203.0.113.7');
    assert.equal(call.init.headers.get('origin'), 'https://origin.sychos.de');
    assert.equal(res.status, 200);
    assert.equal(res.headers.get('x-proxied-by'), 'sychos-worker');
    assert.deepEqual(res.headers.getSetCookie(), [
      'wm_session=abc123; Path=/; Secure; HttpOnly; SameSite=Strict',
    ]);
    assert.equal(res.headers.get('cache-control'), 'no-store');
  } finally {
    mock.restore();
  }
});

test('POST auf /api/login behält Methode, Body und CSRF-Header', async () => {
  const mock = mockFetch(upstreamOk);
  try {
    await worker.fetch(
      new Request('https://sychos.de/api/login', {
        method: 'POST',
        headers: { 'content-type': 'application/json', 'x-csrf-token': 'tok' },
        body: JSON.stringify({ email: 'admin@sychos.de', password: 'geheim' }),
      }),
      makeEnv(),
    );
    const call = mock.calls[0];
    assert.equal(call.init.method, 'POST');
    assert.equal(call.init.headers.get('x-csrf-token'), 'tok');
    assert.equal(call.init.headers.get('content-type'), 'application/json');
    assert.ok(call.init.body, 'Body wird weitergegeben');
    assert.equal(call.init.duplex, 'half');
  } finally {
    mock.restore();
  }
});

test('Stream-Antworten (SSE) bleiben unangetastet', async () => {
  const mock = mockFetch(() => new Response('data: {"type":"ping"}\n\n', {
    headers: { 'content-type': 'text/event-stream' },
  }));
  try {
    const res = await worker.fetch(new Request('https://sychos.de/api/events'), makeEnv());
    assert.equal(res.headers.get('content-type'), 'text/event-stream');
    assert.equal(await res.text(), 'data: {"type":"ping"}\n\n');
  } finally {
    mock.restore();
  }
});

test('Mailserver nicht erreichbar -> 502 mit JSON', async () => {
  const mock = mockFetch(() => {
    throw new Error('connect timeout');
  });
  try {
    const res = await worker.fetch(new Request('https://sychos.de/api/config'), makeEnv());
    assert.equal(res.status, 502);
    const body = await res.json();
    assert.equal(body.error, 'mailserver_unreachable');
  } finally {
    mock.restore();
  }
});

test('www wird auf die Hauptdomain umgeleitet', async () => {
  const res = await worker.fetch(new Request('https://www.sychos.de/mail'), makeEnv());
  assert.equal(res.status, 308);
  assert.equal(res.headers.get('location'), 'https://sychos.de/mail');
});

test('/healthz meldet Status und API-Ziel', async () => {
  const res = await worker.fetch(new Request('https://sychos.de/healthz'), makeEnv());
  const body = await res.json();
  assert.equal(res.status, 200);
  assert.equal(body.ok, true);
  assert.equal(body.app, 'Sychos Mail');
  assert.equal(body.api, 'https://origin.sychos.de');
});

test('API_ORIGIN lässt sich überschreiben', async () => {
  const mock = mockFetch(upstreamOk);
  try {
    await worker.fetch(new Request('https://sychos.de/api/config'), makeEnv({
      API_ORIGIN: 'https://mail.sychos.de:8443',
    }));
    assert.equal(mock.calls[0].url, 'https://mail.sychos.de:8443/api/config');
  } finally {
    mock.restore();
  }
});

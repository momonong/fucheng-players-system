import { test } from 'node:test';
import assert from 'node:assert/strict';
import worker from '../deploy/workers-vpc/worker.mjs';

const origin = 'https://fucheng.momonong.workers.dev';

test('preserves POST path, body and Origin while replacing forwarding authority', async () => {
  const request = new Request(`${origin}/api/login?next=%2Fadmin`, {
    method: 'POST', body: 'synthetic-body', headers: {
      Origin: 'https://wrong.example', 'Content-Type': 'text/plain',
      'CF-Connecting-IP': '2001:db8::10',
      'X-Forwarded-For': '198.51.100.3', 'X-Forwarded-Proto': 'http',
      'X-Forwarded-Host': 'wrong.example', Forwarded: 'for=wrong',
      'True-Client-IP': '198.51.100.4', 'X-CSRF-Token': 'synthetic-csrf',
      Cookie: 'session=synthetic-session',
    },
  });
  const response = await worker.fetch(request, { fucheng: {
    async fetch(forwarded) {
      return Response.json({ url: forwarded.url, method: forwarded.method,
        body: await forwarded.text(), headers: Object.fromEntries(forwarded.headers),
        redirect: forwarded.redirect });
    },
  } });
  const result = await response.json();
  assert.equal(result.url, 'http://fucheng.momonong.workers.dev/api/login?next=%2Fadmin');
  assert.equal(result.method, 'POST');
  assert.equal(result.body, 'synthetic-body');
  assert.equal(result.headers.origin, 'https://wrong.example');
  assert.equal(result.headers['x-csrf-token'], 'synthetic-csrf');
  assert.equal(result.headers.cookie, 'session=synthetic-session');
  assert.equal(result.headers.host, 'fucheng.momonong.workers.dev');
  assert.equal(result.headers['cf-connecting-ip'], '2001:db8::10');
  assert.equal(result.headers['x-forwarded-proto'], 'https');
  for (const name of ['x-forwarded-for', 'x-forwarded-host', 'forwarded', 'true-client-ip']) {
    assert.equal(result.headers[name], undefined);
  }
  assert.equal(result.redirect, 'manual');
  assert.equal(response.headers.get('Cache-Control'), 'no-store');
});

test('keeps cookies, redirect status, Location and streamed response intact', async () => {
  const response = await worker.fetch(new Request(`${origin}/admin`, {
    headers: { 'CF-Connecting-IP': '192.0.2.10' },
  }), { fucheng: { async fetch() {
    return new Response('redirect body', { status: 303, headers: [
      ['Location', `${origin}/admin/login`],
      ['Set-Cookie', 'first=one; Path=/; Secure; HttpOnly; SameSite=Lax'],
      ['Set-Cookie', 'second=two; Path=/; Secure; HttpOnly; SameSite=Lax'],
      ['Cache-Control', 'public, max-age=86400'],
    ] });
  } } });
  assert.equal(response.status, 303);
  assert.equal(response.headers.get('Location'), `${origin}/admin/login`);
  assert.deepEqual(response.headers.getSetCookie(), [
    'first=one; Path=/; Secure; HttpOnly; SameSite=Lax',
    'second=two; Path=/; Secure; HttpOnly; SameSite=Lax',
  ]);
  assert.equal(await response.text(), 'redirect body');
  assert.equal(response.headers.get('Cache-Control'), 'no-store');
});

test('refuses a different public authority before forwarding credentials', async () => {
  let called = false;
  const response = await worker.fetch(new Request('https://wrong.example/api/login', {
    headers: { 'CF-Connecting-IP': '192.0.2.10' },
  }), { fucheng: { async fetch() { called = true; throw Error('unreachable'); } } });
  assert.equal(called, false);
  assert.equal(response.status, 400);
  assert.equal(response.headers.get('Cache-Control'), 'no-store');
});

for (const headers of [{}, { 'CF-Connecting-IP': 'invalid-header-value' }]) {
  test(`fails closed without a usable edge client address: ${JSON.stringify(headers)}`, async () => {
    let called = false;
    const response = await worker.fetch(new Request(`${origin}/`, { headers }), {
      fucheng: { async fetch() { called = true; return new Response('unreachable'); } },
    });
    assert.equal(called, false);
    assert.equal(response.status, 503);
  });
}

test('unbound and disconnected Service return a noncached maintenance response', async () => {
  for (const env of [{}, { fucheng: { async fetch() { throw Error('PRIVATE_ERROR_SENTINEL'); } } }]) {
    const response = await worker.fetch(new Request(`${origin}/`, {
      headers: { 'CF-Connecting-IP': '192.0.2.10' },
    }), env);
    assert.equal(response.status, 503);
    assert.equal(response.headers.get('Cache-Control'), 'no-store');
    assert.doesNotMatch(await response.text(), /PRIVATE_ERROR_SENTINEL/);
  }
});

test('caches only successful hashed build assets explicitly allowed by origin', async () => {
  for (const path of ['/assets/index-ABcd1234.js', '/assets/screen-ABcd1234.png', '/fucheng/assets/index-ABcd1234.css']) {
    const type = path.endsWith('.png') ? 'image/png' : path.endsWith('.css') ? 'text/css' : 'text/javascript';
    const response = await worker.fetch(new Request(origin + path, { headers: { 'CF-Connecting-IP': '192.0.2.10' } }), {
      fucheng: { async fetch() { return new Response('synthetic', { headers: { 'Cache-Control': 'public, max-age=31536000, immutable', 'Content-Type': type } }); } },
    });
    assert.equal(response.headers.get('Cache-Control'), 'public, max-age=31536000, immutable');
  }
});

test('API, HTML, media, cookies, mismatched MIME and errors never gain static caching', async () => {
  for (const [path, status, extra] of [
    ['/api/public/members', 200, {}], ['/admin', 200, {}], ['/help/home.png', 200, {}],
    ['/assets/plain.js', 200, {}], ['/api/assets/index-ABcd1234.js', 200, {}],
    ['/assets/index-ABcd1234.js', 404, {}], ['/assets/index-ABcd1234.js', 200, { 'Set-Cookie': 'synthetic=one' }],
    ['/assets/index-ABcd1234.js', 200, { 'Content-Type': 'text/html' }],
  ]) {
    const response = await worker.fetch(new Request(origin + path, { headers: { 'CF-Connecting-IP': '192.0.2.10' } }), {
      fucheng: { async fetch() { return new Response('synthetic', { status, headers: { 'Cache-Control': 'public, max-age=31536000, immutable', 'Content-Type': 'text/javascript', ...extra } }); } },
    });
    assert.equal(response.headers.get('Cache-Control'), 'no-store', path);
  }
});

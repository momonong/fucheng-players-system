import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import ts from 'typescript'

async function library(fetcher, run) {
  const source = await readFile(new URL('./src/publicReads.ts', import.meta.url), 'utf8')
  const originalFetch = globalThis.fetch, originalWindow = globalThis.window
  const timers = new Map(); let id = 0
  globalThis.window = { setTimeout(fn, delay) { assert.equal(delay, 20000); timers.set(++id, fn); return id }, clearTimeout(timer) { timers.delete(timer) } }
  globalThis.fetch = fetcher
  try {
    const code = ts.transpileModule(source.replace("import { appUrl } from './paths'", "const appUrl = path => '/fucheng' + path"), { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext } }).outputText
    const module = await import('data:text/javascript;base64,' + Buffer.from(code).toString('base64') + '#' + crypto.randomUUID())
    await run(module.publicGet, timers)
  } finally { globalThis.fetch = originalFetch; globalThis.window = originalWindow }
}
const deferred = () => { let resolve, reject; const promise = new Promise((a, b) => { resolve = a; reject = b }); return { promise, resolve, reject } }

test('same pending public GET is shared, completed data is never cached', async () => {
  let calls = 0; const first = deferred()
  await library((path, options) => { calls++; assert.equal(path, '/fucheng/api/public/members'); assert.equal(options.credentials, 'same-origin'); assert.equal(options.cache, 'no-store'); return calls === 1 ? first.promise : Promise.resolve(Response.json(['fresh'])) }, async (get, timers) => {
    const a = get('/api/public/members'), b = get('/api/public/members')
    assert.equal(a, b); assert.equal(calls, 1)
    first.resolve(Response.json(['synthetic'])); assert.deepEqual(await a, ['synthetic']); await b
    assert.deepEqual(await get('/api/public/members'), ['fresh']); assert.equal(calls, 2); assert.equal(timers.size, 0)
  })
})
test('fresh read bypasses old pending; old completion cannot delete newer pending', async () => {
  const old = deferred(), fresh = deferred(); let calls = 0
  await library(() => (++calls === 1 ? old.promise : fresh.promise), async get => {
    const a = get('/api/public/competitions/synthetic/registrations')
    const b = get('/api/public/competitions/synthetic/registrations', true)
    old.resolve(Response.json(['old'])); await a
    assert.equal(get('/api/public/competitions/synthetic/registrations'), b)
    assert.equal(calls, 2)
    fresh.resolve(Response.json(['confirmed'])); assert.deepEqual(await b, ['confirmed'])
  })
})
test('failed read clears pending and retains HTTP status for the caller', async () => {
  let calls = 0
  await library(async () => { calls++; return calls === 1 ? Response.json({ detail: 'synthetic conflict' }, { status: 409 }) : Response.json([]) }, async get => {
    await assert.rejects(get('/api/public/registration-rosters'), error => error.status === 409 && error.message === 'synthetic conflict')
    assert.deepEqual(await get('/api/public/registration-rosters'), []); assert.equal(calls, 2)
  })
})
test('timeout covers response body decoding and aborts the read', async () => {
  let signal
  await library(async (_path, options) => {
    signal = options.signal
    return { ok: true, json: () => new Promise((_resolve, reject) => signal.addEventListener('abort', () => reject(new Error('synthetic timeout')))) }
  }, async (get, timers) => {
    const request = get('/api/public/members'); await Promise.resolve()
    for (const callback of timers.values()) callback()
    await assert.rejects(request, /synthetic timeout/); assert.equal(signal.aborted, true); assert.equal(timers.size, 0)
  })
})
test('administrator paths cannot enter public read coalescing', async () => {
  await library(() => { throw new Error('must not fetch') }, async get => { assert.throws(() => get('/api/admin/members'), /public read path/) })
})

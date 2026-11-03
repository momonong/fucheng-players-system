import { appUrl } from './paths'

const pending = new Map<string, Promise<unknown>>()
// Only in-flight public GETs are shared. No response, credential or receipt is
// stored after completion; a post-write read must bypass any older GET.
export function publicGet<T>(path: string, fresh = false): Promise<T> {
  if (!path.startsWith('/api/public/')) throw new Error('Expected a public read path')
  if (!fresh && pending.has(path)) return pending.get(path)! as Promise<T>
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), 20000)
  const promise = (async () => {
    try {
      const response = await fetch(appUrl(path), { credentials: 'same-origin', cache: 'no-store', signal: controller.signal })
      if (!response.ok) {
        const body = await response.json().catch(() => null)
        throw Object.assign(new Error(typeof body?.detail === 'string' ? body.detail : '名單暫時無法讀取，請稍後重試'), { status: response.status })
      }
      return await response.json() as T
    } finally { window.clearTimeout(timer) }
  })()
  pending.set(path, promise)
  const clear = () => { if (pending.get(path) === promise) pending.delete(path) }
  void promise.then(clear, clear)
  return promise
}

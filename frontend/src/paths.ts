// Supplied by FastAPI when serving index.html; Vite development defaults to /.
const basePath = document.querySelector<HTMLMetaElement>('meta[name="fucheng-base-path"]')?.content ?? ''

export function appUrl(path: string): string {
  if (!path.startsWith('/') || path.startsWith('//')) throw new Error('Expected an application path')
  return `${basePath}${path}`
}

export function appPathname(): string {
  const path = window.location.pathname
  return basePath && path.startsWith(`${basePath}/`) ? path.slice(basePath.length) : path
}

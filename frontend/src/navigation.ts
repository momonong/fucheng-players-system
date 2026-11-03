import { useEffect, useSyncExternalStore } from 'react'
import { appPathname, appUrl } from './paths'

const publicPath = (path: string) => ['/', '/members', '/competitions', '/help'].includes(path) || /^\/register\/[^/]+$/.test(path)
const snapshot = () => window.location.pathname + window.location.search
function subscribe(changed: () => void) {
  window.addEventListener('popstate', changed)
  window.addEventListener('fucheng:navigate', changed)
  return () => { window.removeEventListener('popstate', changed); window.removeEventListener('fucheng:navigate', changed) }
}
function localPath(pathname: string) {
  const prefix = appUrl('/').slice(0, -1)
  if (prefix && !pathname.startsWith(prefix + '/')) return null
  return prefix ? pathname.slice(prefix.length) : pathname
}

// Native anchors retain their URLs, keyboard support and open-in-new-tab behavior.
// Only ordinary navigation wholly within the public site stays in this document.
export function usePublicNavigation() {
  const location = useSyncExternalStore(subscribe, snapshot)
  useEffect(() => {
    const click = (event: MouseEvent) => {
      if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
      const anchor = event.target instanceof Element ? event.target.closest('a') : null
      if (!anchor || anchor.hasAttribute('download') || (anchor.target && anchor.target !== '_self') || anchor.relList.contains('external')) return
      const target = new URL(anchor.href, window.location.href)
      const path = localPath(target.pathname)
      if (target.origin !== window.location.origin || !path || !publicPath(path) || !publicPath(appPathname())) return
      if (target.pathname === window.location.pathname && target.search === window.location.search) {
        if (!target.hash) event.preventDefault()
        return
      }
      event.preventDefault()
      history.pushState(null, '', target.pathname + target.search + target.hash)
      window.dispatchEvent(new Event('fucheng:navigate'))
      requestAnimationFrame(() => {
        if (target.hash) document.getElementById(decodeURIComponent(target.hash.slice(1)))?.scrollIntoView()
        else window.scrollTo(0, 0)
      })
    }
    document.addEventListener('click', click)
    return () => document.removeEventListener('click', click)
  }, [])
  return location
}

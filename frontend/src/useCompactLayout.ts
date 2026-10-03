import { useEffect, useState } from 'react'

// Layout follows the available viewport, not a guessed device or operating system.
export function useCompactLayout() {
  const [compact, setCompact] = useState(() => window.matchMedia('(max-width: 900px)').matches)
  useEffect(() => {
    const media = window.matchMedia('(max-width: 900px)')
    const update = () => setCompact(media.matches)
    update()
    media.addEventListener('change', update)
    return () => media.removeEventListener('change', update)
  }, [])
  return compact
}

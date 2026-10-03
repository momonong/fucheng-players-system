import { useLayoutEffect, useRef, type ReactNode } from 'react'
import { useCompactLayout } from './useCompactLayout'

/** One mounted form: modal sheet on small screens, inline panel on desktop. */
export function ResponsivePanel({ label, onClose, children }: { label: string; onClose: () => void; children: ReactNode }) {
  const compact = useCompactLayout()
  const ref = useRef<HTMLDialogElement>(null)
  useLayoutEffect(() => {
    const dialog = ref.current!
    dialog.close()
    if (compact) dialog.showModal()
    else dialog.show()
  }, [compact])
  return <dialog ref={ref} className="responsive-detail no-print" role={compact ? 'dialog' : 'region'} aria-label={label} onCancel={event => { event.preventDefault(); onClose() }}>{children}</dialog>
}

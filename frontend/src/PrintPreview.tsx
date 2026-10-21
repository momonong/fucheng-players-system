import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { createPortal, flushSync } from 'react-dom'

const MM = 96 / 25.4
const PAPER_WIDTH = 297 * MM
const PAPER_HEIGHT = 210 * MM
const CONTENT_WIDTH = 285 * MM

/** A readable print document. The browser paginates vertically; content never shrinks to fit. */
export function PrintPreview({ children, open, onOpen, onClose, label, className = '', fontSize = 14 }: {
  children: ReactNode; open: boolean; onOpen: () => void; onClose: () => void; label: string; className?: string; fontSize?: number
}) {
  const previousOpen = useRef(false)
  const snapshot = useRef(children)
  if (!open || !previousOpen.current) snapshot.current = children
  previousOpen.current = open
  const report = open ? snapshot.current : children
  const content = useRef<HTMLDivElement>(null)
  const viewport = useRef<HTMLDivElement>(null)
  const closeButton = useRef<HTMLButtonElement>(null)
  const [paperScale, setPaperScale] = useState(1)
  const [documentHeight, setDocumentHeight] = useState(PAPER_HEIGHT)
  const [printing, setPrinting] = useState(false)
  const [fullSize, setFullSize] = useState(false)
  useLayoutEffect(() => {
    const node = content.current
    if (!node) return
    const resize = () => setDocumentHeight(Math.max(PAPER_HEIGHT, node.offsetHeight + 12 * MM))
    resize()
    const observer = new ResizeObserver(resize); observer.observe(node)
    void document.fonts.ready.then(resize)
    return () => observer.disconnect()
  }, [report])
  useLayoutEffect(() => {
    if (!open || !viewport.current) return
    const node = viewport.current
    const resize = () => {
      const style = getComputedStyle(node)
      const width = node.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight)
      setPaperScale(fullSize ? 1 : Math.min(1, width / PAPER_WIDTH))
    }
    resize()
    const observer = new ResizeObserver(resize); observer.observe(node)
    return () => observer.disconnect()
  }, [open, fullSize])
  useEffect(() => {
    const before = () => flushSync(() => setPrinting(true))
    const after = () => { setPrinting(false); onClose() }
    const key = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'p') { event.preventDefault(); if (open) void print(); else onOpen() }
      if (open && event.key === 'Tab') {
        const controls = Array.from(document.querySelectorAll<HTMLButtonElement>('.preview-open button')).filter(node => !node.disabled)
        const first = controls[0], last = controls.at(-1)
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
      }
      if (open && event.key === 'Escape') { event.preventDefault(); onClose() }
    }
    window.addEventListener('beforeprint', before); window.addEventListener('afterprint', after); window.addEventListener('keydown', key)
    return () => { window.removeEventListener('beforeprint', before); window.removeEventListener('afterprint', after); window.removeEventListener('keydown', key) }
  }, [onOpen, onClose, open])
  useEffect(() => {
    if (!open) { setFullSize(false); return }
    const previous = document.activeElement as HTMLElement | null
    const overflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const app = document.getElementById('root')
    const wasInert = app?.inert ?? false
    if (app) app.inert = true
    closeButton.current?.focus()
    return () => { document.body.style.overflow = overflow; if (app) app.inert = wasInert; previous?.focus() }
  }, [open])
  async function print() { await document.fonts.ready; window.print() }
  return createPortal(<section className={`print-output ${open ? 'preview-open' : ''} ${open || printing ? className : ''}`} aria-hidden={!open && !printing ? true : undefined} role={open ? 'dialog' : undefined} aria-modal={open ? true : undefined} aria-label={label}>
    {open && <div className="print-preview-toolbar"><div><h2>A4 橫向列印預覽</h2><p>依原字級分頁・內容較多時增加頁數・可上下捲動檢視</p></div><div><button className="secondary" ref={closeButton} onClick={onClose}>返回編輯</button><button className="secondary" aria-pressed={fullSize} onClick={() => setFullSize(!fullSize)}>{fullSize ? '符合寬度' : '放大檢視'}</button><button onClick={() => void print()}>列印／另存 PDF</button></div></div>}
    <div className="print-preview-scroll" ref={viewport}><div className="print-preview-viewport" style={open ? { width: PAPER_WIDTH * paperScale, height: documentHeight * paperScale } : undefined}>
      <div className="print-paper" style={{ transform: open && !printing ? `scale(${paperScale})` : undefined }}>
        <div className="print-document" ref={content} style={{ width: CONTENT_WIDTH, fontSize: `${fontSize}pt` }}>{report}</div>
      </div>
    </div></div>
  </section>, document.body)
}

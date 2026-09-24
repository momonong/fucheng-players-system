import { useEffect, useRef, useState } from 'react'

export function hydrateAnnouncementImages(root: HTMLElement, scope: 'admin' | 'public') {
  const figures = [...root.querySelectorAll<HTMLElement>('figure[data-media-id]')]
  if (root.matches('figure[data-media-id]')) figures.push(root)
  figures.forEach(figure => {
    const id = figure.dataset.mediaId
    if (!id || !/^[0-9a-f-]{36}$/.test(id)) return
    const image = document.createElement('img')
    image.src = `/api/${scope}/announcement-media/${id}`
    image.alt = '公告圖片'
    figure.replaceChildren(image)
  })
}

type Props = {
  initial: string
  disabled: boolean
  canUpload: boolean
  onChange: (html: string) => void
  onUpload: (file: File) => Promise<string>
  onError: (message: string) => void
}

export function AnnouncementRichEditor({ initial, disabled, canUpload, onChange, onUpload, onError }: Props) {
  const editor = useRef<HTMLDivElement>(null)
  const picker = useRef<HTMLInputElement>(null)
  const savedRange = useRef<Range | null>(null)
  const selectedBlock = useRef<HTMLElement | null>(null)
  const [style, setStyle] = useState('p')
  const [active, setActive] = useState<Record<string, boolean>>({})
  const [linkOpen, setLinkOpen] = useState(false)
  const [link, setLink] = useState('')
  const [uploading, setUploading] = useState(false)
  const [blockType, setBlockType] = useState('')

  useEffect(() => {
    if (editor.current) {
      editor.current.innerHTML = initial
      for (const node of [...editor.current.childNodes]) {
        if (node.nodeType === Node.TEXT_NODE && node.textContent?.trim()) {
          const paragraph = document.createElement('p')
          node.replaceWith(paragraph)
          paragraph.append(node)
        }
      }
      hydrateAnnouncementImages(editor.current, 'admin')
    }
  }, [])

  function directBlock(node: Node | null): HTMLElement | null {
    const root = editor.current
    if (!root || !node || !root.contains(node)) return null
    let current = node instanceof HTMLElement ? node : node.parentElement
    while (current && current.parentElement !== root) current = current.parentElement
    return current?.parentElement === root ? current : null
  }
  function remember() {
    const selection = window.getSelection()
    if (!selection?.rangeCount || !editor.current?.contains(selection.anchorNode)) return
    savedRange.current = selection.getRangeAt(0).cloneRange()
    selectedBlock.current = directBlock(selection.anchorNode)
    refresh()
  }
  function refresh() {
    const selection = window.getSelection()
    const node = selection?.anchorNode
    let element = node instanceof HTMLElement ? node : node?.parentElement
    const root = editor.current
    if (!root || !element || !root.contains(element)) return
    const block = directBlock(node ?? null)
    selectedBlock.current = block
    setBlockType(block?.tagName.toLowerCase() ?? '')
    while (element && element !== root && !/^(P|H1|H2|H3|H4|DIV)$/.test(element.tagName)) element = element.parentElement
    setStyle(element && element !== root ? element.tagName.toLowerCase() : 'p')
    setActive(Object.fromEntries(['bold', 'italic', 'underline', 'insertUnorderedList', 'insertOrderedList'].map(name => [name, document.queryCommandState(name)])))
  }
  function restore() {
    editor.current?.focus()
    if (!savedRange.current) return
    const selection = window.getSelection()
    selection?.removeAllRanges()
    try { selection?.addRange(savedRange.current) } catch { /* Selection became stale after an edit. */ }
  }
  function changed() { onChange(editor.current?.innerHTML ?? ''); remember() }
  function command(name: string, value?: string) {
    restore()
    document.execCommand(name, false, value)
    changed()
  }
  function align(value: 'left' | 'center' | 'right') {
    const block = selectedBlock.current
    if (!block) return
    block.dataset.align = value
    changed()
  }
  function move(direction: -1 | 1) {
    const block = selectedBlock.current
    if (!block || !editor.current) return
    const sibling = direction < 0 ? block.previousElementSibling : block.nextElementSibling
    if (!sibling) return
    if (direction < 0) editor.current.insertBefore(block, sibling)
    else editor.current.insertBefore(sibling, block)
    selectedBlock.current = block
    onChange(editor.current.innerHTML)
  }
  function removeImage() {
    const block = selectedBlock.current
    if (block?.tagName !== 'FIGURE') return
    block.remove()
    selectedBlock.current = null
    setBlockType('')
    onChange(editor.current?.innerHTML ?? '')
  }
  function clearImageSelection() {
    editor.current?.querySelectorAll('figure[data-selected]').forEach(figure => figure.removeAttribute('data-selected'))
    selectedBlock.current = null
    setBlockType('')
  }
  function applyLink() {
    let parsed: URL
    try { parsed = new URL(link) } catch { onError('連結須為完整的 http 或 https 網址'); return }
    if (!['http:', 'https:'].includes(parsed.protocol)) { onError('連結須為完整的 http 或 https 網址'); return }
    command('createLink', parsed.toString())
    setLinkOpen(false); setLink('')
  }
  async function selectedFile(file: File | undefined) {
    if (!file || !editor.current) return
    const replacement = selectedBlock.current?.tagName === 'FIGURE' ? selectedBlock.current : null
    setUploading(true)
    try {
      const id = await onUpload(file)
      const figure = document.createElement('figure')
      figure.dataset.mediaId = id
      figure.dataset.align = replacement?.getAttribute('data-align') ?? 'center'
      figure.contentEditable = 'false'
      hydrateAnnouncementImages(figure, 'admin')
      if (replacement) replacement.replaceWith(figure)
      else {
        const block = selectedBlock.current
        if (block?.parentElement === editor.current) block.after(figure)
        else editor.current.append(figure)
      }
      selectedBlock.current = figure
      setBlockType('figure')
      onChange(editor.current.innerHTML)
    } catch (error) { onError((error as Error).message) }
    finally { setUploading(false); if (picker.current) picker.current.value = '' }
  }
  const controlsDisabled = disabled || uploading
  return <div className="rich-editor">
    <p className="mobile-toolbar-hint">公告工具列可左右滑動；點選圖片可調整順序。</p>
    <div className="rich-toolbar" role="toolbar" aria-label="公告格式" onPointerDown={remember}>
      <div className="rich-group"><span className="rich-group-title" aria-hidden="true">樣式</span><div className="rich-group-controls"><select aria-label="文字樣式" value={style} disabled={controlsDisabled} onChange={event => { setStyle(event.target.value); command('formatBlock', event.target.value) }}><option value="p">正文</option><option value="h1">標題 1</option><option value="h2">標題 2</option><option value="h3">標題 3</option></select></div></div>
      <div className="rich-group" aria-label="文字格式"><span className="rich-group-title" aria-hidden="true">文字</span><div className="rich-group-controls">{([['bold', '粗體', 'B'], ['italic', '斜體', 'I'], ['underline', '底線', 'U'], ['removeFormat', '清除格式', '清除']] as const).map(([name, label, text]) => <button key={name} type="button" title={label} aria-label={label} aria-pressed={active[name] || false} disabled={controlsDisabled} onMouseDown={event => event.preventDefault()} onClick={() => command(name)}>{text}</button>)}</div></div>
      <div className="rich-group" aria-label="段落格式"><span className="rich-group-title" aria-hidden="true">段落</span><div className="rich-group-controls">{([['insertUnorderedList', '項目列點', '• 清單'], ['insertOrderedList', '編號列點', '1. 清單']] as const).map(([name, label, text]) => <button key={name} type="button" aria-label={label} aria-pressed={active[name] || false} disabled={controlsDisabled} onMouseDown={event => event.preventDefault()} onClick={() => command(name)}>{text}</button>)}{(['left', 'center', 'right'] as const).map((value, index) => <button key={value} type="button" aria-label={['靠左', '置中', '靠右'][index]} aria-pressed={selectedBlock.current?.dataset.align === value} disabled={controlsDisabled} onClick={() => align(value)}>{['≡', '≣', '☷'][index]}</button>)}</div></div>
      <div className="rich-group" aria-label="插入內容"><span className="rich-group-title" aria-hidden="true">插入</span><div className="rich-group-controls"><button type="button" disabled={controlsDisabled} onClick={() => { remember(); setLinkOpen(value => !value) }}>插入連結</button><button type="button" disabled={controlsDisabled || !canUpload} title={canUpload ? '選取圖片後可替換' : '請先儲存草稿'} onClick={() => { remember(); picker.current?.click() }}>{uploading ? '上傳中…' : '插入圖片'}</button><input ref={picker} className="rich-file-input" type="file" accept="image/png,image/jpeg,image/webp" aria-label="選擇內文圖片" disabled={controlsDisabled || !canUpload} onChange={event => void selectedFile(event.target.files?.[0])} /></div></div>
      <div className="rich-group" aria-label="區塊順序"><span className="rich-group-title" aria-hidden="true">區塊</span><div className="rich-group-controls"><button type="button" disabled={controlsDisabled || !blockType} onClick={() => move(-1)}>上移區塊</button><button type="button" disabled={controlsDisabled || !blockType} onClick={() => move(1)}>下移區塊</button><button type="button" disabled={controlsDisabled || blockType !== 'figure'} onClick={removeImage}>移除圖片</button></div></div>
    </div>
    {linkOpen && <div className="rich-link"><label>連結網址<input type="url" value={link} onChange={event => setLink(event.target.value)} placeholder="https://example.com" /></label><button type="button" disabled={controlsDisabled} onClick={applyLink}>套用連結</button><button type="button" className="secondary" onClick={() => setLinkOpen(false)}>取消</button></div>}
    {!canUpload && <p className="editor-hint">先儲存草稿，即可在段落間插入圖片。</p>}
    <div ref={editor} className="rich-input rich-body" contentEditable={!controlsDisabled} role="textbox" aria-label="公告內容" aria-multiline="true" onInput={changed} onKeyUp={remember} onMouseUp={remember} onTouchEnd={remember} onClick={event => { const figure = (event.target as HTMLElement).closest('figure'); editor.current?.querySelectorAll('figure[data-selected]').forEach(item => item.removeAttribute('data-selected')); if (figure && editor.current?.contains(figure)) { figure.setAttribute('data-selected', 'true'); const range = document.createRange(); range.selectNodeContents(figure); range.collapse(true); const selection = window.getSelection(); selection?.removeAllRanges(); selection?.addRange(range); savedRange.current = range; selectedBlock.current = figure; setBlockType('figure') } else { selectedBlock.current = directBlock(event.target as Node); setBlockType(selectedBlock.current?.tagName.toLowerCase() ?? '') } }} data-placeholder="輸入公告內容" />
    {blockType === 'figure' && <div className="mobile-image-actions" role="group" aria-label="圖片操作"><span>已選圖片</span><button type="button" disabled={controlsDisabled} onClick={() => move(-1)}>上移圖片</button><button type="button" disabled={controlsDisabled} onClick={() => move(1)}>下移圖片</button><button type="button" disabled={controlsDisabled} onClick={removeImage}>移除圖片</button><button type="button" className="secondary" onClick={clearImageSelection}>完成</button></div>}
  </div>
}

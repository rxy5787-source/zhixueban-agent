import { useEffect, useId, useRef } from 'react'
import type { ReactNode } from 'react'
import { Icon } from './Icon'

export function Sheet({ title, children, onClose }: { title: string; children: ReactNode; onClose: () => void }) {
  const ref = useRef<HTMLDivElement>(null)
  const returnTo = useRef<HTMLElement | null>(null)
  const titleId = useId()
  useEffect(() => {
    if (!returnTo.current) returnTo.current = document.activeElement as HTMLElement | null
    const panel = ref.current!
    const focusable = () => [...panel.querySelectorAll<HTMLElement>('button:not([disabled]), input:not([disabled]):not([type="hidden"]), textarea:not([disabled]), select:not([disabled]), [href], [tabindex="0"]')]
    focusable()[0]?.focus()
    function handleKey(event: KeyboardEvent) {
      if (event.key === 'Escape') { event.preventDefault(); onClose() }
      if (event.key !== 'Tab') return
      const items = focusable(), first = items[0], last = items[items.length - 1]
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
    }
    document.addEventListener('keydown', handleKey)
    return () => { document.removeEventListener('keydown', handleKey); returnTo.current?.focus() }
  }, [onClose, title])
  return <div className="sheet-scrim" onClick={event => { if (event.target === event.currentTarget) onClose() }}>
    <div className="sheet" ref={ref} role="dialog" aria-modal="true" aria-labelledby={titleId}>
      <div className="sheet-handle"/>
      <header className="sheet-heading"><h2 id={titleId}>{title}</h2><button className="icon-button" aria-label="关闭弹层" onClick={onClose}><Icon name="close"/></button></header>
      {children}
    </div>
  </div>
}

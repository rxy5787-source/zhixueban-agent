import type { CSSProperties, ReactNode } from 'react'

type IconName = 'today' | 'libraries' | 'reports' | 'profile' | 'chevron' | 'arrow' | 'send' | 'play' | 'close' | 'check' | 'target' | 'clock' | 'info' | 'leaf' | 'spark' | 'plus' | 'file' | 'folder' | 'search' | 'back' | 'settings'
export function Icon({ name, size = 22, className = '', style }: { name: IconName; size?: number; className?: string; style?: CSSProperties }) {
  const paths: Record<IconName, ReactNode> = {
    plus: <path d="M12 5v14M5 12h14"/>,
    file: <><path d="M5 3h9l5 5v13H5Z"/><path d="M14 3v6h5M8 13h8m-8 4h6"/></>,
    folder: <path d="M3 6h7l2 3h9v11H3Zm0 3V5h7l2 2h9v2"/>,
    search: <><circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/></>,
    back: <path d="m11 5-7 7 7 7M4 12h16"/>,
    settings: <><circle cx="12" cy="12" r="3"/><path d="m9 3-1 3-3 1-2 4 2 2 1 4 3 1 3 3 3-3 3-1 1-4 2-2-2-4-3-1-1-3Z"/></>,
    today: <><path d="m3 10 9-7 9 7v10H3Z"/><path d="M9 20v-7h6v7"/></>,
    libraries: <><path d="M3 5h7a3 3 0 0 1 2 1 3 3 0 0 1 2-1h7v15h-7a3 3 0 0 0-2 1 3 3 0 0 0-2-1H3Z"/><path d="M12 6v15M6 9h3m6 0h3M6 13h3m6 0h3"/></>,
    reports: <><path d="M4 3v18h17M8 16v-5m5 5V6m5 10v-7"/></>,
    profile: <><circle cx="12" cy="8" r="4"/><path d="M4 21v-2a8 8 0 0 1 16 0v2"/></>,
    chevron: <path d="m9 5 7 7-7 7"/>,
    arrow: <path d="M4 12h16m-6-6 6 6-6 6"/>,
    send: <path d="M12 20V4m-6 6 6-6 6 6"/>,
    play: <path d="m9 5 10 7-10 7Z" fill="currentColor" strokeWidth="0"/>,
    close: <path d="m6 6 12 12M6 18 18 6"/>,
    check: <path d="m5 12 4 4 10-10"/>,
    target: <><circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3"/><path d="m15 9 6-6m-5 0h5v5"/></>,
    clock: <><circle cx="12" cy="12" r="9"/><path d="M12 7v6l4 2"/></>,
    info: <><circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10v.01"/></>,
    leaf: <><path d="M20 3C8 2 3 8 5 15c5 6 15 0 15-12Z"/><path d="M3 21 15 9"/></>,
    spark: <><path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5Z"/></>,
  }
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" className={className} style={style} aria-hidden="true">{paths[name]}</svg>
}

export function BookGarden() {
  return <svg className="book-garden" viewBox="0 0 160 135" fill="none" aria-hidden="true">
    <ellipse cx="84" cy="117" rx="61" ry="9" fill="var(--color-primary-soft)"/>
    <path d="M44 84c12-9 24-7 38 1 14-8 27-11 40-6v33c-13-4-26-1-40 5-14-7-26-8-38-4Z" fill="var(--color-surface)" stroke="var(--color-primary)" strokeWidth="2.3" strokeLinejoin="round"/>
    <path d="M82 85v32M53 93l18 5m-18 3 18 5m20-11 21-6m-21 15 21-6" stroke="var(--color-primary)" strokeWidth="1.7" strokeLinecap="round"/>
    <path d="M86 78c0-26 7-46 23-62M89 57C69 57 62 47 65 34c17-1 29 7 24 23ZM98 39c17 2 27-7 29-21-16-4-30 4-29 21Z" fill="var(--color-leaf)" stroke="var(--color-primary)" strokeWidth="2" strokeLinejoin="round"/>
    <path d="m38 38 1.5 5 5 1.5-5 1.5-1.5 5-1.5-5-5-1.5 5-1.5Zm91 22 1 4 4 1-4 1-1 4-1-4-4-1 4-1Z" fill="var(--color-primary)"/>
    <circle cx="48" cy="65" r="3" fill="var(--color-leaf)"/><circle cx="119" cy="48" r="2" fill="var(--color-primary)"/>
  </svg>
}

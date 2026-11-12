import { api } from './generation'

export type StudyKind = 'single_choice' | 'mnemonic' | 'cloze' | 'reply'
export type StudyAnchor = {
  point: string; cue?: string; meaning: string; evidence: string; source: string; location: string; ocr: boolean
}
export type StudyOutput = {
  kind: 'mnemonic' | 'reply'; title: string; content: string; anchors: StudyAnchor[]; limited: boolean
  cards?: { title: string; mnemonic: string; anchors: StudyAnchor[] }[]
} | {
  kind: 'cloze'; title: string; items: { id: string; before: string; after: string }[]; limited: boolean; ocr?: boolean
}
export type StudyTurn = {
  id: string; requirement: string; kind: StudyKind; libraryId: string; libraryName: string; sources: string[]
}
const THREAD_KEY = 'zhixue-study-thread-v1'
const REQUEST_KEY = 'zhixue-study-request-v1'
export const CLOZE_FROM_MNEMONIC = '把这段口诀的关键动作挖空考我'

export function studyIntent(text: string, previous?: StudyKind): StudyKind {
  const requested = text.replace(/(?:不要|不出|不做|不用)(?:生成)?\s*(?:选择题|单选题?|填空题?|口诀)/g, '')
  if (/填空|挖空|留空/.test(requested)) return 'cloze'
  const mnemonic = /口诀|顺口溜|记忆法/.test(requested)
  if (mnemonic && /(?:改成|编成|整理成|给我).{0,12}(?:口诀|顺口溜|记忆法)/.test(requested)) return 'mnemonic'
  if (/选择题|单选|出题|练习题|模拟题|试题|考我|[0-9一二两三四五六七八九十]+\s*道.{0,18}题/.test(requested)) return 'single_choice'
  if (mnemonic) return 'mnemonic'
  if (previous && /再短|简短|押韵|改写|换一[个种]|简化/.test(text)) return previous
  return 'reply'
}

export function readStudyThread(): StudyTurn[] {
  try {
    const value = JSON.parse(sessionStorage.getItem(THREAD_KEY) ?? '[]')
    return Array.isArray(value) ? value.filter(item =>
      item && typeof item.id === 'string' && /^[a-f0-9]{32}$/.test(item.id) &&
      typeof item.requirement === 'string' && typeof item.libraryId === 'string' &&
      typeof item.libraryName === 'string' && Array.isArray(item.sources)
    ).slice(-12) : []
  } catch { return [] }
}

export function storeStudyThread(turns: StudyTurn[]) {
  try { sessionStorage.setItem(THREAD_KEY, JSON.stringify(turns)) } catch { /* Keep the thread in memory. */ }
}

let pending: { signature: string; id: string } | undefined
export async function continueStudy(parentId: string, requirement: string, kind: StudyKind, questionCount: number) {
  const fields = { parentId, requirement, kind, questionCount }
  const signature = JSON.stringify(fields)
  try {
    const saved = JSON.parse(sessionStorage.getItem(REQUEST_KEY) ?? 'null')
    if (saved?.signature === signature && typeof saved.id === 'string') pending = saved
  } catch { /* In-memory retries also reuse the request ID. */ }
  if (pending?.signature !== signature) pending = { signature, id: crypto.randomUUID() }
  const requestId = pending.id
  try { sessionStorage.setItem(REQUEST_KEY, JSON.stringify(pending)) } catch { /* Keep in-memory state. */ }
  const result = await api<{ taskId: string; status: string }>('/api/study-turns', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...fields, requestId }),
  })
  pending = undefined
  try { sessionStorage.removeItem(REQUEST_KEY) } catch { /* The server already accepted the turn. */ }
  return result
}

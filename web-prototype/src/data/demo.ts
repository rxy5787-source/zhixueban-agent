/** UI fixtures only: no AI, uploaded file contents or BKT calculations. */
export type Destination = 'home' | 'libraries' | 'profile'
export const DESTINATIONS: { id: Destination; title: string }[] = [
  { id: 'home', title: '首页' }, { id: 'libraries', title: '知识库' }, { id: 'profile', title: '我的' },
]
export type DocumentKind = 'source' | 'questions' | 'knowledge'
export type LibraryDocument = { id: string; title: string; format: 'PDF' | 'DOCX' | 'JPG' | 'QSET' | 'TXT' | 'NOTE'; kind: DocumentKind; description: string; taskId?: string; study?: boolean }
export type Library = {
  id: string; title: string; subtitle: string; mark: string
  color: 'mint' | 'sand' | 'blue' | 'rose'; updated: string
  documents: LibraryDocument[]; points: string[]
  question: { stem: string; options: string[] }
  records: { title: string; time: string; result: string }[]
}
export const LIBRARY_SEEDS: Library[] = ([
  { id: 'sql', title: 'SQL 学习笔记', subtitle: '数据库 · 查询与应用', mark: 'SQL', color: 'mint' },
  { id: 'structure', title: '数据结构', subtitle: '计算机 · 从理解到应用', mark: '{ }', color: 'sand' },
  { id: 'english', title: '英语六级', subtitle: '语言 · 日积月累', mark: 'Aa', color: 'blue' },
  { id: 'reasoning', title: '行测资料分析', subtitle: '公考 · 数字里的逻辑', mark: '%', color: 'rose' },
] as const).map(library => ({
  ...library, updated: '等待学习资料', documents: [], points: [], records: [],
  question: { stem: '', options: [] },
}))

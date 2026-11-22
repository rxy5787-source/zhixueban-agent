import type { Destination } from './data/demo'

export type Route = { destination: Destination; libraryId?: string; taskId?: string; practicing?: boolean; study?: boolean; offlinePractice?: boolean }
export const STUDY_HASH = '#home/study'

export function readRoute(): Route {
  const [path, id, mode] = window.location.hash.slice(1).split('/')
  if (path === 'libraries') {
    try { return { destination: 'libraries', libraryId: id ? decodeURIComponent(id) : undefined } }
    catch { return { destination: 'libraries' } }
  }
  if (path === 'home' && (id === 'study' || id === 'exam')) return { destination: 'home', study: true }
  if (path === 'home' && id === 'local-practice') return { destination: 'home', offlinePractice: true }
  if (path === 'home' && id && /^[a-f0-9]{32}$/.test(id)) return { destination: 'home', taskId: id, practicing: mode === 'practice' }
  if (path === 'profile' || path === 'reports') return { destination: 'profile' }
  return { destination: 'home' }
}

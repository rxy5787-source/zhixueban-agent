import { useCallback, useEffect, useState } from 'react'
import { api, isActiveTask } from './generation'
import type { GenerationTaskSummary } from './generation'

export function useTaskHistory() {
  const [tasks, setTasks] = useState<GenerationTaskSummary[]>([])
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState('')
  const [revision, setRevision] = useState(0)
  const refresh = useCallback(() => setRevision(value => value + 1), [])

  useEffect(() => {
    const controller = new AbortController()
    let timer: number | undefined
    async function poll() {
      let delay = 4000
      try {
        const data = await api<{ tasks: GenerationTaskSummary[] }>('/api/generation-tasks', { signal: controller.signal })
        if (controller.signal.aborted) return
        setTasks(data.tasks)
        setLoaded(true)
        setError('')
        delay = data.tasks.some(isActiveTask) ? 2200 : 10000
      } catch (cause) {
        if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : '暂时无法读取出题任务')
      } finally {
        if (!controller.signal.aborted) timer = window.setTimeout(poll, delay)
      }
    }
    void poll()
    return () => { controller.abort(); window.clearTimeout(timer) }
  }, [revision])

  useEffect(() => {
    function onVisible() { if (document.visibilityState === 'visible') refresh() }
    document.addEventListener('visibilitychange', onVisible)
    return () => document.removeEventListener('visibilitychange', onVisible)
  }, [refresh])

  return { tasks, loaded, error, refresh }
}

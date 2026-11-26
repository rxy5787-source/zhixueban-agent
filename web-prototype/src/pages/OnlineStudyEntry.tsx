import { useEffect, useState } from 'react'
import { onlineStudyOrigin } from '../deployment'
import { STUDY_HASH } from '../routes'

type Availability = 'checking' | 'ready' | 'unreachable' | 'model-unavailable' | 'offline'

async function checkAvailability(origin: string): Promise<Availability> {
  if (!navigator.onLine) return 'offline'
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), 6500)
  try {
    const response = await fetch(new URL('/study-availability', origin), {
      signal: controller.signal, credentials: 'omit', cache: 'no-store', redirect: 'error',
    })
    if (!response.ok) return 'unreachable'
    const { status } = await response.json()
    return status === 'ready' || status === 'model-unavailable' || status === 'checking' ? status : 'unreachable'
  } catch {
    return navigator.onLine ? 'unreachable' : 'offline'
  } finally {
    window.clearTimeout(timeout)
  }
}

export function OnlineStudyEntry() {
  const [status, setStatus] = useState<Availability>('checking')
  const [opening, setOpening] = useState(false)
  const origin = onlineStudyOrigin

  useEffect(() => {
    if (!origin) return
    let active = true
    let revision = 0
    const refresh = () => {
      const check = ++revision
      setStatus(navigator.onLine ? 'checking' : 'offline')
      void checkAvailability(origin).then(result => {
        if (active && check === revision) setStatus(result)
      })
    }
    refresh()
    const timer = window.setInterval(refresh, 30_000)
    window.addEventListener('online', refresh)
    window.addEventListener('offline', refresh)
    window.addEventListener('focus', refresh)
    return () => {
      active = false
      window.clearInterval(timer)
      window.removeEventListener('online', refresh)
      window.removeEventListener('offline', refresh)
      window.removeEventListener('focus', refresh)
    }
  }, [origin])

  if (!origin) return <p className="supporting">本网站尚未配置在线 AI 服务。</p>

  async function open() {
    if (!origin || opening) return
    setOpening(true)
    setStatus('checking')
    const result = await checkAvailability(origin)
    setStatus(result)
    setOpening(false)
    if (result === 'ready') window.location.assign(new URL('/' + STUDY_HASH, origin))
  }

  return <div className="offline-card">
    <h2>在线学习</h2>
    <p role="status">
      {status === 'ready' && '已检测到在线服务和出题模型。进入前会再次检查。'}
      {status === 'checking' && '正在检查在线服务和出题模型…'}
      {status === 'offline' && '设备已断网。联网后可重试，仍可继续本地学习。'}
      {status === 'unreachable' && '暂时连不上在线服务。请检查网络、运行后端的电脑或试用链接。'}
      {status === 'model-unavailable' && '已连接后端，出题模型暂不可用。请检查 Ollama 后重试。'}
    </p>
    <p className="supporting">进入在线学习后，请在服务页面上传资料并发送要求。本机资料和记录留在此浏览器。</p>
    <button className="secondary-button" type="button" onClick={() => void open()} disabled={opening || status === 'offline'}>
      {opening ? '正在连接…' : status === 'ready' ? '进入在线学习' : '检查并进入在线学习'}
    </button>
  </div>
}

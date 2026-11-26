import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { App } from '../App'
import { setLearningAccount } from '../api/learningAccount'
import './account.css'

type Session = { username: string }
type Material = { id: string; title: string }
type FullMaterial = Material & { text: string }

class AccountError extends Error {
  constructor(readonly status: number, message: string) { super(message) }
}

async function accountApi<T>(path: string, method = 'GET', body?: object): Promise<T> {
  const response = await fetch(`/api/account${path}`, {
    method,
    credentials: 'same-origin',
    cache: 'no-store',
    headers: { 'X-Zhixue-Account': '1', ...(body ? { 'Content-Type': 'application/json' } : {}) },
    body: body ? JSON.stringify(body) : undefined,
    signal: AbortSignal.timeout(20000),
  })
  if (!response.ok) {
    const error = await response.json().catch(() => ({}))
    throw new AccountError(response.status, error.detail || '账号服务暂不可用，请稍后重试。')
  }
  if (response.status === 204) return undefined as T
  return response.json()
}

function message(error: unknown) {
  return error instanceof AccountError ? error.message : '网络连接暂不可用，请稍后重试。'
}

function AccountMaterials({ expire }: { expire: () => void }) {
  const [items, setItems] = useState<Material[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [title, setTitle] = useState('')
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(true)
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')
  const report = (failure: unknown) => {
    if (failure instanceof AccountError && failure.status === 401) expire()
    else setError(message(failure))
  }
  useEffect(() => {
    let active = true
    void accountApi<Material[]>('/materials').then(result => {
      if (active) setItems(result)
    }).catch(failure => { if (active) report(failure) }).finally(() => { if (active) setBusy(false) })
    return () => { active = false }
  }, [])
  async function run(action: () => Promise<void>) {
    setBusy(true)
    setNotice('')
    setError('')
    try { await action() } catch (failure) { report(failure) } finally { setBusy(false) }
  }
  function reset() { setSelected(null); setTitle(''); setText('') }
  function save(event: FormEvent) {
    event.preventDefault()
    void run(async () => {
      const value = await accountApi<FullMaterial>(selected ? `/materials/${selected}` : '/materials',
        selected ? 'PUT' : 'POST', { title, text })
      setItems(previous => [value, ...previous.filter(item => item.id !== value.id)])
      setSelected(value.id)
      setNotice('资料已保存。')
    })
  }
  return (
    <section className="account-materials">
      <h2>我的文字资料</h2>
      {error && <p role="alert">{error}</p>}
      <p role="status">{notice}</p>
      <ul>{items.map(item => <li key={item.id}><button type="button" disabled={busy}
        onClick={() => void run(async () => {
          const value = await accountApi<FullMaterial>(`/materials/${item.id}`)
          setSelected(value.id); setTitle(value.title); setText(value.text)
        })}>{item.title}</button></li>)}</ul>
      {!busy && items.length === 0 && !error && <p>还没有文字资料。</p>}
      <form onSubmit={save}>
        <label>标题<input required maxLength={120} value={title} onChange={e => setTitle(e.target.value)} /></label>
        <label>正文<textarea required maxLength={20000} rows={6} value={text} onChange={e => setText(e.target.value)} /></label>
        <div className="account-actions">
          <button type="submit" disabled={busy || !title.trim() || !text.trim()}>保存资料</button>
          <button type="button" disabled={busy} onClick={reset}>新建</button>
          {selected && <button type="button" disabled={busy} onClick={() => {
            if (!window.confirm('删除这份文字资料？')) return
            void run(async () => {
              await accountApi(`/materials/${selected}`, 'DELETE')
              setItems(previous => previous.filter(item => item.id !== selected))
              reset()
              setNotice('资料已删除。')
            })
          }}>删除资料</button>}
        </div>
      </form>
    </section>
  )
}

export function AccountPage() {
  const query = new URLSearchParams(location.search)
  const register = query.get('mode') === 'register'
  const materials = query.get('view') === 'materials'
  const [session, setSession] = useState<Session | null>(null)
  const [checking, setChecking] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const sessionChanges = useRef<BroadcastChannel | null>(null)
  useEffect(() => {
    let active = true
    void accountApi<Session>('/session').then(value => {
      if (!active) return
      if (materials) setSession(value)
      else location.replace('/learn#home/study')
    }).catch(error => {
      if (active && !(error instanceof AccountError && error.status === 401)) setError(message(error))
    }).finally(() => { if (active) setChecking(false) })
    const restored = (event: PageTransitionEvent) => { if (event.persisted) location.reload() }
    const channel = typeof BroadcastChannel === 'function' ? new BroadcastChannel('zhixue-account-session') : null
    if (channel) channel.onmessage = () => location.reload()
    sessionChanges.current = channel
    window.addEventListener('pageshow', restored)
    return () => {
      active = false
      channel?.close()
      sessionChanges.current = null
      window.removeEventListener('pageshow', restored)
    }
  }, [materials])
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (busy) return
    const credentials = new FormData(event.currentTarget)
    const username = credentials.get('username')
    const password = credentials.get('password')
    if (register && password !== credentials.get('confirm')) {
      setError('两次输入的密码不一致。')
      return
    }
    setBusy(true); setError('')
    try {
      await accountApi<Session>(register ? '/register' : '/login', 'POST', { username, password })
      sessionChanges.current?.postMessage('changed')
      location.replace('/learn#home/study')
    } catch (error) { setError(message(error)); setBusy(false) }
  }
  if (materials && session) return (
    <main className="account-page account-notes">
      <div className="account-panel">
        <a href="/learn#home/study">返回学习对话</a>
        <h1>{session.username} 的文字资料</h1>
        <AccountMaterials key={session.username} expire={() => location.replace('/account')} />
      </div>
    </main>
  )
  return (
    <main className="account-page">
      <div className="account-shell">
        <div className="account-brand">
          <a className="account-wordmark" href="/">知学伴</a>
          <div className="account-brand-copy">
            <strong>让知识生长。</strong>
            <p>在每一次探索中，拓宽思维的边界。</p>
          </div>
          <div className="account-landscape" aria-hidden="true">
            <i className="account-sun"/><i/><i/><i/><i/><i/><i/>
          </div>
        </div>
        <div className="account-panel">
          {checking ? <p role="status">正在验证登录状态…</p> : <>
            <h1>{register ? '创建账号' : '欢迎回来'}</h1>
            <p className="account-subtitle">{register ? '建立自己的学习空间' : '继续你的学习之旅'}</p>
            <form onSubmit={submit}>
              <label>用户名<input required name="username" placeholder="输入用户名" autoComplete="username"
                pattern="[A-Za-z0-9_]{4,32}" title="4–32 个字母、数字或下划线" /></label>
              <label>密码<span className="account-password">
                <input required name="password" type={showPassword ? 'text' : 'password'}
                  placeholder={register ? '至少 15 个字符' : '输入密码'}
                  autoComplete={register ? 'new-password' : 'current-password'}
                  minLength={register ? 15 : 8} maxLength={128} />
                <button type="button" aria-pressed={showPassword} onClick={() => setShowPassword(value => !value)}>
                  {showPassword ? '隐藏' : '显示'}</button>
              </span></label>
              {register && <label>确认密码<input required name="confirm" type={showPassword ? 'text' : 'password'}
                placeholder="再输入一次密码" autoComplete="new-password" minLength={15} maxLength={128} /></label>}
              {error && <p role="alert">{error}</p>}
              <button className="account-primary" type="submit" disabled={busy}>
                {busy ? '正在提交…' : register ? '创建账号并开始学习' : '登录'}
              </button>
            </form>
            <p className="account-switch">{register ? '已有账号？' : '还没有账号？'}
              <a href={register ? '/account' : '/account?mode=register'}>{register ? '登录' : '创建账号'}</a>
            </p>
            <a className="account-guest" href="/">继续以游客身份学习</a>
          </>}
        </div>
      </div>
    </main>
  )
}

export function AccountLearning() {
  const [session, setSession] = useState<Session | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    let active = true
    void accountApi<Session>('/session').then(value => {
      if (!active) return
      setLearningAccount(value.username)
      setSession(value)
    }).catch(error => {
      if (!active) return
      if (error instanceof AccountError && error.status === 401) location.replace('/account')
      else setError(message(error))
    })
    const channel = typeof BroadcastChannel === 'function' ? new BroadcastChannel('zhixue-account-session') : null
    if (channel) channel.onmessage = () => location.reload()
    const restored = (event: PageTransitionEvent) => { if (event.persisted) location.reload() }
    window.addEventListener('pageshow', restored)
    return () => { active = false; channel?.close(); window.removeEventListener('pageshow', restored) }
  }, [])
  async function signOut() {
    setBusy(true); setError('')
    try {
      await accountApi('/logout', 'POST')
      if (typeof BroadcastChannel === 'function') {
        const channel = new BroadcastChannel('zhixue-account-session')
        channel.postMessage('changed')
        channel.close()
      }
      location.replace('/account')
    } catch (error) { setError(message(error)); setBusy(false) }
  }
  if (!session) return <main className="account-page">{error
    ? <p role="alert">{error} <a href="/account">返回登录</a></p>
    : <p role="status">正在打开学习空间…</p>}</main>
  return <App accountAction={<div className="learning-account-actions">
    <a href="/account?view=materials">文字资料</a>
    <button type="button" disabled={busy} onClick={() => void signOut()}>退出</button>
    {error && <span role="alert">{error}</span>}
  </div>} />
}

export function GuestLearning() {
  const [accountsEnabled, setAccountsEnabled] = useState(false)
  useEffect(() => {
    const controller = new AbortController()
    void fetch('/api/account/session', { signal: controller.signal, cache: 'no-store' })
      .then(response => setAccountsEnabled(response.ok || response.status === 401))
      .catch(() => {})
    return () => controller.abort()
  }, [])
  return <App accountAction={accountsEnabled && <a className="task-entry" href="/account">登录</a>} />
}

import { useEffect, useState } from 'react'
import { DESTINATIONS } from '../data/demo'
import { readRoute, STUDY_HASH } from '../routes'
import { Icon } from '../components/Icon'
import { WelcomePage } from './WelcomePage'
import { OfflineConversation } from './OfflineConversation'
import { OfflinePractice } from './OfflinePractice'
import { sampleQuestions } from '../offline/questions'
import { addLibrary, addMaterials, deleteLibrary, deleteMaterial, readOfflineData, renameLibrary, saveAttempt } from '../offline/storage'
import type { LocalAttempt, LocalMaterial, OfflineData } from '../offline/storage'
import './offline.css'

if ('serviceWorker' in navigator) {
  // Only the offline production entry is emitted with this worker.
  if (import.meta.env.MODE === 'offline-study') {
    void navigator.serviceWorker.register('/offline-worker.js', { updateViaCache: 'none' }).catch(() => {})
  }
}

const EMPTY: OfflineData = { libraries: [], materials: [], attempts: [] }
const MAX_FILE_BYTES = 20 * 1024 * 1024
const PRACTICE = '#home/local-practice'

function download(material: LocalMaterial) {
  const url = URL.createObjectURL(material.file)
  const link = document.createElement('a')
  link.href = url
  link.download = material.name
  link.click()
  window.setTimeout(() => URL.revokeObjectURL(url), 30_000)
}

export function OfflineStudy() {
  const [route, setRoute] = useState(readRoute)
  const [data, setData] = useState(EMPTY)
  const [ready, setReady] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [editing, setEditing] = useState<'add' | 'rename' | null>(null)
  const [name, setName] = useState('')
  const library = data.libraries.find(item => item.id === route.libraryId)

  useEffect(() => {
    const sync = () => { setRoute(readRoute()); setEditing(null) }
    window.addEventListener('hashchange', sync)
    return () => window.removeEventListener('hashchange', sync)
  }, [])
  useEffect(() => {
    let active = true
    readOfflineData().then(value => {
      if (active) { setData(value); setReady(true) }
    }).catch(() => { if (active) setError('无法打开浏览器本地存储，请检查站点存储权限后刷新。') })
    return () => { active = false }
  }, [])

  async function update(action: () => Promise<void>, onSaved?: () => void) {
    if (busy) return
    setBusy(true)
    setError('')
    try {
      await action()
      onSaved?.()
      try { setData(await readOfflineData()) }
      catch { setError('操作已保存，页面暂时无法刷新数据。请重新加载。') }
    } catch {
      setError('未能保存操作。请检查浏览器存储空间或刷新后重试。')
    } finally { setBusy(false) }
  }

  async function storeMaterials(libraryId: string | null, files: File[]) {
    if (files.some(file => !/\.(pdf|docx?|txt)$/i.test(file.name) || !file.size || file.size > MAX_FILE_BYTES)) {
      throw new Error('请选择非空的 PDF、Word（DOC 或 DOCX）或 TXT 文件，每个文件最多 20 MiB。')
    }
    try { await addMaterials(libraryId, files) }
    catch { throw new Error('资料尚未保存。请检查站点存储权限或空间后重试。') }
    await refreshSavedData()
  }

  async function refreshSavedData() {
    try { setData(await readOfflineData()) }
    catch { setError('数据已保存，暂时无法刷新列表。请重新加载页面。') }
  }

  async function recordAttempt(attempt: LocalAttempt) {
    await saveAttempt(attempt)
    await refreshSavedData()
  }

  const go = (hash: string) => { window.location.hash = hash }

  return <div className="workbench editorial-workbench">
    <div className="phone-frame"><div className="mobile-app mobile-app--handbook">
      <div className="app-content">
        <header className="app-header">
          <button className="app-brand" aria-label="知学伴首页" onClick={() => go('#home')}>
            <span className="handbook-brand-mark"><Icon name="libraries" size={20}/></span><strong>知学伴</strong>
          </button>
          <span className="handbook-tag">本地学习</span>
        </header>
        <main className="page-scroll">
          {error && <p className="offline-error generation-error" role="alert">{error}</p>}
          {route.destination === 'home' && route.offlinePractice &&
            <OfflinePractice onSave={recordAttempt} onRecords={() => go('#profile')} />}
          {route.destination === 'home' && route.study &&
            <OfflineConversation libraries={data.libraries} ready={ready} onFiles={storeMaterials} onPractice={() => go(PRACTICE)} />}
          {route.destination === 'home' && route.taskId && <section className="offline-page">
            <h1>在线出题任务</h1>
            <p>离线模式无法读取在线任务。请使用连接 FastAPI 的版本查看出题结果。</p>
            <button className="secondary-button" onClick={() => go(STUDY_HASH)}>打开学习对话</button>
          </section>}
          {route.destination === 'home' && !route.offlinePractice && !route.study && !route.taskId &&
            <WelcomePage onStart={() => go(STUDY_HASH)} />}
          {route.destination === 'libraries' && <section className="offline-page">
            {route.libraryId ? <button className="back-link" onClick={() => go('#libraries')}>返回知识库</button> : null}
            <h1>{library?.name ?? '本地知识库'}</h1>
            <p className="supporting">导入的原文件保存在当前浏览器，可取回下载。PDF、Word 和 TXT 的解析与出题需要后端。</p>
            {!ready && !error && <p role="status">正在读取本地资料…</p>}
            {ready && !route.libraryId && <>
              <button className="primary-button" disabled={busy} onClick={() => { setName(''); setEditing('add') }}>新建知识库</button>
              {data.libraries.length ? <ul className="offline-list">{data.libraries.map(item => <li key={item.id}>
                <button className="secondary-button" onClick={() => go(`#libraries/${item.id}`)}>{item.name}</button>
              </li>)}</ul> : <p className="supporting">还没有本地知识库。</p>}
            </>}
            {ready && route.libraryId && !library && <p>未在此浏览器找到该知识库。</p>}
            {library && <div className="offline-card">
              <div className="offline-actions">
                <button className="secondary-button" disabled={busy} onClick={() => { setName(library.name); setEditing('rename') }}>改名</button>
                <button className="danger-button" disabled={busy} onClick={() => {
                  if (window.confirm('删除这个本地知识库及其保存的资料？')) void update(() => deleteLibrary(library.id), () => go('#libraries'))
                }}>删除知识库</button>
              </div>
              <label className="field-label" htmlFor="offline-materials">导入资料到本机</label>
              <input className="text-field offline-file" id="offline-materials" type="file" accept=".pdf,.doc,.docx,.txt" multiple disabled={busy}
                onChange={event => {
                  const files = Array.from(event.currentTarget.files ?? [])
                  event.currentTarget.value = ''
                  if (!files.length) return
                  setError('')
                  setBusy(true)
                  void storeMaterials(library.id, files).catch(cause => setError(cause.message)).finally(() => setBusy(false))
                }}/>
              <ul className="offline-list">{data.materials.filter(item => item.libraryId === library.id).map(item => <li key={item.id}>
                <strong>{item.name}</strong>
                <div className="offline-actions">
                  <button className="secondary-button" onClick={() => download(item)}>下载</button>
                  <button className="archive-link remove-link" disabled={busy} onClick={() => {
                    if (window.confirm('移除这份本地资料？')) void update(() => deleteMaterial(item.id))
                  }}>移除</button>
                </div>
              </li>)}</ul>
            </div>}
            {editing && <form className="offline-card" onSubmit={event => {
              event.preventDefault()
              const value = name.trim()
              if (!value) { setError('请输入知识库名称。'); return }
              if (editing === 'add') void update(() => addLibrary(value), () => setEditing(null))
              else if (library) void update(() => renameLibrary(library.id, value), () => setEditing(null))
            }}>
              <label className="field-label" htmlFor="offline-library-name">知识库名称</label>
              <input className="text-field" id="offline-library-name" required value={name} maxLength={80} onChange={event => setName(event.target.value)}/>
              <div className="offline-actions">
                <button className="primary-button" disabled={busy}>保存知识库</button>
                <button className="secondary-button" type="button" disabled={busy} onClick={() => setEditing(null)}>取消</button>
              </div>
            </form>}
          </section>}
          {route.destination === 'profile' && <section className="offline-page">
            <h1>本地学习记录</h1>
            <p className="supporting">记录只保存在当前浏览器和站点。清除站点数据会移除资料与记录。</p>
            {ready && !data.attempts.length && <p>还没有作答记录。</p>}
            <ul className="offline-list">{data.attempts.map(attempt => {
              const item = sampleQuestions.find(candidate => candidate.id === attempt.questionId)
              return <li className="offline-card" key={attempt.id}>
                <strong>{item?.stem ?? '示例题'}</strong>
                <p>{attempt.correct ? '答对' : '答错'} · {new Date(attempt.time).toLocaleString('zh-CN')}</p>
              </li>
            })}</ul>
            <button className="primary-button" onClick={() => go(PRACTICE)}>练习示例题</button>
          </section>}
        </main>
        <nav className="bottom-nav" aria-label="主导航">{DESTINATIONS.map(item => (
          <button key={item.id} data-destination={item.id} aria-current={route.destination === item.id ? 'page' : undefined}
            onClick={() => go(`#${item.id}`)}>
            <span className="nav-icon"><span className="handbook-nav-glyph" aria-hidden="true"/></span><span>{item.id === 'profile' ? '记录' : item.title}</span>
          </button>
        ))}</nav>
      </div>
    </div></div>
  </div>
}

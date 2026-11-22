import { useEffect, useRef, useState } from 'react'
import { loadProfileSettings, saveProfileSettings } from '../api/profileSettings'
import type { ProfileSettings } from '../api/profileSettings'
import { Icon } from '../components/Icon'
import { Sheet } from '../components/Sheet'
import { DESTINATIONS, LIBRARY_SEEDS } from '../data/demo'
import { readRoute, STUDY_HASH } from '../routes'
import { BookshelfPage, LibraryDetailPage } from './LibraryPage'
import { ProfilePage } from './ProfilePage'
import { WelcomePage } from './WelcomePage'

const SAMPLE_LIBRARIES = LIBRARY_SEEDS.map(library => ({ ...library, updated: '示例主题' }))

export function StaticDemo() {
  const [route, setRoute] = useState(readRoute)
  const [settings, setSettings] = useState(loadProfileSettings)
  const [notice, setNotice] = useState('')
  const main = useRef<HTMLElement>(null)
  const pageKey = `${route.destination}/${route.libraryId ?? route.taskId ?? (route.study ? 'study' : '')}`
  useEffect(() => {
    function sync() {
      setRoute(readRoute())
      setNotice(window.location.hash === '#reports' ? '学习分析' : '')
    }
    sync()
    window.addEventListener('hashchange', sync)
    return () => window.removeEventListener('hashchange', sync)
  }, [])
  useEffect(() => { main.current?.focus({ preventScroll: true }) }, [pageKey])

  function save(value: ProfileSettings) {
    try { saveProfileSettings(value); setSettings(value); return true }
    catch { return false }
  }

  const go = (hash: string) => { window.location.hash = hash }
  const openLibrary = (id: string) => go(`#libraries/${encodeURIComponent(id)}`)
  const library = SAMPLE_LIBRARIES.find(item => item.id === route.libraryId)
  const actionNotice = (title: string) => () => setNotice(title)

  return <div className="workbench editorial-workbench">
    <div className="phone-frame"><div className="mobile-app mobile-app--handbook">
      <div className="app-content" inert={!!notice}>
        <header className="app-header">
          <button type="button" className="app-brand" aria-label="知学伴首页" onClick={() => go('#home')}>
            <span className="handbook-brand-mark"><Icon name="libraries" size={20}/></span><strong>知学伴</strong>
          </button>
          <span className="handbook-tag">静态演示版</span>
        </header>
        <main className="page-scroll" key={pageKey} ref={main} tabIndex={-1}>
          {route.destination === 'home' && (route.study || route.taskId
            ? <section className="empty-state">
              <h1>{route.practicing ? '练习' : route.taskId ? '出题任务' : '学习对话'}</h1>
              <p>在线服务尚未开放。资料上传、AI 出题和答题需要连接学习服务。</p>
              <button className="secondary-button" onClick={() => go('#home')}>返回首页</button>
            </section>
            : <WelcomePage onStart={() => go(STUDY_HASH)} />)}
          {route.destination === 'libraries' && (library
            ? <LibraryDetailPage library={library} onBack={() => go('#libraries')} onRename={actionNotice('知识库改名')}
              onDelete={actionNotice('删除知识库')} onCompose={actionNotice('资料上传与出题')}
              onRecords={actionNotice('练习记录')} onAnalysis={actionNotice('学习分析')}
              onDocument={actionNotice('查看资料')} onRemoveItem={actionNotice('移除资料')} />
            : route.libraryId
              ? <section className="empty-state"><h1>该主题无法在演示版中读取</h1><p>在线服务尚未开放。可以返回书架浏览示例主题。</p>
                <button className="secondary-button" onClick={() => go('#libraries')}>返回书架</button></section>
              : <BookshelfPage libraries={SAMPLE_LIBRARIES} deletedCount={0} loading={false} error=""
                onRetry={actionNotice('知识库')} onTrash={actionNotice('回收站')} onOpen={openLibrary} onCreate={actionNotice('新建知识库')} />)}
          {route.destination === 'profile' && <ProfilePage settings={settings} libraries={SAMPLE_LIBRARIES}
            onSave={save} onRecords={actionNotice('学习记录')} onSettings={actionNotice('演示版说明')}
            onOpenTask={actionNotice('出题任务')} onLibrary={openLibrary} onReview={actionNotice('按薄弱点出题')} />}
        </main>
        <nav className="bottom-nav" aria-label="主导航">{DESTINATIONS.map(item => (
          <button key={item.id} data-destination={item.id} aria-current={route.destination === item.id ? 'page' : undefined}
            onClick={() => go(`#${item.id}`)}>
            <span className="nav-icon"><span className="handbook-nav-glyph" aria-hidden="true"/></span><span>{item.title}</span>
          </button>
        ))}</nav>
      </div>
      {notice && <Sheet title={notice} onClose={() => setNotice('')}>
        <p className="sheet-description">{notice === '演示版说明'
          ? '昵称、学习目标与偏好仅保存在当前浏览器中。实际练习与学习数据需等在线服务开放。'
          : '在线服务尚未开放。此功能需要连接学习服务。'}</p>
      </Sheet>}
    </div></div>
  </div>
}

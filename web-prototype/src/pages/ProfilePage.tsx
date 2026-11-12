import { useCallback, useEffect, useState } from 'react'
import { api } from '../api/generation'
import type { PracticeHistory } from '../api/generation'
import type { ProfileSettings } from '../api/profileSettings'
import { onlineTrial } from '../deployment'
import { Icon } from '../components/Icon'
import { PointProgressList } from '../components/PointProgressList'
import { Sheet } from '../components/Sheet'
import companion from '../assets/handbook/paper-companion.svg'
import './profile.css'

type LibraryReference = { id: string; title: string }
type Analysis = { library: LibraryReference; data?: PracticeHistory }

export function ProfilePage({ settings, libraries, onSave, onRecords, onSettings, onOpenTask, onLibrary, onReview }: {
  settings: ProfileSettings; libraries: LibraryReference[]; onSave: (value: ProfileSettings) => boolean
  onRecords: () => void; onSettings: () => void; onOpenTask: (id: string) => void; onLibrary: (id: string) => void
  onReview: (libraryId: string) => void
}) {
  const [panel, setPanel] = useState<'info' | 'preferences' | 'analysis' | null>(null)
  const close = useCallback(() => setPanel(null), [])
  const [draft, setDraft] = useState(settings)
  const [saveError, setSaveError] = useState('')
  const [history, setHistory] = useState<PracticeHistory | null>(null)
  const [error, setError] = useState('')
  const [refresh, setRefresh] = useState(0)
  const [analysis, setAnalysis] = useState<Analysis[] | null>(null)
  const libraryKey = libraries.map(library => `${library.id}/${library.title}`).join('|')

  useEffect(() => {
    const controller = new AbortController()
    setError('')
    api<PracticeHistory>('/api/practice-history', { signal: controller.signal }).then(value => {
      if (!controller.signal.aborted) setHistory(value)
    }).catch(cause => {
      if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : '暂时无法读取学习记录')
    })
    return () => controller.abort()
  }, [refresh])

  useEffect(() => {
    if (panel !== 'analysis') return
    const controller = new AbortController()
    setAnalysis(null)
    void Promise.all(libraries.map(async library => {
      try {
        const data = await api<PracticeHistory>(`/api/practice-history?libraryId=${encodeURIComponent(library.id)}`, { signal: controller.signal })
        return { library, data }
      } catch { return { library } }
    })).then(values => { if (!controller.signal.aborted) setAnalysis(values) })
    return () => controller.abort()
  }, [panel, libraryKey, refresh])

  const sessions = history?.sessions ?? []
  const recentAnswered = sessions.reduce((sum, item) => sum + item.answered, 0)
  const recentCorrect = sessions.reduce((sum, item) => sum + item.correct, 0)
  const today = new Date().toLocaleDateString('sv-SE')
  const todaySessions = sessions.filter(item => new Date(item.created * 1000).toLocaleDateString('sv-SE') === today)
  const todayAnswered = todaySessions.reduce((sum, item) => sum + item.answered, 0)
  const todayAtLeast = todaySessions.length === 30
  const days = new Set(sessions.map(item => new Date(item.created * 1000).toLocaleDateString('sv-SE'))).size
  const known = analysis?.filter(item => item.data?.points.length) ?? []
  const weakCount = known.reduce((sum, item) => sum + item.data!.points.filter(point => point.reviewPriority).length, 0)

  function edit(next: 'info' | 'preferences') {
    setDraft(settings); setSaveError(''); setPanel(next)
  }

  function save() {
    if (!draft.nickname.trim()) { setSaveError('请填写昵称'); return }
    if (onSave({ ...draft, nickname: draft.nickname.trim(), learningGoal: draft.learningGoal.trim() })) setPanel(null)
    else setSaveError('设置未能保存，请检查浏览器的站点存储权限后重试。')
  }

  return <div className="profile-page page-enter">
    <header className="handbook-section-intro profile-intro">
      <div className="handbook-section-copy"><span className="handbook-tag">学习手帐</span><h1>我的</h1><p>记下进步，也找到下一步。</p></div>
      <img src={companion} width="122" height="130" alt=""/>
    </header>
    <button className="profile-card learner-card" onClick={() => edit('info')} aria-label="编辑个人信息">
      <span className="avatar"><Icon name={settings.avatar === 'book' ? 'libraries' : settings.avatar} size={27}/></span>
      <span className="learner-copy"><strong>{settings.nickname}</strong><small>{settings.learningGoal || '为自己设一个学习目标'}</small><small>{onlineTrial ? '浏览器试用空间' : '本机学习空间'}</small></span>
      <Icon name="chevron" size={17}/>
    </button>

    <section className="profile-goal" aria-label="今日学习目标">
      <div className="profile-section-heading"><h2>今天，学一点</h2><button onClick={() => edit('preferences')}>调整目标<Icon name="chevron" size={13}/></button></div>
      <p>{history ? `今日${todayAtLeast ? '至少' : '完成'} ${todayAnswered} 题` : error ? '暂时无法读取今日练习' : '正在读取今日练习'}<span>目标 {settings.dailyTarget} 题</span></p>
      <progress aria-label="今日答题目标进度" max={settings.dailyTarget} value={Math.min(todayAnswered, settings.dailyTarget)}/>
      {history && <small>{todayAnswered >= settings.dailyTarget ? '今日目标已完成，记得休息一下。' : '完成一组练习并保存结果后，进度会自动更新。'}</small>}
    </section>

    <section className="profile-summary" aria-label="近期学习概况">
      <div className="profile-section-heading"><h2>最近的积累</h2><span>最近 30 次练习</span></div>
      {error ? <div role="alert"><p>{error}</p><button className="archive-link" onClick={() => setRefresh(value => value + 1)}>重新读取</button></div> :
        <div className="profile-metrics"><div><strong>{history ? recentAnswered : '—'}</strong><span>答题数</span></div><div><strong>{history && recentAnswered ? `${Math.round(recentCorrect / recentAnswered * 100)}%` : '—'}</strong><span>答题正确率</span></div><div><strong>{history ? days : '—'}</strong><span>有练习的天数</span></div></div>}
    </section>

    <div className="profile-menu">
      <button onClick={onRecords}><span className="profile-menu-mark"><Icon name="clock" size={20}/></span><span className="profile-menu-copy"><strong>学习记录</strong><small>查看成绩，回到原题练习</small></span><Icon name="chevron" size={16}/></button>
      <button onClick={() => setPanel('analysis')}><span className="profile-menu-mark"><Icon name="reports" size={20}/></span><span className="profile-menu-copy"><strong>学习分析</strong><small>按知识库查看掌握估计与薄弱点</small></span><Icon name="chevron" size={16}/></button>
      <button onClick={() => edit('preferences')}><span className="profile-menu-mark"><Icon name="target" size={20}/></span><span className="profile-menu-copy"><strong>学习偏好</strong><small>每日目标、默认题量与出题侧重</small></span><Icon name="chevron" size={16}/></button>
      <button onClick={onSettings}><span className="profile-menu-mark"><Icon name="settings" size={20}/></span><span className="profile-menu-copy"><strong>设置与帮助</strong><small>学习空间说明与草稿管理</small></span><Icon name="chevron" size={16}/></button>
    </div>

    <section className="profile-recent" aria-label="最近练习">
      <div className="profile-section-heading"><h2>最近练习</h2><button onClick={onRecords}>全部记录<Icon name="chevron" size={13}/></button></div>
      {sessions.slice(0, 3).map(item => <button className="profile-record" key={item.sessionId} onClick={() => onOpenTask(item.taskId)}><Icon name="clock" size={17}/><span><strong>{item.libraryName}</strong><small>{new Date(item.created * 1000).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</small></span><b>{item.correct}/{item.answered}</b><Icon name="chevron" size={14}/></button>)}
      {history && !sessions.length && <p className="supporting">完成第一组练习后，这里就会留下你的学习足迹。</p>}
      {!history && !error && <p className="supporting" role="status">正在读取练习…</p>}
    </section>

    {panel && <Sheet title={panel === 'info' ? '个人信息' : panel === 'preferences' ? '学习偏好' : '学习分析'} onClose={close}>
      {panel === 'info' && <form className="profile-form" onSubmit={event => { event.preventDefault(); save() }}>
        <label className="field-label" htmlFor="learner-nickname">昵称</label><input className="text-field" id="learner-nickname" maxLength={20} value={draft.nickname} onChange={event => setDraft({ ...draft, nickname: event.target.value })}/>
        <label className="field-label" htmlFor="learner-goal">学习目标</label><input className="text-field" id="learner-goal" maxLength={100} placeholder="例如：备考软件设计师" value={draft.learningGoal} onChange={event => setDraft({ ...draft, learningGoal: event.target.value })}/>
        <fieldset className="profile-avatar-options"><legend>选择头像</legend>{(['profile', 'book', 'leaf'] as const).map(value => <label key={value}><input type="radio" name="learner-avatar" checked={draft.avatar === value} onChange={() => setDraft({ ...draft, avatar: value })}/><Icon name={value === 'book' ? 'libraries' : value}/><span>{value === 'profile' ? '学习者' : value === 'book' ? '书本' : '叶子'}</span></label>)}</fieldset>
        {saveError && <p className="field-error" role="alert">{saveError}</p>}<p className="supporting">个人信息与偏好保存在当前浏览器中。</p><button className="primary-button" type="submit">保存信息<Icon name="check" size={17}/></button>
      </form>}
      {panel === 'preferences' && <form className="profile-form" onSubmit={event => { event.preventDefault(); save() }}>
        <label className="field-label" htmlFor="daily-target">每日答题目标</label><select className="text-field" id="daily-target" value={draft.dailyTarget} onChange={event => setDraft({ ...draft, dailyTarget: Number(event.target.value) })}>{[5, 10, 20, 30].map(count => <option key={count} value={count}>{count} 题</option>)}</select>
        <label className="field-label" htmlFor="preferred-count">默认出题数量</label><select className="text-field" id="preferred-count" value={draft.questionCount} onChange={event => setDraft({ ...draft, questionCount: Number(event.target.value) })}>{[0, 3, 5, 10].map(count => <option key={count} value={count}>{count ? `${count} 题` : '跟随当前场景'}</option>)}</select>
        <label className="field-label" htmlFor="preferred-difficulty">默认难度侧重</label><select className="text-field" id="preferred-difficulty" value={draft.difficulty} onChange={event => setDraft({ ...draft, difficulty: event.target.value as ProfileSettings['difficulty'] })}><option value="auto">由出题要求决定</option><option value="basic">基础</option><option value="intermediate">中等</option><option value="advanced">提高</option></select>
        <label className="profile-checkbox"><input type="checkbox" checked={draft.weakFirst} onChange={event => setDraft({ ...draft, weakFirst: event.target.checked })}/><span>优先巩固薄弱知识点<small>依据所选知识库的答题记录，在资料支持的范围内出题。</small></span></label>
        <p className="supporting">输入框里明确写出的题量与难度优先。当前支持四选一单选题。</p>{saveError && <p className="field-error" role="alert">{saveError}</p>}<button className="primary-button" type="submit">保存偏好<Icon name="check" size={17}/></button>
      </form>}
      {panel === 'analysis' && <>
        {!analysis && <p className="supporting" role="status">正在读取各知识库的学习数据…</p>}
        {analysis && <p className="sheet-description">{weakCount ? `${weakCount} 个知识点需要优先巩固。` : known.length ? '继续练习，掌握估计会随作答更新。' : '完成练习并保存结果后，这里会出现掌握估计。'}</p>}
        {analysis?.some(item => !item.data) && <div role="alert"><p className="supporting">部分知识库暂时无法读取，当前仅显示已读取的数据。</p><button className="archive-link" onClick={() => setRefresh(value => value + 1)}>重新读取</button></div>}
        {known.map(({ library, data }) => {
          if (!data) return null
          return <section className="profile-analysis-group" key={library.id}>
            <div className="profile-section-heading"><h2>{library.title}</h2><button onClick={() => onLibrary(library.id)}>前往知识库<Icon name="chevron" size={13}/></button></div>
            <PointProgressList points={data.points}/>
            {data.points.some(point => point.reviewPriority) && <button className="secondary-button" onClick={() => onReview(library.id)}>按薄弱点出题<Icon name="arrow" size={16}/></button>}
          </section>
        })}
      </>}
    </Sheet>}
  </div>
}

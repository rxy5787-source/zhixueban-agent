import { useEffect, useRef, useState } from 'react'
import { api, ApiHttpError, isActiveTask } from '../api/generation'
import type { GenerationTask, PracticeReport } from '../api/generation'
import { CLOZE_FROM_MNEMONIC } from '../api/study'
import type { StudyTurn } from '../api/study'
import { Icon } from '../components/Icon'
import { PointProgressList } from '../components/PointProgressList'
import './study.css'

type Feedback = { id: string; correct: boolean; answer: string; evidence: string; source: string; location: string }
type ResultProps = {
  task: GenerationTask; onSaved: () => Promise<void>; onPrompt?: (text: string) => void
}

export function StudyResultCard({ task, onSaved, onPrompt }: ResultProps) {
  const result = task.study?.result
  const [saved, setSaved] = useState(false)
  const [answers, setAnswers] = useState<Record<string, string>>({})
  const [submission, setSubmission] = useState<{ report: PracticeReport; feedback: Feedback[] }>()
  const [busy, setBusy] = useState<'save' | 'practice' | null>(null)
  const [error, setError] = useState('')
  const session = useRef<string | null>(null)

  async function save() {
    setBusy('save')
    setError('')
    try {
      await api(`/api/study-turns/${task.taskId}/save`, { method: 'POST' })
      setSaved(true)
      await onSaved().catch(() => {})
    } catch (cause) { setError(cause instanceof Error ? cause.message : '保存失败') }
    finally { setBusy(null) }
  }

  async function grade() {
    if (result?.kind !== 'cloze' || busy || submission) return
    setBusy('practice')
    setError('')
    session.current ??= crypto.randomUUID()
    try {
      const response = await api<{ report: PracticeReport; feedback: Feedback[] }>(`/api/study-turns/${task.taskId}/practice-sessions`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sessionId: session.current, answers: result.items.map(item => ({
          questionId: item.id, answer: answers[item.id]?.trim(),
        })) }),
      })
      setSubmission(response)
    } catch (cause) { setError(cause instanceof Error ? cause.message : '答题结果未能保存，请重试。') }
    finally { setBusy(null) }
  }

  if (task.libraryDeleted || task.study?.hidden) return <p className="supporting">内容已移入回收站，可以恢复后继续查看。</p>
  if (!result) return null
  return <article className="study-result">
    <header><span>{result.kind === 'cloze' ? '填空练习' : result.kind === 'mnemonic' ? '记忆口诀' : '资料解答'}</span><h2>{result.title}</h2></header>
    {result.kind === 'cloze' ? <form onSubmit={event => { event.preventDefault(); void grade() }}>
      {result.items.map((item, index) => {
        const checked = submission?.feedback.find(entry => entry.id === item.id)
        return <div className="study-blank" key={item.id}>
          <p>{index + 1}. {item.before}<span className="blank-line" aria-label="空格">_____</span>{item.after}</p>
          <input className="text-field" aria-label={`第 ${index + 1} 题答案`} placeholder="填写原文中的词" maxLength={80}
            disabled={!!submission || busy === 'practice'} value={answers[item.id] ?? ''} required
            onChange={event => {
              session.current = null
              setAnswers(previous => ({ ...previous, [item.id]: event.target.value }))
            }}/>
          {checked && <div className="study-feedback">
            <p><strong>{checked.correct ? '答对了' : '正确答案'} · {checked.answer}</strong></p>
            <p>{checked.evidence}</p>
            <small>{checked.source} · {checked.location}</small>
          </div>}
        </div>
      })}
      {submission ? <section className="study-report"><h3>答对 {submission.report.correct} / {submission.report.answered} 题</h3><PointProgressList points={submission.report.points}/></section> :
        <button className="primary-button" type="submit" disabled={!!busy || result.items.some(item => !answers[item.id]?.trim())}>
          {busy === 'practice' ? '正在保存答案…' : '提交填空答案'}<Icon name="check" size={16}/>
        </button>}
    </form> : result.cards?.length ? <div className="study-mnemonic-groups">
      <p className="supporting">共 {result.cards.length} 组。先背粗体，卡住时再展开解释。</p>
      {result.cards.map((card, index) => <section className="study-mnemonic-group" key={index}>
        <h3>{card.title}</h3>
        <p className="mnemonic-text">{card.mnemonic}</p>
        <details className="study-evidence">
          <summary>看解释与原文</summary>
          {card.anchors.map(anchor => <figure key={`${anchor.point}-${anchor.evidence}`}>
            {anchor.meaning !== anchor.evidence && <p><strong>{anchor.point}</strong>　{anchor.meaning}</p>}
            <blockquote>{anchor.evidence}</blockquote>
            <figcaption>{anchor.source} · {anchor.location}{anchor.ocr ? ' · OCR，请对照原件' : ''}</figcaption>
          </figure>)}
        </details>
      </section>)}
    </div> : <>
      <p className={result.kind === 'mnemonic' ? 'mnemonic-text' : 'study-reply'}>{result.content}</p>
      <ul className="study-anchors">{result.anchors.map(anchor => <li key={anchor.point}>
        <strong>{anchor.cue ? `「${anchor.cue}」 · ${anchor.point}` : anchor.point}</strong> {anchor.meaning}
      </li>)}</ul>
      <details className="study-evidence"><summary>查看资料依据</summary>
        {result.anchors.map(anchor => <figure key={anchor.point}><blockquote>{anchor.evidence}</blockquote><figcaption>{anchor.source} · {anchor.location}{anchor.ocr ? ' · OCR，请对照原件' : ''}</figcaption></figure>)}
      </details>
    </>}
    {result.limited && <p className="supporting">{result.kind === 'mnemonic' && result.cards?.length
      ? '已整理能核对的知识点，未覆盖的章节请对照原文。'
      : '本轮使用了资料中的部分可读段落。'}</p>}
    {result.kind === 'cloze' && result.ocr && <p className="supporting">部分题干来自图片识别，请对照原件核实。</p>}
    {error && <p className="field-error" role="alert">{error}</p>}
    <div className="study-actions">
      <button className="secondary-button" disabled={!!busy || saved || task.study?.saved} onClick={() => void save()}>
        {saved || task.study?.saved ? '已保存到知识库' : busy === 'save' ? '正在保存…' : '保存到知识库'}
      </button>
      {onPrompt && result.kind === 'mnemonic' && <button className="secondary-button" onClick={() => onPrompt(CLOZE_FROM_MNEMONIC)}>用这段口诀考我</button>}
    </div>
  </article>
}

export function StudyTurnCard({ turn, onOpen, onSaved, onPrompt, onRetry, revision, missing, onMissing, onReattach }: {
  turn: StudyTurn; onOpen: (id: string, practice?: boolean) => void; onSaved: () => Promise<void>
  onPrompt?: (text: string) => void; onRetry?: (id: string) => Promise<void>; revision: number
  missing: boolean; onMissing: (id: string) => void; onReattach?: () => void
}) {
  const [task, setTask] = useState<GenerationTask>()
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  const [retrying, setRetrying] = useState(false)
  const [retryError, setRetryError] = useState('')
  async function retry() {
    if (!onRetry || retrying) return
    setRetrying(true)
    setRetryError('')
    try { await onRetry(turn.id) }
    catch (cause) { setRetryError(cause instanceof Error ? cause.message : '重试失败') }
    finally { setRetrying(false) }
  }
  useEffect(() => {
    if (missing) return
    const controller = new AbortController()
    let timer: number | undefined
    async function poll() {
      try {
        const value = await api<GenerationTask>(`/api/generation-tasks/${turn.id}`, { signal: controller.signal })
        if (controller.signal.aborted) return
        setTask(value)
        setError('')
        if (isActiveTask(value)) timer = window.setTimeout(poll, 2400)
      } catch (cause) {
        if (controller.signal.aborted) return
        if (cause instanceof ApiHttpError && cause.status === 404) {
          onMissing(turn.id)
          return
        }
        setError(cause instanceof Error ? cause.message : '无法读取这轮对话')
        if (!(cause instanceof ApiHttpError) || cause.status >= 500) timer = window.setTimeout(poll, 6000)
      }
    }
    void poll()
    return () => { controller.abort(); window.clearTimeout(timer) }
  }, [turn.id, attempt, revision, missing, onMissing])

  return <div className="study-turn">
    <div className="study-user-message"><p>{turn.requirement}</p>
      {turn.sources.length > 0 && <small className="study-context">{turn.sources.join('、')}</small>}
    </div>
    {missing ? <div className="generation-error" role="alert">
      <p>当前学习空间找不到这轮任务。重新上传原资料后可以继续。</p>
      <button className="archive-link" disabled={!onReattach} onClick={onReattach}>重新上传资料</button>
    </div> : <div className="study-assistant">
      {!task && !error && <p className="study-status" role="status">正在读取任务…</p>}
      {task && isActiveTask(task) && <div>
        <p className="study-status" role="status"><Icon name="clock" size={16}/>{error ? '正在重连任务状态…' : task.stage}</p>
        {turn.kind === 'single_choice' && <button className="archive-link" onClick={() => onOpen(task.taskId)}>查看任务进度</button>}
      </div>}
      {error && <div className="generation-error" role="alert"><p>{error}</p><button className="archive-link" onClick={() => setAttempt(value => value + 1)}>重新查询</button></div>}
      {task?.study?.result && <StudyResultCard task={task} onSaved={onSaved} onPrompt={onPrompt}/>}
      {task && !task.study && task.acceptedQuestionCount > 0 && <article className="study-result">
        <header><span>选择题</span><h2>{task.acceptedQuestionCount} 道可练习题</h2></header>
        {task.availableQuestions?.[0] && <p className="study-reply">{task.availableQuestions[0].prompt}</p>}
        <div className="study-actions"><button className="secondary-button" onClick={() => onOpen(task.taskId, true)}>开始练习</button>
          <button className="archive-link" onClick={() => onOpen(task.taskId)}>查看题目集</button></div>
      </article>}
      {task && !isActiveTask(task) && !task.study?.result && !task.acceptedQuestionCount && <div className="generation-error">
        <p>{task.error || (task.study?.hidden || task.libraryDeleted ? '内容已移入回收站。' : '这轮没有可用结果。')}</p>
        {onRetry && !task.study?.hidden && !task.libraryDeleted && !task.removedSet ?
          <button className="archive-link" disabled={retrying} onClick={() => void retry()}>{retrying ? '正在重试…' : '重试这轮任务'}</button> :
          <button className="archive-link" onClick={() => onOpen(task.taskId)}>查看任务详情</button>}
        {retryError && <p role="alert">{retryError}</p>}
      </div>}
    </div>}
  </div>
}

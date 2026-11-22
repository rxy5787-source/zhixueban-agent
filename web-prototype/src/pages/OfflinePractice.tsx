import { useRef, useState } from 'react'
import { gradeAnswer, localRecordId } from '../offline/attempt'
import { sampleQuestions } from '../offline/questions'
import type { LocalAttempt } from '../offline/storage'

export function OfflinePractice({ onSave, onRecords }: {
  onSave: (attempt: LocalAttempt) => Promise<void>
  onRecords: () => void
}) {
  const [index, setIndex] = useState(0)
  const [selected, setSelected] = useState<number | null>(null)
  const [attempt, setAttempt] = useState<LocalAttempt | null>(null)
  const [saveState, setSaveState] = useState<'saving' | 'saved' | 'error'>('saving')
  const inFlight = useRef(false)
  const question = sampleQuestions[index]

  async function persist(record: LocalAttempt) {
    if (inFlight.current) return
    inFlight.current = true
    setSaveState('saving')
    try { await onSave(record); setSaveState('saved') }
    catch { setSaveState('error') }
    finally { inFlight.current = false }
  }

  function submit() {
    if (selected === null || attempt || inFlight.current) return
    const submitted = { id: localRecordId(), questionId: question.id, answer: selected,
      correct: gradeAnswer(question.answer, selected), time: Date.now() }
    setAttempt(submitted)
    void persist(submitted)
  }

  function next() {
    setAttempt(null)
    setSelected(null)
    setIndex(index + 1)
  }

  return <section className="offline-page">
    <h1>本地练习</h1>
    <p className="supporting">知学伴预置示例题。答题记录存于当前浏览器。</p>
    {question ? <form className="offline-card" onSubmit={event => { event.preventDefault(); submit() }}>
      <p className="question-metadata">示例题 · {index + 1} / {sampleQuestions.length}</p>
      <h2>{question.stem}</h2>
      <fieldset className="offline-options" disabled={!!attempt}>
        <legend>选择答案</legend>
        {question.options.map((option, i) => <label key={option} className={selected === i ? 'offline-selected' : undefined}>
          <input type="radio" name="offline-answer" checked={selected === i} onChange={() => setSelected(i)} />
          <span>{option}</span>
        </label>)}
      </fieldset>
      {attempt ? <>
        <div role="status">
          <p><strong>{attempt.correct ? '回答正确。' : '回答错误。'}</strong> 正确答案是 {question.options[question.answer]}。</p>
          <p>{question.explanation}</p>
          {saveState === 'saving' && <p>正在保存作答…</p>}
          {saveState === 'saved' && <p>已保存到本地学习记录。</p>}
        </div>
        {saveState === 'error' && <div role="alert">
          <p>作答尚未保存。请检查站点存储权限或空间。</p>
          <button className="secondary-button" type="button" onClick={() => void persist(attempt)}>重试保存</button>
        </div>}
        <button className="primary-button" type="button" disabled={saveState !== 'saved'} onClick={next}>
          {index + 1 === sampleQuestions.length ? '完成练习' : '下一题'}
        </button>
      </> : <button className="primary-button" type="submit" disabled={selected === null}>提交答案</button>}
    </form> : <div className="offline-card">
      <h2>练习完成</h2>
      <button className="primary-button" onClick={onRecords}>查看学习记录</button>
      <button className="secondary-button" onClick={() => setIndex(0)}>再练一次</button>
    </div>}
  </section>
}

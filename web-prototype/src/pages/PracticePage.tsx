import { useEffect, useRef, useState } from 'react'
import { api } from '../api/generation'
import type { PracticeReport, Question } from '../api/generation'
import { Icon } from '../components/Icon'
import { QuestionEvidence } from '../components/QuestionEvidence'
import { PointProgressList } from '../components/PointProgressList'

export function PracticePage({ taskId, questions, onExit }: { taskId: string; questions: Question[]; onExit: () => void }) {
  const [sessionQuestions] = useState(questions)
  const [sessionId, setSessionId] = useState(() => crypto.randomUUID())
  const [index, setIndex] = useState(0)
  const [selected, setSelected] = useState('')
  const [answers, setAnswers] = useState<string[]>([])
  const [report, setReport] = useState<PracticeReport | null>(null)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState('')
  const heading = useRef<HTMLHeadingElement>(null)
  const question = sessionQuestions[index]
  const submitted = answers[index]

  useEffect(() => {
    heading.current?.closest('main')?.scrollTo(0, 0)
    heading.current?.focus({ preventScroll: true })
  }, [index])

  function reset() {
    setSessionId(crypto.randomUUID())
    setAnswers([])
    setReport(null)
    setSaveError('')
    setSelected('')
    setIndex(0)
  }

  async function recordPractice() {
    setSaving(true)
    setSaveError('')
    try {
      const result = await api<PracticeReport>(`/api/generation-tasks/${taskId}/practice-sessions`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sessionId, answers: sessionQuestions.map((item, position) => ({ questionId: item.id, answer: answers[position] })) }),
      })
      setReport(result)
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : '暂时无法保存练习')
    } finally { setSaving(false) }
  }

  if (!question) {
    const correct = sessionQuestions.filter((item, position) => answers[position] === item.answer).length
    return <div className="generation-page practice-page page-enter">
      <header className="generation-intro">
        <span className="handbook-tag">学习手帐</span>
        <h1 tabIndex={-1} ref={heading}>练习完成</h1>
      </header>
      <div className="practice-score"><strong>{correct} / {sessionQuestions.length}</strong><span>答对 {correct} 题，答错 {sessionQuestions.length - correct} 题</span></div>
      <section className="practice-analysis" aria-label="学习分析">
        <h2>知识点掌握情况</h2>
        {report && <PointProgressList points={report.points}/>}
        {saving && <p className="supporting" role="status">正在保存练习并更新掌握估计…</p>}
        {saveError && <div role="alert"><p className="supporting">练习记录暂未保存。{saveError}</p><button className="secondary-button" onClick={()=>void recordPractice()}>重试保存</button></div>}
      </section>
      <button className="primary-button" disabled={saving} onClick={onExit}>返回题目集<Icon name="check" size={18}/></button>
      <button className="secondary-button" disabled={saving} onClick={reset}>再练一次</button>
    </div>
  }

  return <div className="generation-page practice-page page-enter">
    <div className="practice-top"><button className="back-link" onClick={onExit}><Icon name="back" size={18}/>结束练习</button><span>第 {index + 1} / {sessionQuestions.length} 题</span></div>
    <progress aria-label="练习进度" value={index + (submitted ? 1 : 0)} max={sessionQuestions.length}/>
    <article className="generated-question practice-card">
      <p className="question-metadata">单选题</p>
      <h2 ref={heading} tabIndex={-1}>{question.prompt}</h2>
      <form onSubmit={event => {
        event.preventDefault()
        if (selected && !submitted) setAnswers(previous => [...previous, selected])
      }}>
        <fieldset className="practice-options" disabled={!!submitted}>
          <legend className="sr-only">选择一个答案</legend>
          {question.options.map((option, position) => {
            const letter = 'ABCD'[position]
            const correct = submitted && letter === question.answer
            const incorrect = submitted === letter && !correct
            return <label key={letter} className={`practice-option${correct ? ' correct' : incorrect ? ' incorrect' : selected === letter ? ' selected' : ''}`}>
              <input className="sr-only" type="radio" name="practice-option" checked={selected === letter} onChange={() => setSelected(letter)}/>
              <b>{letter}</b><span>{option}</span>{correct && <Icon name="check" size={16}/>} {incorrect && <Icon name="close" size={16}/>}
            </label>
          })}
        </fieldset>
        {submitted ? <div className="practice-feedback">
          <strong role="status">{submitted === question.answer ? '答对了' : '这题答错了'} · 正确答案 {question.answer}</strong>
          <p>{question.explanation}</p>
          {question.ai.evidenceQuote?.trim() === question.explanation.trim() && <small>解析依据：资料原文摘录</small>}
          <QuestionEvidence question={question}/>
        </div>
          : <button className="primary-button" type="submit" disabled={!selected}>提交答案<Icon name="check" size={18}/></button>}
      </form>
      {submitted && <button className="primary-button" onClick={() => {
        setSelected(''); setIndex(index + 1)
        if (index + 1 === sessionQuestions.length) void recordPractice()
      }}>{index + 1 === sessionQuestions.length ? '查看练习结果' : '下一题'}<Icon name="arrow" size={18}/></button>}
      {submitted && <div className="point-chips">{question.points.map(point => <span key={point}>{point}</span>)}</div>}
      <p className="question-source">来源：{question.ai.sourceFile} · {question.ai.sourceLocation}</p>
      {question.visualValidationLimit && <p className="visual-limit">{question.visualValidationLimit}</p>}
    </article>
  </div>
}

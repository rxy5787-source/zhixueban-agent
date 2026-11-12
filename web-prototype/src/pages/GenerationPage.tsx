import { useEffect, useState } from 'react'
import { api, ApiHttpError, isActiveTask } from '../api/generation'
import type { GenerationTask, Question } from '../api/generation'
import { Icon } from '../components/Icon'
import { PracticePage } from './PracticePage'
import { StudyResultCard } from './StudyConversation'

const STAGES = [{id:'upload',title:'上传学习资料'},{id:'parsing',title:'文件解析'},{id:'knowledge',title:'知识点提取'},{id:'generation',title:'AI生成题目'},{id:'quality',title:'自动质量初筛'},{id:'done',title:'生成完成'}]
export function GenerationPage({taskId,uploadPercent,uploadDetail,submittingExam,libraryTitle,practicing,revision,onBack,onTask,onPractice,onLibrary,onSaved,onRemoveQuestion}: {
  taskId?: string; uploadPercent: number | null; uploadDetail?: string; libraryTitle: string; practicing: boolean
  submittingExam: boolean
  revision: number; onRemoveQuestion: (question: Question, libraryName: string) => void
  onBack:()=>void; onTask:(id:string)=>void; onPractice:(active:boolean)=>void
  onLibrary:(id?:string)=>void; onSaved:()=>Promise<void>
}) {
  const [task,setTask]=useState<GenerationTask | null>(null)
  const [questions,setQuestions]=useState<Question[]>([])
  const [error,setError]=useState('')
  const [retryPoll,setRetryPoll]=useState(0)
  const [revealed,setRevealed]=useState<Set<string>>(new Set())
  const [saving,setSaving]=useState(false)
  const [retrying,setRetrying]=useState(false)
  useEffect(()=>{
    if(!taskId)return
    const controller=new AbortController();let timer:number | undefined
    setTask(null);setQuestions([]);setError('');setRevealed(new Set())
    async function poll() {
      try {
        const value=await api<GenerationTask>(`/api/generation-tasks/${taskId}`,{signal:controller.signal})
        if(controller.signal.aborted)return
        setTask(value);setError('')
        if(value.availableQuestions)setQuestions(value.availableQuestions)
        if(isActiveTask(value)) timer=window.setTimeout(poll,1800)
        else if(!value.availableQuestions) {
          const result=await api<{questions:Question[]}>(`/api/generation-tasks/${taskId}/questions`,{signal:controller.signal})
          if(!controller.signal.aborted)setQuestions(result.questions)
        }
      } catch(err) {
        if(controller.signal.aborted)return
        setError(err instanceof Error ? err.message : '查询任务失败')
        if(!(err instanceof ApiHttpError) || err.status>=500)timer=window.setTimeout(poll,4000)
      }
    }
    void poll()
    return ()=>{controller.abort();window.clearTimeout(timer)}
  },[taskId,retryPoll,revision])
  async function retry() {
    if(!taskId)return
    setRetrying(true);setError('')
    try {const result=await api<{taskId:string}>(`/api/generation-tasks/${taskId}/retry`,{method:'POST'});onTask(result.taskId)}
    catch(err){setError(err instanceof Error ? err.message : '重试失败')}
    finally{setRetrying(false)}
  }
  async function save() {
    if(!taskId)return
    setSaving(true);setError('')
    try {const result=await api<{saved:number}>(`/api/generation-tasks/${taskId}/save`,{method:'POST'});setTask(previous=>previous ? {...previous,savedQuestionCount:result.saved} : previous);await onSaved()}
    catch(err){setError(err instanceof Error ? err.message : '保存失败')}
    finally{setSaving(false)}
  }
  const running=!!task && isActiveTask(task)
  const finished=!!task && !running
  const success=task?.status==='succeeded' || task?.status==='partial'
  const exam=task?.examPractice
  const combinedKnowledge=task?.events.some(event=>event.stage.startsWith('AI生成题目（同步提取知识点）'))
  const stages=combinedKnowledge ? STAGES.filter(stage=>stage.id!=='knowledge') : STAGES
  const entered=new Set([...(task || !taskId ? ['upload'] : []),...(task?.events.map(event=>event.stageCode) ?? [])])
  const current=!taskId ? 'upload' : success ? 'done' : task?.stageCode
  const canPractice=questions.length>0
  const saved=canPractice && task?.savedQuestionCount===questions.length
  if(task?.libraryDeleted)return <div className="generation-page page-enter"><h1>知识库已移入回收站</h1><p className="page-description">恢复「{task.libraryName}」后，可以继续查看这个任务和题目。</p><button className="primary-button" onClick={()=>onLibrary()}>前往知识库<Icon name="arrow" size={18}/></button></div>
  if(task?.removedSet)return <div className="generation-page page-enter"><h1>题目集已移入回收站</h1><p className="page-description">可以在书架的回收站恢复题目集。</p><button className="primary-button" onClick={()=>onLibrary()}>前往知识库<Icon name="arrow" size={18}/></button></div>
  if(task?.study)return <div className="generation-page page-enter">
    <button className="back-link" onClick={onBack}><Icon name="back" size={18}/>回到首页</button>
    <h1>学习结果</h1><p className="page-description">{task.libraryName}</p>
    {task.study.result ? <StudyResultCard key={task.taskId} task={task} onSaved={onSaved}/> :
      <p className={task.error || error ? 'generation-error' : 'live-stage'} role="status">{error || task.error || (task.study.hidden ? '内容已移入回收站。' : task.stage)}</p>}
    {finished && !task.study.result && !task.study.hidden && <button className="secondary-button" disabled={retrying} onClick={()=>void retry()}>重试这轮任务</button>}
  </div>
  if(practicing && task && canPractice)return <PracticePage taskId={task.taskId} questions={questions} onExit={()=>onPractice(false)}/>
  const duration = task?.created ? Math.max(0, Math.round((finished ? (task.updated ?? task.created) : Date.now()/1000) - task.created)) : null
  return <div className="generation-page page-enter">
    <button className="back-link" onClick={onBack} disabled={!taskId}><Icon name="back" size={18}/>{running ? '回到首页，任务继续' : '回到首页'}</button>
    <header className="generation-intro">
      <span className="handbook-tag">学习手帐</span>
      <h1>{error && !task ? '暂时无法读取任务' : finished ? canPractice || !!task?.acceptedQuestionCount ? '本次出题结果' : '本次没有可练习的题目' : '正在准备你的练习'}</h1>
      <p className="page-description">{task?.libraryName ?? libraryTitle}{duration===null ? '' : ` · ${finished ? '用时' : '已等待'} ${exam && duration===0 ? '不到 1 秒' : `${Math.floor(duration/60)} 分 ${duration%60} 秒`}`}</p>
    </header>
    {!finished && <div className="live-stage" role="status">{!taskId ? submittingExam ? '正在生成题目与解析…' : uploadPercent===100 ? '文件已发送，正在校验与创建任务…' : `上传中${uploadPercent===null ? '…' : ` · ${uploadPercent}%（实际传输）`}` : error ? '暂时无法更新进度' : task?.stage ?? '正在查询任务…'}</div>}
    {!taskId && !submittingExam && uploadDetail && <p className="generation-counts" role="status">{uploadDetail}</p>}
    {running && <p className="generation-counts">可切换页面，之后从页头「出题任务」返回。</p>}
    {task && <p className="generation-counts">{task.acceptedQuestionCount} 道可练习 · 目标 {task.requestedQuestionCount} 道{running ? ` · 已生成 ${task.generatedQuestionCount} 道候选` : ''}</p>}
    {exam && <p className="prototype-note">原创模拟题 · {exam.label} · <a href={exam.reference} target="_blank" rel="noreferrer">考点出处</a></p>}
    {canPractice && <div className="result-actions">
      <button className="primary-button" onClick={()=>onPractice(true)}>{running ? '先练已通过的题' : '开始练习'}<Icon name="arrow" size={18}/></button>
      {success && !saved && <button className="secondary-button" disabled={saving} onClick={()=>void save()}>{saving ? '保存中…' : '保存到知识库'}</button>}
      {saved && task && <button className="secondary-button" onClick={()=>onLibrary(task.libraryId)}>已归档到「{task.libraryName}」<Icon name="chevron" size={14}/></button>}
    </div>}
    {task?.status==='partial' && canPractice && <p className="generation-counts">本次只放行达到初筛标准的题目。</p>}
    {!!task?.filteredQuestionCount && <p className="prototype-note">历史结果中有 {task.filteredQuestionCount} 道题缺少独立题意或可验证的条件，已从练习中排除。</p>}
    {!!task?.removedQuestionCount && <p className="prototype-note">{task.removedQuestionCount} 道题已移入回收站。</p>}
    {(error || task?.error) && <div className="generation-error" role="alert"><strong>处理提示</strong><p>{error || task?.error}</p>{error && <button className="secondary-button" onClick={()=>setRetryPoll(value=>value+1)}>重新查询</button>}</div>}
    {finished && !canPractice && !task?.acceptedQuestionCount && !task?.removedQuestionCount && <button className="primary-button" disabled={retrying} onClick={()=>void retry()}>{retrying ? '提交重试中…' : '重试这次任务'}<Icon name="arrow" size={18}/></button>}
    {canPractice && <section className="generated-questions" aria-label={exam ? '计算专项题目' : '初筛通过的题目'}><div className="result-heading"><h2>题目预览</h2><span>{questions.length} 题</span></div>{questions.map((question,index)=><article className="generated-question" key={question.id}>
      <div className="question-metadata"><span>第 {index+1} 题 · 单选</span><span>{['','基础','中等','提高'][question.difficulty] ?? '未标注'}</span></div><h3>{question.prompt}</h3>
      <ol className="generated-options">{question.options.map((option,optionIndex)=><li key={optionIndex}><b>{'ABCD'[optionIndex]}</b><span>{option}</span></li>)}</ol>
      <div className="point-chips">{question.points.map(point=><span key={point}>{point}</span>)}</div>
      <button className="answer-toggle" aria-expanded={revealed.has(question.id)} onClick={()=>setRevealed(previous=>{const next=new Set(previous);next.has(question.id) ? next.delete(question.id) : next.add(question.id);return next})}>{revealed.has(question.id) ? '收起答案与解析' : '查看答案与解析'}<Icon name="chevron" size={14}/></button>
      {revealed.has(question.id) && <div className="real-explanation"><strong>正确答案：{question.answer}</strong><p>{question.explanation}</p><small>{exam ? '解析依据：题干条件与程序计算' : '解析依据：资料原文摘录'}</small></div>}
      <p className="question-source">来源：{question.ai.sourceFile} · {question.ai.sourceLocation}</p>{question.visualValidationLimit && <p className="visual-limit">{question.visualValidationLimit}</p>}
      {saved && task && <button className="archive-link remove-link" aria-label={`移除第 ${index+1} 题`} onClick={()=>onRemoveQuestion(question,task.libraryName)}>移除本题</button>}
    </article>)}</section>}
    {!exam && (taskId || !submittingExam) && <details className="rejection-details"><summary>查看出题步骤{taskId ? ` · ${taskId.slice(0,8)}` : ''}</summary>
      <ol className="real-progress" aria-label="真实任务处理阶段">{stages.map(stage=><li key={stage.id} className={current===stage.id ? 'current' : entered.has(stage.id) ? 'entered' : ''}><span>{current===stage.id && !finished ? <i className="activity-dot"/> : entered.has(stage.id) || (stage.id==='done' && success) ? <Icon name="check" size={13}/> : <i/>}</span><strong>{combinedKnowledge && stage.id==='generation' ? 'AI 出题与提取知识点' : stage.title}</strong><small>{current===stage.id ? success ? '完成' : finished ? '已结束' : '处理中' : entered.has(stage.id) ? '已进入' : '未开始'}</small></li>)}</ol>
    </details>}
    {(task?.rejected.length ?? 0)>0 && <details className="rejection-details"><summary>查看未通过与验证限制（{task!.rejected.length} 项）</summary>{task!.rejected.map((row,index)=><p key={index}>{row.sourceFile}：{row.reasons?.join('；') ?? row.status}</p>)}</details>}
    <p className="generation-footnote">{exam ? task?.reviewNote : `自动初筛包含结构、去重、独立解答、原文证据和解析一致性检查。${task?.reviewNote ?? ''}`}</p>
  </div>
}

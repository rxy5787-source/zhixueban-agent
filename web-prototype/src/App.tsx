import { useCallback, useEffect, useState } from 'react'
import type { CSSProperties } from 'react'
import { onlineTrial } from './deployment'
import { DESTINATIONS, LIBRARY_SEEDS } from './data/demo'
import type { Destination, Library, LibraryDocument } from './data/demo'
import { api, clearPendingSubmission, isActiveTask, submitTask } from './api/generation'
import type { DeletedLibrary, LibraryItem, PracticeHistory, StoredLibrary } from './api/generation'
import { readGenerationRequest } from './api/generationRequest'
import { useTaskHistory } from './api/useTaskHistory'
import { GenerationPage } from './pages/GenerationPage'
import { Icon } from './components/Icon'
import { PointProgressList } from './components/PointProgressList'
import { Sheet } from './components/Sheet'
import { HomePage } from './pages/HomePage'
import { ProfilePage } from './pages/ProfilePage'
import { loadProfileSettings, preferredRequirements, saveProfileSettings } from './api/profileSettings'
import type { ProfileSettings } from './api/profileSettings'
import type { SelectedFile } from './pages/HomePage'
import { continueStudy, readStudyThread, storeStudyThread, studyIntent } from './api/study'
import type { StudyTurn } from './api/study'
import { BookshelfPage, FileBadge, LibraryDetailPage } from './pages/LibraryPage'
import handbookStatus from './assets/handbook/status.svg'
import handbookBook from './assets/handbook/brand-book.svg'
import handbookClock from './assets/handbook/clock.svg'

type Route = { destination: Destination; libraryId?: string; taskId?: string; practicing?: boolean }
const UPLOAD_DRAFT_KEY = 'zhixue-upload-draft'
function uploadDraft(): { libraryId: string; requirements: string } | null {
  try {
    const value = JSON.parse(localStorage.getItem(UPLOAD_DRAFT_KEY) ?? sessionStorage.getItem(UPLOAD_DRAFT_KEY) ?? 'null')
    if (typeof value?.libraryId === 'string' && typeof value?.requirements === 'string') return value
  } catch { /* A disabled browser store still allows an in-page upload. */ }
  return null
}
const BASE_LIBRARIES: Library[] = LIBRARY_SEEDS.map(library=>({...library,documents:[],points:[],records:[],question:{stem:'',options:[]}}))
const TASK_KEY='zhixue-last-generation-task'
const TASK_STATUS: Record<string,string> = { queued:'排队中', running:'生成中', succeeded:'已完成', partial:'部分完成', failed:'未完成', interrupted:'服务中断', cancelled:'已取消' }
const ITEM_LABEL = {source:'原始资料',set:'题目集',question:'单题',task:'任务记录',study:'学习内容'}
const REMOVE_NOTE = {
  source:'这份资料会从知识库目录移出，已有题目可继续练习。',
  set:'整个题目集会从知识库移出，恢复后可以继续练习。',
  question:'这道题会从题目集和练习中移出，其他题目可以继续使用。',
  task:'该记录会从「出题任务」移出，已保存的题目仍可从知识库打开。',
  study:'这份学习内容会移入回收站，恢复后可以继续查看。',
}
function previousTask(){try{return localStorage.getItem(TASK_KEY) ?? ''}catch{return ''}}
type Panel = { type: 'demo' | 'target' | 'create' | 'overview' | 'settings' | 'tasks' | 'trash' }
  | { type: 'delete' | 'rename'; libraryId: string }
  | { type: 'item-remove' | 'task-cancel'; item: LibraryItem }
  | { type: 'document'; libraryId: string; documentId: string }
  | { type: 'records' | 'analysis'; libraryId?: string }
  | null
function readRoute(): Route {
  const [path, id, mode] = window.location.hash.slice(1).split('/')
  if (path === 'libraries') { try { return { destination: 'libraries', libraryId: id ? decodeURIComponent(id) : undefined } } catch { return { destination: 'libraries' } } }
  if (path === 'home' && id && /^[a-f0-9]{32}$/.test(id)) return {destination:'home',taskId:id,practicing:mode==='practice'}
  if (path === 'profile' || path === 'reports') return { destination: 'profile' }
  return { destination: 'home' }
}

export function App() {
  const [route, setRoute] = useState<Route>(readRoute)
  const [width, setWidth] = useState('393')
  const [profile, setProfile] = useState(loadProfileSettings)
  function changeProfile(value: ProfileSettings) {
    try { saveProfileSettings(value); setProfile(value); return true } catch { return false }
  }
  const [libraries, setLibraries] = useState<Library[]>(BASE_LIBRARIES)
  const [deletedLibraries, setDeletedLibraries] = useState<DeletedLibrary[]>([])
  const [removedItems, setRemovedItems] = useState<LibraryItem[]>([])
  const [contentRevision,setContentRevision] = useState(0)
  const [libraryMutation, setLibraryMutation] = useState('')
  const [libraryError, setLibraryError] = useState('')
  const [studyEnabled, setStudyEnabled] = useState(false)
  const [studyTurns, setStudyTurns] = useState(readStudyThread)
  const [targetId, setTargetId] = useState(()=>uploadDraft()?.libraryId ?? readStudyThread().at(-1)?.libraryId ?? 'sql')
  useEffect(() => {
    const controller = new AbortController()
    api<{ studyChat: boolean }>('/api/study-capabilities', { signal: controller.signal })
      .then(value => { if (!controller.signal.aborted) setStudyEnabled(value.studyChat) })
      .catch(() => {})
    return () => controller.abort()
  }, [])
  useEffect(() => { storeStudyThread(studyTurns) }, [studyTurns])
  const [files, setFiles] = useState<SelectedFile[]>([])
  const [requirement, setRequirement] = useState(()=>uploadDraft()?.requirements ?? '')
  const [feedback, setFeedback] = useState(()=>uploadDraft() ? '发现未完成的上传，请重新选择原文件后继续。' : '')
  const [submitting,setSubmitting]=useState<'material' | 'exam' | null>(null)
  const [uploadPercent,setUploadPercent]=useState<number|null>(null)
  const [uploadDetail,setUploadDetail]=useState('')
  const [recentTask,setRecentTask]=useState(previousTask)
  const { tasks, loaded:tasksLoaded, error:taskHistoryError, refresh:refreshTasks } = useTaskHistory()
  const refreshLibraries=useCallback(async()=>{
    const data=await api<{libraries:StoredLibrary[];deletedLibraries?:DeletedLibrary[];removedItems?:LibraryItem[]}>('/api/libraries')
    const deleted=data.deletedLibraries ?? []
    const deletedIds=new Set(deleted.map(library=>library.id))
    const result=BASE_LIBRARIES.filter(library=>!deletedIds.has(library.id))
    for(const stored of data.libraries){
      const base=BASE_LIBRARIES.find(item=>item.id===stored.id) ?? {id:stored.id,title:stored.title,subtitle:'自定义学习主题',mark:Array.from(stored.title).slice(0,2).join(''),color:'mint' as const,updated:onlineTrial ? '试用知识库' : '本机知识库',documents:[],points:[],records:[],question:{stem:'',options:[]}}
      const sourceDocs:LibraryDocument[]=stored.sources.map(source=>({id:source.id,title:source.name,format:source.name.toLowerCase().endsWith('.docx')?'DOCX':source.name.toLowerCase().endsWith('.pdf')?'PDF':source.name.toLowerCase().endsWith('.txt')?'TXT':'JPG',kind:'source',description:`真实上传 · ${Math.max(1,Math.round(source.size/1024))} KB`}))
      const sets:LibraryDocument[]=stored.questionSets.map(set=>({id:set.id,taskId:set.taskId,title:`${set.examPractice ? '软考专项题目集' : 'AI 题目集'} · ${set.count} 道`,format:'QSET',kind:'questions',description:'打开题目集开始练习'}))
      const studyDocs: LibraryDocument[] = (stored.studyResults ?? []).map(item => ({
        id: item.taskId, taskId: item.taskId, title: item.title, study: true,
        format: item.kind === 'cloze' ? 'QSET' : 'NOTE', kind: item.kind === 'cloze' ? 'questions' : 'knowledge',
        description: item.kind === 'cloze' ? '填空练习' : item.kind === 'mnemonic' ? '记忆口诀' : '资料解答',
      }))
      const library:Library={...base,title:stored.title,points:stored.points,updated:sets.length?'已有可练习的题目':stored.sources.length?'已上传学习资料':'等待学习资料',documents:[...studyDocs,...sets,...sourceDocs]}
      const index=result.findIndex(item=>item.id===stored.id)
      if(index<0)result.push(library);else result[index]=library
    }
    setLibraries(result)
    setDeletedLibraries(deleted)
    setRemovedItems(data.removedItems ?? [])
  },[])
  const completedTasks=tasks.filter(task=>task.status==='succeeded' || task.status==='partial').map(task=>task.taskId).sort().join(',')
  const libraryTaskVersion=route.destination==='libraries' ? completedTasks : ''
  useEffect(()=>{
    void refreshLibraries().catch(()=>{/* Submission shows a recoverable connection error. */})
  },[refreshLibraries,route.destination,libraryTaskVersion])
  const [newName, setNewName] = useState('')
  const [nameError, setNameError] = useState('')
  const [notice, setNotice] = useState('')
  const [panel, setPanel] = useState<Panel>(null)
  const [practiceHistory, setPracticeHistory] = useState<{path:string; data?:PracticeHistory; error?:string} | null>(null)
  const historyPath=panel?.type==='analysis' || panel?.type==='records'
    ? `/api/practice-history${panel.libraryId ? `?libraryId=${encodeURIComponent(panel.libraryId)}` : ''}` : ''
  const currentHistory=practiceHistory?.path===historyPath ? practiceHistory : null
  useEffect(()=>{
    if(!historyPath){setPracticeHistory(null);return}
    const controller=new AbortController()
    api<PracticeHistory>(historyPath,{signal:controller.signal}).then(data=>{
      if(!controller.signal.aborted)setPracticeHistory({path:historyPath,data})
    }).catch(error=>{
      if(!controller.signal.aborted)setPracticeHistory({path:historyPath,error:error instanceof Error ? error.message : '暂时无法读取练习记录'})
    })
    return ()=>controller.abort()
  },[historyPath])
  const close = useCallback(() => setPanel(null), [])
  useEffect(() => {
    function sync() {
      const oldHash = window.location.hash
      setRoute(readRoute())
      if (oldHash === '#home/exam') {
        setRequirement(previous => previous || '生成 5 道软考综合计算题')
        window.history.replaceState(null, '', '#home')
      }
      setPanel(oldHash === '#reports' ? { type: 'overview' } : null)
      if (oldHash === '#today' || oldHash === '#reports') window.history.replaceState(null, '', oldHash === '#today' ? '#home' : '#profile')
    }
    sync()
    window.addEventListener('hashchange', sync)
    return () => window.removeEventListener('hashchange', sync)
  }, [])
  useEffect(() => { if (!notice) return; const timer = window.setTimeout(() => setNotice(''), 3200); return () => window.clearTimeout(timer) }, [notice])

  function navigate(destination: Destination, libraryId?: string) {
    setPanel(null)
    setRoute({ destination, libraryId })
    window.location.hash = `${destination}${libraryId ? `/${encodeURIComponent(libraryId)}` : ''}`
  }

  function prepareWeakPointReview(libraryId: string) {
    navigate('home')
    if (submitting || files.length || requirement.trim() || uploadDraft()) {
      setNotice('已保留首页的出题草稿。处理后再从学习分析开始薄弱点练习。')
      return
    }
    setTargetId(libraryId)
    setRequirement('根据资料优先生成本知识库的薄弱知识点练习')
    setFeedback('')
    setNotice('请添加相关学习资料，再点击出题。')
  }
  function resetDemo() {
    setFiles([]); setRequirement(''); setFeedback(''); setNewName(''); setNameError('')
    clearPendingSubmission()
    try { localStorage.removeItem(UPLOAD_DRAFT_KEY); sessionStorage.removeItem(UPLOAD_DRAFT_KEY) } catch { /* Draft state is already cleared in memory. */ }
    navigate('home'); setNotice('出题草稿已清空，已保存题库保留')
  }

  function newStudyThread() {
    if (submitting) return
    setStudyTurns([])
    resetDemo()
  }
  function selectFiles(selected: File[]) {
    if (!selected.length) return
    const next = [...files]
    let rejected = 0
    for (const file of selected) {
      if (!/\.(docx|pdf|png|jpe?g|webp|bmp|txt)$/i.test(file.name) || file.size === 0 || file.size > 20 * 1024 * 1024) { rejected++; continue }
      const id = `${file.name}:${file.size}:${file.lastModified}`
      if (next.some(item => item.id === id)) continue
      if(next.length>=5){rejected++;continue}
      next.push({ id, name: file.name, file })
    }
    setFiles(next)
    setFeedback(rejected ? '部分文件未添加。请选择非空的 DOCX、PDF、图片或 TXT，最多 5 份，每份不超过 20 MB。旧 DOC 请另存为 DOCX。' : '')
  }
  async function saveLibraryName() {
    const title = newName.trim()
    const existing = panel?.type==='rename' ? panel.libraryId : undefined
    if (!title) { setNameError('请先填写知识库名称'); return }
    if (libraries.some(library => library.id!==existing && library.title.toLowerCase() === title.toLowerCase())) { setNameError('这个名称已在书架中，请换一个名称'); return }
    const id = existing ?? `local-${crypto.randomUUID()}`
    setLibraryMutation(id)
    try {
      await api(`/api/libraries/${id}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({title})})
      if(existing)setLibraries(previous=>previous.map(library=>library.id===id ? {...library,title} : library))
      else setTargetId(id)
      setNewName('');setNameError('');navigate('libraries',id);setNotice(existing ? '知识库已改名' : onlineTrial ? '知识库已保存' : '知识库已保存到本机')
      refreshTasks()
      await refreshLibraries().catch(()=>setNotice('已保存，可刷新页面查看最新书架。'))
    }catch(error){setNameError(error instanceof Error?error.message:'保存知识库名称失败')}
    finally{setLibraryMutation('')}
  }
  async function changeLibraryArchive(id:string, title:string, restore:boolean) {
    if(libraryMutation)return
    setLibraryMutation(id);setLibraryError('')
    try {
      await api(`/api/libraries/${id}${restore ? '/restore' : ''}`,{method:restore ? 'POST' : 'DELETE'})
      if(restore) {
        setDeletedLibraries(previous=>previous.filter(library=>library.id!==id))
        setNotice(`已恢复「${title}」`)
      }else{
        setLibraries(previous=>previous.filter(library=>library.id!==id))
        setDeletedLibraries(previous=>[{id,title},...previous.filter(library=>library.id!==id)])
        setTargetId(previous=>previous===id ? '' : previous)
        navigate('libraries')
        setNotice(`「${title}」已移入回收站`)
      }
      refreshTasks()
      await refreshLibraries().catch(()=>setNotice('操作已完成。可刷新页面查看最新书架。'))
    }catch(error){setLibraryError(error instanceof Error ? error.message : '知识库操作失败，请重试')}
    finally{setLibraryMutation('')}
  }
  function manageItem(item: LibraryItem, cancelTask = false) {
    setLibraryError('')
    setPanel({type:cancelTask ? 'task-cancel' : 'item-remove',item})
  }
  async function changeItemArchive(item: LibraryItem, restore: boolean) {
    if(libraryMutation)return
    setLibraryMutation(item.id);setLibraryError('')
    try {
      const path=`/api/libraries/${encodeURIComponent(item.libraryId)}/items/${item.kind}/${encodeURIComponent(item.id)}`
      await api(`${path}${restore ? '/restore' : ''}`,{method:restore ? 'POST' : 'DELETE'})
      if(!restore)close()
      setNotice(restore ? '内容已恢复' : '已移入回收站')
      setContentRevision(value=>value+1)
      refreshTasks()
      await refreshLibraries().catch(()=>setNotice('操作已完成，可刷新页面查看最新内容。'))
    }catch(error){setLibraryError(error instanceof Error ? error.message : '操作失败，请重试')}
    finally{setLibraryMutation('')}
  }
  async function cancelGeneration(item: LibraryItem) {
    if(libraryMutation)return
    setLibraryMutation(item.id);setLibraryError('')
    try {
      await api(`/api/generation-tasks/${item.id}/cancel`,{method:'POST'})
      close();refreshTasks();setContentRevision(value=>value+1);setNotice('已提交取消请求')
    }catch(error){setLibraryError(error instanceof Error ? error.message : '取消失败，请重试')}
    finally{setLibraryMutation('')}
  }
  function rememberTask(id:string){
    setRecentTask(id);try{localStorage.setItem(TASK_KEY,id)}catch{/* Task remains addressable by URL. */}
  }
  function openTask(id:string, practice = false){
    rememberTask(id)
    refreshTasks()
    setPanel(null);setRoute({destination:'home',taskId:id,practicing:practice});window.location.hash=`home/${id}${practice ? '/practice' : ''}`
  }
  function openTasks() {
    refreshTasks()
    setPanel({ type: 'tasks' })
  }

  async function retryStudyTurn(id: string) {
    const result = await api<{ taskId: string }>(`/api/generation-tasks/${id}/retry`, { method: 'POST' })
    setStudyTurns(previous => previous.map(turn => turn.id === id ? { ...turn, id: result.taskId } : turn))
    rememberTask(result.taskId)
    refreshTasks()
  }
  function togglePractice(active:boolean){
    if(!route.taskId)return
    setRoute({...route,practicing:active})
    const hash=`home/${route.taskId}${active ? '/practice' : ''}`
    if(active)window.location.hash=hash
    else window.history.replaceState(null,'',`#${hash}`)
  }
  async function generate(){
    if (submitting || (!files.length && !requirement.trim())) return
    if(!target){setPanel({type:'target'});return}
    const message = requirement.trim() || '根据资料生成选择题'
    const parent = studyEnabled && !files.length && studyTurns.at(-1)?.libraryId === target.id ? studyTurns.at(-1) : undefined
    const inStudy = studyEnabled && (!!files.length || !!parent)
    const intent = studyIntent(message, parent?.kind)
    const studyKind = inStudy ? intent : 'single_choice'
    if ((intent === 'mnemonic' || intent === 'cloze') && !inStudy) {
      setFeedback(studyEnabled ? '请先添加资料，再生成口诀或填空。' : '当前服务尚未接入口诀和填空，请打开新版学习对话预览。')
      return
    }
    const request = readGenerationRequest(message, !!files.length || !!parent, profile.questionCount || undefined)
    if ('error' in request) {
      setFeedback(request.error)
      return
    }
    const library = { libraryId: target.id, libraryName: target.title }
    if (onlineTrial && request.kind === 'material' && files.length) {
      try { localStorage.setItem(UPLOAD_DRAFT_KEY, JSON.stringify({ libraryId: library.libraryId, requirements: requirement })) }
      catch { /* The selected files can still be uploaded in this page. */ }
    }
    setSubmitting(request.kind)
    setUploadPercent(null)
    setUploadDetail('')
    setFeedback('')
    navigate('home')
    try{
      let weakPoints: string[] = []
      if (request.kind === 'material' && studyKind === 'single_choice' && (profile.weakFirst || /薄弱/.test(requirement))) {
        setUploadDetail('正在读取所选知识库的学习情况…')
        const progress = await api<PracticeHistory>(`/api/practice-history?libraryId=${encodeURIComponent(library.libraryId)}`)
        weakPoints = progress.points.filter(point=>point.reviewPriority).sort((a,b)=>a.mastery-b.mastery).map(point=>point.point)
      }
      const generationRequirements = studyKind === 'single_choice' ? preferredRequirements(requirement, profile, weakPoints) : message
      const result = request.kind === 'exam' 
        ? await api<{ taskId: string }>('/api/exam-practice-tasks', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ ...library, topic: request.topic, questionCount: request.questionCount }),
        })
        : parent
          ? await continueStudy(parent.id, generationRequirements || message, studyKind, request.questionCount)
          : await submitTask(files.map(file => file.file), {
            ...library, requirements: generationRequirements, questionCount: String(request.questionCount), questionType: studyKind,
          }, setUploadPercent, setUploadDetail)
      setFiles([])
      setRequirement('')
      try { localStorage.removeItem(UPLOAD_DRAFT_KEY); sessionStorage.removeItem(UPLOAD_DRAFT_KEY) } catch { /* The task has its own saved entry. */ }
      if (inStudy && request.kind === 'material') {
        const turn: StudyTurn = { id: result.taskId, requirement: message, kind: studyKind, ...library,
          sources: parent?.sources ?? files.map(file => file.name) }
        setStudyTurns(previous => [...previous.filter(item => item.id !== turn.id), turn].slice(-12))
        rememberTask(result.taskId)
        refreshTasks()
        if (window.location.hash !== '#home') setNotice('已提交学习任务，可回首页查看这轮对话。')
      }
      else if(window.location.hash==='#home') openTask(result.taskId)
      else {rememberTask(result.taskId);refreshTasks();setNotice('出题任务已提交，可从「出题任务」查看进度。')}
    }catch(error){
      const message=error instanceof Error ? error.message : '提交生成任务失败，请重试'
      setFeedback(message)
      if(window.location.hash!=='#home')setNotice('出题任务未提交成功，请回首页查看原因。')
    }
    finally{setSubmitting(null)}
  }

  const target = libraries.find(library => library.id === targetId) ?? libraries[0]
  const activeTaskCount=tasks.filter(isActiveTask).length
  const latest=tasks[0]?.taskId ?? (tasksLoaded ? '' : recentTask)
  const activeLibrary = libraries.find(library => library.id === route.libraryId)
  const panelLibrary = panel && 'libraryId' in panel ? libraries.find(library => library.id === panel.libraryId) : undefined
  const document = panel?.type === 'document' ? panelLibrary?.documents.find(item => item.id === panel.documentId) : undefined
  const title = panel?.type === 'item-remove' ? `移除${ITEM_LABEL[panel.item.kind]}` : panel?.type === 'task-cancel' ? '取消生成任务' : panel?.type === 'rename' ? '知识库改名' : panel?.type === 'tasks' ? '出题任务' : panel?.type === 'delete' ? '删除知识库' : panel?.type === 'trash' ? '回收站' : panel?.type === 'demo' ? (onlineTrial ? '关于在线试用' : '关于这份原型') : panel?.type === 'target' ? '选择归档知识库' : panel?.type === 'create' ? '新建知识库' : panel?.type === 'document' ? document?.title ?? '文档示例' : panel?.type === 'analysis' ? '学习分析' : panel?.type === 'records' ? '学习记录' : panel?.type === 'overview' ? '总体学习分析' : '应用设置'

  return <div className="workbench" style={{ '--preview-width': `${width}px` } as CSSProperties}>
    <header className="preview-toolbar"><div className="preview-identity"><img src="/favicon.svg" width="32" height="32" alt=""/><div><strong>知学伴</strong><span>上传资料 → 生成练习 → 归档学习</span></div></div><div className="preview-tools"><select aria-label="预览宽度" value={width} onChange={event => setWidth(event.target.value)}><option value="393">393 × 852 基准</option><option value="360">360 紧凑屏</option><option value="320">320 窄屏检查</option></select><button className="reset-button" onClick={resetDemo}>清空草稿</button></div></header>
    <div className="phone-frame"><div className="mobile-app mobile-app--handbook">
      <div className="app-content" inert={panel !== null} aria-hidden={panel ? true : undefined}>
        <div className="status-bar" aria-hidden="true">
          <span>09:41</span>
          <img src={handbookStatus} width="54" height="14" alt=""/>
        </div>
        <header className="app-header">
          <button type="button" className="app-brand" aria-label={onlineTrial ? '知学伴 · 关于在线出题' : '知学伴 · 关于本机出题'} onClick={() => setPanel({ type: 'demo' })}>
            <span className="handbook-brand-mark"><img src={handbookBook} width="23" height="23" alt=""/></span><strong>知学伴</strong>
          </button>
          <div className="header-actions">
            {!route.practicing && <button className="task-entry" onClick={openTasks}>
              <img src={handbookClock} width="17" height="17" alt=""/>
              出题任务{(activeTaskCount>0 || submitting) && <span>{activeTaskCount || '提交中'}</span>}
            </button>}
          </div>
        </header>
        <main className="page-scroll" key={`${route.destination}/${route.libraryId ?? route.taskId ?? ''}`}>
          {route.destination === 'home' && (route.taskId || (submitting && (!studyEnabled || submitting === 'exam')) ? (
            <GenerationPage taskId={route.taskId} uploadPercent={uploadPercent} uploadDetail={uploadDetail} submittingExam={submitting === 'exam'}
              libraryTitle={target?.title ?? ''} practicing={!!route.practicing} revision={contentRevision}
              onBack={() => navigate('home')} onTask={openTask} onPractice={togglePractice}
              onLibrary={id => navigate('libraries',id)} onSaved={refreshLibraries}
              onRemoveQuestion={(question,libraryName)=>manageItem({kind:'question',id:question.id,label:question.prompt,libraryId:question.libraryId,libraryName})}/>
          ) : (
            <HomePage files={files} requirement={requirement} libraryTitle={target?.title ?? '选择知识库'} feedback={feedback}
              studyEnabled={studyEnabled} turns={studyTurns} contextTurn={studyTurns.at(-1)?.libraryId === target?.id ? studyTurns.at(-1) : undefined}
              submitting={!!submitting} uploadPercent={uploadPercent} uploadDetail={uploadDetail} revision={contentRevision}
              onNewThread={newStudyThread} onOpenTask={openTask} onRetry={retryStudyTurn} onSaved={refreshLibraries}
              onFiles={selectFiles} onRemove={id=>{setFiles(previous=>previous.filter(file=>file.id!==id));setFeedback('')}}
              onRequirement={value => { setRequirement(value); setFeedback('') }} onTarget={()=>setPanel({type:'target'})} onGenerate={()=>void generate()}
              onRecent={() => latest ? openTask(latest) : openTasks()}/>
          ))}
          {route.destination === 'libraries' && (!route.libraryId ? <BookshelfPage libraries={libraries} deletedCount={deletedLibraries.length+removedItems.length} onTrash={()=>{setLibraryError('');setPanel({type:'trash'})}} onOpen={id => navigate('libraries', id)} onCreate={() => { setNameError('');setNewName('');setPanel({ type: 'create' }) }}/> : activeLibrary ? <LibraryDetailPage library={activeLibrary} onDelete={()=>{setLibraryError('');setPanel({type:'delete',libraryId:activeLibrary.id})}} onRename={()=>{setNameError('');setNewName(activeLibrary.title);setPanel({type:'rename',libraryId:activeLibrary.id})}} onRemoveItem={item=>manageItem({kind:item.study ? 'study' : item.taskId ? 'set' : 'source',id:item.taskId ?? item.id,label:item.title,libraryId:activeLibrary.id,libraryName:activeLibrary.title})} onBack={() => navigate('libraries')} onDocument={item => item.taskId ? openTask(item.taskId) : setPanel({ type: 'document', libraryId: activeLibrary.id, documentId: item.id })} onCompose={() => { setTargetId(activeLibrary.id); navigate('home') }} onRecords={() => setPanel({ type: 'records', libraryId: activeLibrary.id })} onAnalysis={() => setPanel({ type: 'analysis', libraryId: activeLibrary.id })}/> : <div className="empty-state"><h1>暂未找到这个知识库</h1><p>若已删除，可以回到书架，在回收站恢复。</p><button className="primary-button" onClick={() => navigate('libraries')}>回到书架<Icon name="arrow" size={18}/></button></div>)}
          {route.destination === 'profile' && <ProfilePage settings={profile} libraries={libraries}
            onSave={changeProfile} onRecords={()=>setPanel({type:'records'})} onSettings={()=>setPanel({type:'settings'})}
            onOpenTask={openTask} onLibrary={id=>navigate('libraries',id)} onReview={prepareWeakPointReview}/>}
        </main>
        {!route.practicing && <nav className="bottom-nav" aria-label="主导航">{DESTINATIONS.map(item => (
          <button key={item.id} data-destination={item.id} aria-current={route.destination === item.id ? 'page' : undefined} onClick={() => navigate(item.id)}>
            <span className="nav-icon">
              <span className="handbook-nav-glyph" aria-hidden="true"/>
            </span>
            <span>{item.title}</span>
          </button>
        ))}</nav>}
      </div>
      {notice && <div className="toast" role="status">{notice}</div>}
      {panel && <Sheet title={title} onClose={close}>
        {(panel.type==='target' || panel.type==='create') && <span className="small-tag">{onlineTrial ? '试用知识库 · 持久化存储' : '本机知识库 · 持久化存储'}</span>}
        {panel.type==='tasks' && <><p className="sheet-description">{onlineTrial ? '资料上传完成并创建任务后，出题会在后台继续。上传中断时，返回页面可继续接收。点任务查看进度或题目。' : '提交后可切换页面，任务会在本机后台继续。点任务查看进度或题目。'}</p>
          {submitting && <p className="supporting" role="status">正在提交出题任务，完成后会显示在这里。</p>}
          {taskHistoryError && <p className="field-error" role="alert">暂时无法刷新任务。{taskHistoryError}</p>}
          {tasks.length ? <div className="management-list">{tasks.map(task=>{
            const active=isActiveTask(task)
            return <div className="row-with-action" key={task.taskId}><button className="task-row" onClick={()=>openTask(task.taskId)}>
              <Icon name={active ? 'clock' : 'file'} size={18}/><span><strong>{task.libraryName}</strong><small>{active ? task.stage : new Date(task.created*1000).toLocaleString('zh-CN',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'})}</small></span><b className={active ? 'task-active' : ''}>{TASK_STATUS[task.status] ?? task.status}</b><Icon name="chevron" size={14}/>
            </button><button className="archive-link remove-link" aria-label={`${active ? '取消' : '移除'} ${task.libraryName}的任务 ${task.taskId.slice(0,8)}`} onClick={()=>manageItem({kind:'task',id:task.taskId,label:`${task.libraryName} · ${task.taskId.slice(0,8)}`,libraryId:task.libraryId,libraryName:task.libraryName},active)}>{active ? '取消' : '移除'}</button></div>
          })}</div> : !taskHistoryError && <p className="supporting">{tasksLoaded ? '还没有出题任务。' : '正在读取任务…'}</p>}
        </>}
        {(panel.type==='item-remove' || panel.type==='task-cancel') && <><p className="sheet-description">「{panel.item.label}」</p><p className="supporting">{panel.type==='task-cancel' ? '停止剩余生成，已经处理的结果会保留。' : REMOVE_NOTE[panel.item.kind]}</p>
          {libraryError && <p className="field-error" role="alert">{libraryError}</p>}
          <div className="archive-actions"><button className="secondary-button" onClick={()=>panel.item.kind==='task' ? setPanel({type:'tasks'}) : close()}>返回</button><button className="danger-button" disabled={!!libraryMutation} onClick={()=>void (panel.type==='task-cancel' ? cancelGeneration(panel.item) : changeItemArchive(panel.item,false))}>{libraryMutation ? '正在处理…' : panel.type==='task-cancel' ? '确认取消' : '移入回收站'}</button></div>
        </>}
        {panel.type==='delete' && panelLibrary && <><p className="sheet-description">将「{panelLibrary.title}」移入回收站？它会从书架和出题归档列表移除，可以连同资料与题目集一起恢复。</p>
          {libraryError && <p className="field-error" role="alert">{libraryError}</p>}
          <div className="archive-actions"><button className="secondary-button" onClick={close}>取消</button><button className="danger-button" disabled={!!libraryMutation} onClick={()=>void changeLibraryArchive(panelLibrary.id,panelLibrary.title,false)}>{libraryMutation ? '正在移入…' : '移入回收站'}</button></div>
        </>}
        {panel.type==='trash' && <><p className="sheet-description">恢复后，内容会回到原来的位置。</p>
          {libraryError && <p className="field-error" role="alert">{libraryError}</p>}
          {deletedLibraries.length || removedItems.length ? <div className="management-list">
            {deletedLibraries.map(library=><div className="trash-row" key={library.id}><span>{library.title}<small>知识库</small></span><button className="secondary-button" aria-label={`恢复 ${library.title}`} disabled={!!libraryMutation} onClick={()=>void changeLibraryArchive(library.id,library.title,true)}>{libraryMutation===library.id ? '恢复中…' : '恢复'}</button></div>)}
            {removedItems.map(item=><div className="trash-row" key={`${item.libraryId}/${item.kind}/${item.id}`}><span>{item.label}<small>{ITEM_LABEL[item.kind]} · {item.libraryName}</small></span><button className="secondary-button" aria-label={`恢复 ${item.label}`} disabled={!!libraryMutation} onClick={()=>void changeItemArchive(item,true)}>{libraryMutation===item.id ? '恢复中…' : '恢复'}</button></div>)}
          </div> : <p className="supporting">回收站为空。</p>}
        </>}
        {panel.type === 'demo' && <><p className="sheet-description">添加资料后，千问会按提取的内容和出题要求生成题目。也可以直接写“生成 3 道软考补码题”。</p><ul className="demo-notes">{onlineTrial && <li>上传资料和学习记录保存在服务器，使用当前浏览器访问。请用非敏感资料试用。</li>}<li>每次支持 1–12 道单选题。按资料出题默认 3 道，直接输入计算题要求默认 5 道。</li><li>扫描件和图片优先提取文字。图表、公式或依赖原图才能作答的内容需要人工核对。</li><li>通过初筛即可开始练习。任务结束后，合格题自动归入选定知识库。完成练习后可查看知识点掌握情况。</li></ul><button className="primary-button" onClick={close}>明白了<Icon name="check" size={18}/></button></>}
        {panel.type === 'target' && <><p className="sheet-description">{libraries.length ? '资料、题目集和知识点将归档在同一个主题下。' : '请先新建一个知识库来保存本次资料和题目。'}</p>{libraries.length ? <div className="target-options">{libraries.map(library => <button key={library.id} aria-pressed={target?.id === library.id} onClick={() => { setTargetId(library.id); close() }}><span className={`target-mark cover-${library.color}`}>{library.mark}</span><strong>{library.title}</strong>{target?.id === library.id ? <Icon name="check" size={18}/> : <Icon name="chevron" size={15}/>}</button>)}</div> : <button className="primary-button" onClick={()=>{setNameError('');setNewName('');setPanel({type:'create'})}}>新建知识库<Icon name="plus" size={18}/></button>}</>}

        {(panel.type === 'create' || panel.type==='rename') && <form onSubmit={event => { event.preventDefault();if(!libraryMutation)void saveLibraryName() }}><p className="sheet-description">{panel.type==='rename' ? '填写在书架和出题任务里显示的名称。' : '给新的学习主题留一个位置。'}</p><label className="field-label" htmlFor="library-name">知识库名称</label><input className="text-field" id="library-name" maxLength={120} placeholder="例如：数据库期末复习" value={newName} onChange={event => { setNewName(event.target.value); setNameError('') }} aria-invalid={!!nameError} aria-describedby={nameError ? 'name-error' : undefined}/>{nameError && <p className="field-error" id="name-error" role="alert">{nameError}</p>}<button className="primary-button" type="submit" disabled={!!libraryMutation}>{libraryMutation ? '正在保存…' : panel.type==='rename' ? '保存名称' : '创建知识库'}<Icon name={panel.type==='rename' ? 'check' : 'plus'} size={18}/></button></form>}
        {panel.type === 'document' && document && panelLibrary && <><div className="document-preview-heading"><FileBadge format={document.format} large/><div><strong>{document.kind === 'source' ? '原始学习资料' : 'AI 内容归档示例'}</strong><p>{panelLibrary.title} · {document.format}</p></div></div><div className="paper-preview"><span className="paper-label">知学伴 / 文档呈现示例</span><h3>{document.title.replace(/\.[^.]+$/, '')}</h3>{document.kind === 'questions' ? <><p className="paper-subtitle">选择题 · 节选 1 题</p><p className="question-stem">1. {panelLibrary.question.stem}</p><ul>{panelLibrary.question.options.map(option => <li key={option}>{option}</li>)}</ul><div className="paper-rule"/><p className="supporting">练习交互尚未开放；后续可从题目集开始作答并查看解析。</p></> : document.kind === 'knowledge' ? <><p className="paper-subtitle">知识点目录</p><ol>{panelLibrary.points.map(point => <li key={point}>{point}</li>)}</ol></> : <><p className="paper-subtitle">{document.description}</p><p>{onlineTrial ? '这份资料已上传到试用服务器。' : '这份资料已通过接口上传到本机。'}此面板仅显示文件信息，原文件正文预览尚未接入。</p></>}</div><p className="prototype-note">{document.kind==='source' ? '来源文件已真实上传；正文预览与 Word/PDF 导出尚未接入。' : '此处仅展示内容外观，真实题目请从已保存的 AI 题目集进入。'}</p><button className="primary-button" onClick={close}>关闭预览<Icon name="check" size={18}/></button></>}
        {historyPath && !currentHistory && <p className="supporting" role="status">正在读取练习数据…</p>}
        {historyPath && currentHistory?.error && <p className="field-error" role="alert">{currentHistory.error}</p>}
        {panel.type === 'records' && currentHistory?.data && <><p className="sheet-description">{panelLibrary ? `${panelLibrary.title} · 最近练习` : '各知识库的最近练习'}</p><div className="example-records">{currentHistory.data.sessions.map(record => <div key={record.sessionId}><Icon name="clock" size={19}/><span><strong>{record.libraryName}</strong><small>{new Date(record.created * 1000).toLocaleString('zh-CN')}</small></span><b>答对 {record.correct}/{record.answered} 题</b><button className="archive-link record-return" onClick={()=>openTask(record.taskId)}>查看题目<Icon name="chevron" size={13}/></button></div>)}</div>{!currentHistory.data.sessions.length && <p className="supporting">完成一组练习后，记录会显示在这里。</p>}</>}
        {panel.type === 'analysis' && currentHistory?.data && <><p className="sheet-description">{panelLibrary?.title} · 根据累计作答估计掌握情况</p><PointProgressList points={currentHistory.data.points}/></>}
        {panel.type === 'overview' && <><p className="sheet-description">总览入口留在“我的”。具体知识点与学习建议，回到对应知识库查看。</p><div className="overview-libraries">{libraries.map(library => <button key={library.id} onClick={() => { navigate('libraries', library.id) }}><span className={`target-mark cover-${library.color}`}>{library.mark}</span><span><strong>{library.title}</strong><small>进入知识库查看学习分析</small></span><Icon name="chevron" size={16}/></button>)}</div><p className="prototype-note">当前不展示未经计算的掌握概率或整体学习结论。</p></>}
        {panel.type === 'settings' && <><p className="sheet-description">让学习空间保持简单、清晰。</p><div className="settings-row"><span>外观</span><strong>手帐风 · 暖白与苔绿</strong></div><div className="settings-row"><span>学习数据</span><strong>{onlineTrial ? '保存在试用服务器' : '保存在本机'}</strong></div><p className="supporting">昵称与学习偏好保存在当前浏览器，练习记录来自当前学习空间。</p><button className="secondary-button" onClick={()=>setPanel({type:'demo'})}>使用说明</button><button className="secondary-button reset-demo" onClick={resetDemo}>清空出题草稿</button></>}
      </Sheet>}
    </div></div>
    <footer className="preview-footer">{onlineTrial ? '在线千问出题 · 卡片练习' : '本机千问出题 · 卡片练习'}</footer>
  </div>
}

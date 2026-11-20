import { onlineTrial } from '../deployment'
import { sha256, uploadInChunks } from './resumable'
import type { StudyKind, StudyOutput } from './study'

export type Question = {
  id: string; libraryId: string; prompt: string; options: string[]; answer: string
  explanation: string; points: string[]; difficulty: number; qualityStatus: string
  visualValidationLimit: string
  ai: { sourceFile: string; sourceLocation: string; evidenceQuote?: string; extraction: string; generationModel: string; reviewModel: string }
}
export type ExamTopic = 'mixed' | 'complement' | 'overflow' | 'floating' | 'graph' | 'cache'
export type GenerationTask = {
  taskId: string; status: string; stage: string; stageCode: string; libraryId: string; libraryName: string
  events: { stage: string; stageCode: string; state: string; created: number }[]
  generatedQuestionCount: number; acceptedQuestionCount: number; requestedQuestionCount: number
  savedQuestionCount: number
  availableQuestions?: Question[]; filteredQuestionCount?: number; created?: number; updated?: number
  study?: { kind: Exclude<StudyKind, 'single_choice'>; saved: boolean; hidden: boolean; result: StudyOutput | null } | null
  libraryDeleted?: boolean
  examPractice?: { topic: ExamTopic; label: string; reference: string } | null
  removedSet?: boolean; removedQuestionCount?: number
  error: string; resultId: string | null; reviewNote: string
  rejected: { sourceFile?: string; reasons?: string[]; status?: string }[]
}
export type GenerationTaskSummary = Pick<GenerationTask, 'taskId' | 'status' | 'stage' | 'libraryName' | 'libraryId'> & { created: number }
export const isActiveTask = (task: Pick<GenerationTask, 'status'>) => task.status === 'queued' || task.status === 'running'
export type StoredLibrary = { id: string; title: string; questionSets: { id: string; taskId: string; count: number; examPractice?: boolean }[]; sources: {id:string;name:string;size:number}[]; points:string[]
  studyResults?: { taskId: string; title: string; kind: Exclude<StudyKind, 'single_choice'> }[]
}
export type PointProgress = { point: string; observations: number; correct: number; mastery: number; reviewPriority: boolean }
type SessionSummary = { sessionId: string; taskId: string; libraryId: string; created: number; answered: number; correct: number }
export type PracticeReport = SessionSummary & { points: (PointProgress & { sessionAnswered: number; sessionCorrect: number })[] }
export type PracticeHistory = { sessions: (SessionSummary & { libraryName: string })[]; points: PointProgress[] }
export type DeletedLibrary = Pick<StoredLibrary, 'id' | 'title'>
export type LibraryItem = { libraryId: string; libraryName: string; kind: 'source' | 'set' | 'question' | 'task' | 'study'; id: string; label: string }
export class ApiHttpError extends Error {
  constructor(message: string, readonly status: number) { super(message) }
}
async function errorText(response: Response) {
  if (onlineTrial && response.status === 530) return '公网隧道暂时无法连接。请稍后重试，已选择的资料会保留。'
  if (onlineTrial && response.status === 413) return '单次请求的资料总大小不能超过 25 MB。'
  try { const body = await response.json(); return typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail ?? body) }
  catch { return `服务返回错误（HTTP ${response.status}）` }
}
export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  let response: Response
  try {
    response = await fetch(path, options)
    const retries = onlineTrial && (options.method ?? 'GET').toUpperCase() === 'GET' ? 4 : 0
    for (let attempt = 0; response.status === 530 && attempt < retries; attempt++) {
      await new Promise<void>(resolve => window.setTimeout(resolve, (attempt + 1) * 2000))
      options.signal?.throwIfAborted()
      response = await fetch(path, options)
    }
  }
  catch (error) { if (options.signal?.aborted) throw error; throw new Error(onlineTrial ? '无法连接在线出题服务，请检查网络或稍后重试。' : '无法连接本机出题服务，请确认 Python 服务在 8091 端口运行。') }
  if (!response.ok) throw new ApiHttpError(await errorText(response),response.status)
  try { return await response.json() as T } catch { throw new Error('出题服务响应格式无效，请检查 Python 服务。') }
}
type TaskReceipt = { taskId: string; status: string }
type PendingSubmission = { signature: string; id: string }
const SUBMISSION_KEY = 'zhixue-pending-upload'
let pendingSubmission: PendingSubmission | null = null

export function clearPendingSubmission() {
  pendingSubmission = null
  try { localStorage.removeItem(SUBMISSION_KEY); sessionStorage.removeItem(SUBMISSION_KEY) } catch { /* Browser storage may be disabled. */ }
}

async function uploadSubmission(files: File[], fields: Record<string,string>) {
  const hashes: string[] = []
  for (const file of files) hashes.push(await sha256(file))
  const signature = JSON.stringify([Object.entries(fields).sort(), files.map((file, index) => [file.name, file.size, hashes[index]])])
  const previousSignature = JSON.stringify([Object.entries(fields).sort(), files.map(file => [file.name, file.size, file.lastModified])])
  try {
    const stored = JSON.parse(localStorage.getItem(SUBMISSION_KEY) ?? sessionStorage.getItem(SUBMISSION_KEY) ?? 'null') as PendingSubmission | null
    if (stored && [signature, previousSignature].includes(stored.signature) && /^[a-f0-9]{32}$/.test(stored.id)) {
      pendingSubmission = { signature, id: stored.id }
    }
  } catch { /* A blocked browser store still allows recovery within this page. */ }
  const repeated = pendingSubmission?.signature === signature
  if (!repeated) pendingSubmission = { signature, id: crypto.randomUUID().replaceAll('-', '') }
  try { localStorage.setItem(SUBMISSION_KEY, JSON.stringify(pendingSubmission)) } catch { /* Keep the in-memory receipt. */ }
  return { id: pendingSubmission!.id, repeated, hashes }
}

async function lookupSubmission(id: string): Promise<TaskReceipt | null> {
  const response = await fetch(`/api/generation-submissions/${id}`, { signal: AbortSignal.timeout(6000) })
  if (response.status === 404) return null
  if (!response.ok) throw new ApiHttpError(await errorText(response), response.status)
  return await response.json() as TaskReceipt
}

export async function submitTask(files: File[], fields: Record<string,string>, onProgress: (percent: number | null) => void,
  onDetail?: (detail: string) => void): Promise<TaskReceipt> {
  onDetail?.('正在核对资料…')
  const submission = onlineTrial ? await uploadSubmission(files, fields) : null
  function finish(receipt: TaskReceipt) {
    if (submission && pendingSubmission?.id === submission.id) {
      clearPendingSubmission()
    }
    return receipt
  }
  if (submission?.repeated) {
    onDetail?.('正在核对上一次提交结果…')
    try {
      const previous = await lookupSubmission(submission.id)
      if (previous) return finish(previous)
    } catch (error) {
      if (error instanceof ApiHttpError && error.status === 401) throw error
    }
  }
  if (submission) return finish(await uploadInChunks(files, submission.hashes, fields, submission.id, onProgress, onDetail))
  return submitLocalTask(files, fields, onProgress, onDetail)
}

function submitLocalTask(files: File[], fields: Record<string,string>, onProgress: (percent: number | null) => void,
  onDetail?: (detail: string) => void): Promise<TaskReceipt> {
  return new Promise<TaskReceipt>((resolve,reject) => {
    const form = new FormData()
    files.forEach(file => form.append('files',file,file.name))
    Object.entries(fields).forEach(([name,value]) => form.append(name,value))
    const request = new XMLHttpRequest()
    request.open('POST','/api/generation-tasks')
    request.timeout=15 * 60 * 1000
    const started = performance.now()
    request.upload.onprogress=event => {
      onProgress(event.lengthComputable ? Math.round(event.loaded/event.total*100) : null)
      const seconds = Math.max(1, (performance.now() - started) / 1000)
      const sent = (event.loaded / 1024 / 1024).toFixed(1)
      const total = event.lengthComputable ? ` / ${(event.total / 1024 / 1024).toFixed(1)}` : ''
      onDetail?.(`已发送 ${sent}${total} MB · 约 ${Math.round(event.loaded / seconds / 1024)} KB/s`)
    }
    request.upload.onload=()=>onDetail?.('文件已发送，正在等待服务器确认…')
    async function recover(message: string) {
      reject(new Error(message))
    }
    request.onerror=()=>void recover(onlineTrial ? '上传连接中断。已保留资料和出题要求，请检查网络后再点出题，系统会先核对上次任务。' : '无法连接本机出题服务，请检查 Python 服务与文件上传连接。')
    request.ontimeout=()=>void recover('上传等待已超过15分钟。已保留文件，请检查网络后重试。')
    request.onload=()=>{
      if (onlineTrial && request.status === 413) { reject(new Error('单次请求的资料总大小不能超过 25 MB。')); return }
      let body
      try { body=JSON.parse(request.responseText) } catch { void recover('连接暂时中断。请检查网络后重试，系统会先核对上一次提交。');return }
      if (request.status<200 || request.status>=300) {
        const message = typeof body.detail==='string' ? body.detail : JSON.stringify(body.detail ?? body)
        if (request.status>=500 || request.status===408) void recover(message)
        else reject(new Error(message))
        return
      }
      if (!body.taskId) { reject(new Error('服务没有返回任务ID'));return }
      resolve(body)
    }
    onDetail?.('正在上传资料…')
    request.send(form)
  })
}

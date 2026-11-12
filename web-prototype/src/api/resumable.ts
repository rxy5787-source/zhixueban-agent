type Receipt = { taskId: string; status: string }
type UploadStatus = { offsets: number[]; chunkBytes: number; receipt: Receipt | null }

class UploadError extends Error {
  constructor(message: string, readonly status: number) { super(message) }
}

async function pause(milliseconds: number) {
  await new Promise<void>(resolve => {
    const finish = () => {
      window.clearTimeout(timer)
      window.removeEventListener('online', finish)
      document.removeEventListener('visibilitychange', onVisible)
      resolve()
    }
    const onVisible = () => { if (!document.hidden) finish() }
    const timer = window.setTimeout(finish, milliseconds)
    window.addEventListener('online', finish, { once: true })
    document.addEventListener('visibilitychange', onVisible)
  })
}

async function request<T>(path: string, options: RequestInit, onDetail?: (detail: string) => void): Promise<T> {
  for (let attempt = 0; attempt < 6; attempt++) {
    try {
      const response = await fetch(path, { ...options, signal: AbortSignal.timeout(60000) })
      if (!response.ok) {
        let detail = `上传服务暂时无法连接（HTTP ${response.status}）`
        try { const data = await response.json(); if (typeof data.detail === 'string') detail = data.detail } catch { /* The tunnel may return HTML. */ }
        throw new UploadError(detail, response.status)
      }
      return await response.json() as T
    } catch (error) {
      if (error instanceof UploadError && error.status < 500 && ![408, 429].includes(error.status)) throw error
      if (attempt === 5) throw new Error('连接暂时中断，已收到的资料片段已保存。网络恢复后再点出题，可接着上传。')
      onDetail?.('连接中断，已保存上传进度，正在重连…')
      await pause(Math.min(8000, 1000 * 2 ** attempt))
    }
  }
  throw new Error('上传暂时无法完成，请稍后继续')
}

export async function uploadInChunks(files: File[], hashes: string[], fields: Record<string,string>, id: string,
  onProgress: (percent: number | null) => void, onDetail?: (detail: string) => void): Promise<Receipt> {
  const base = `/api/resumable-uploads/${id}`
  const descriptors = files.map((file, index) => ({ name: file.name, size: file.size, sha256: hashes[index] }))
  onDetail?.('正在核对已保存的上传进度…')
  const state = await request<UploadStatus>(base, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...fields, questionCount: Number(fields.questionCount), files: descriptors }),
  }, onDetail)
  if (state.receipt) return state.receipt
  const total = files.reduce((sum, file) => sum + file.size, 0)
  const offsets = [...state.offsets]
  const initial = offsets.reduce((sum, value) => sum + value, 0)
  const start = performance.now()
  onProgress(Math.floor(initial / total * 100))
  for (let index = 0; index < files.length; index++) {
    while (offsets[index] < files[index].size) {
      const offset = offsets[index]
      const content = files[index].slice(offset, offset + state.chunkBytes)
      const digest = await sha256(content)
      const saved = offsets.reduce((sum, value) => sum + value, 0)
      onDetail?.(`${files[index].name} · 已保存 ${(saved / 1048576).toFixed(1)} / ${(total / 1048576).toFixed(1)} MB`)
      const reply = await request<{ offset: number }>(`${base}/files/${index}?offset=${offset}`, {
        method: 'PUT', headers: { 'Content-Type': 'application/octet-stream', 'X-Chunk-SHA256': digest }, body: content,
      }, onDetail)
      if (reply.offset <= offset || reply.offset > files[index].size) throw new Error('上传进度返回异常，请重新核对')
      offsets[index] = reply.offset
      const confirmed = offsets.reduce((sum, value) => sum + value, 0)
      const speed = Math.round((confirmed - initial) / Math.max(1, (performance.now() - start) / 1000) / 1024)
      onProgress(Math.floor(confirmed / total * 100))
      onDetail?.(`已保存 ${(confirmed / 1048576).toFixed(1)} / ${(total / 1048576).toFixed(1)} MB · 约 ${speed} KB/s`)
    }
  }
  onDetail?.('资料已上传完整，正在校验并创建出题任务…')
  return await request<Receipt>(`${base}/complete`, { method: 'POST' }, onDetail)
}

export async function sha256(content: Blob) {
  const digest = await crypto.subtle.digest('SHA-256', await content.arrayBuffer())
  return Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('')
}

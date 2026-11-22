import { useRef, useState } from 'react'
import { Icon } from '../components/Icon'
import type { LocalLibrary } from '../offline/storage'
import { OnlineStudyEntry } from './OnlineStudyEntry'

export function OfflineConversation({ libraries, ready, onFiles, onPractice }: {
  libraries: LocalLibrary[]
  ready: boolean
  onFiles: (id: string | null, files: File[]) => Promise<void>
  onPractice: () => void
}) {
  const [requirement, setRequirement] = useState('')
  const [messages, setMessages] = useState<string[]>([])
  const [libraryId, setLibraryId] = useState('')
  const [fileState, setFileState] = useState('')
  const [saving, setSaving] = useState(false)
  const input = useRef<HTMLInputElement>(null)
  const destination = libraries.find(library => library.id === libraryId) ?? libraries[0]

  async function attach(files: File[]) {
    if (!files.length) return
    setSaving(true)
    setFileState('正在保存资料到本机…')
    try {
      await onFiles(destination?.id ?? null, files)
      setFileState(`已保存到「${destination?.name ?? '学习资料'}」：${files.map(file => file.name).join('、')}`)
    } catch (error) {
      setFileState(error instanceof Error ? error.message : '资料未能保存，请检查站点存储。')
    } finally { setSaving(false) }
  }

  return <section className="offline-page" aria-labelledby="offline-study-heading">
    <h1 id="offline-study-heading">学习对话</h1>
    <p className="supporting">离线模式 · AI 出题暂不可用。可以输入学习要求、保存资料，或练习已有的示例题。</p>
    <OnlineStudyEntry />
    <div className="offline-thread" role="log" aria-label="对话记录">
      {messages.map((message, index) => <p className="study-user-message" key={index}>{message}</p>)}
      {messages.length > 0 && <p className="supporting">学习要求已保留在此对话。当前没有提交 AI 任务。</p>}
    </div>
    <form className="offline-card" onSubmit={event => {
      event.preventDefault()
      const message = requirement.trim()
      if (!message) return
      setMessages(previous => [...previous, message])
      setRequirement('')
    }}>
      <label className="field-label" htmlFor="offline-requirement">学习要求</label>
      <textarea className="text-field" id="offline-requirement" rows={3} maxLength={1200}
        placeholder="根据我上传的数据库资料生成10道选择题，难度中等。"
        value={requirement} onChange={event => setRequirement(event.target.value)} />
      {libraries.length > 0 && <label className="field-label">资料归档到
        <select className="text-field" value={destination?.id ?? ''} onChange={event => setLibraryId(event.target.value)}>
          {libraries.map(library => <option key={library.id} value={library.id}>{library.name}</option>)}
        </select>
      </label>}
      <div className="offline-actions">
        <button className="secondary-button" type="button" disabled={!ready || saving} onClick={() => input.current?.click()}>
          <Icon name="plus" size={18}/> 添加资料
        </button>
        <input ref={input} type="file" hidden multiple accept=".pdf,.doc,.docx,.txt" aria-label="选择学习资料"
          onChange={event => { const files = Array.from(event.currentTarget.files ?? []); event.currentTarget.value = ''; void attach(files) }} />
        <button className="primary-button" type="submit" disabled={!requirement.trim()}>记在本轮</button>
      </div>
    </form>
    {fileState && <p role="status">{fileState}</p>}
    <button className="secondary-button" onClick={onPractice}>练习已有题库</button>
  </section>
}

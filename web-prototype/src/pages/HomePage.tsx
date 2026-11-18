import { useEffect, useRef } from 'react'
import { Icon } from '../components/Icon'
import { onlineTrial } from '../deployment'
import companion from '../assets/handbook/paper-companion.svg'
import plus from '../assets/handbook/plus.svg'
import folder from '../assets/handbook/folder.svg'
import targetChevron from '../assets/handbook/target-chevron.svg'
import arrow from '../assets/handbook/arrow.svg'
import recent from '../assets/handbook/recent.svg'
import recentChevron from '../assets/handbook/recent-chevron.svg'
import type { StudyTurn } from '../api/study'
import { StudyTurnCard } from './StudyConversation'

export type SelectedFile = { id: string; name: string; file: File }
type Props = {
  files: SelectedFile[]; requirement: string; libraryTitle: string; feedback: string
  studyEnabled: boolean; turns: StudyTurn[]; contextTurn?: StudyTurn
  submitting: boolean; uploadPercent: number | null; uploadDetail: string; revision: number
  onNewThread: () => void; onOpenTask: (id: string, practice?: boolean) => void
  onRetry: (id: string) => Promise<void>; onSaved: () => Promise<void>
  onFiles: (files: File[]) => void; onRemove: (id: string) => void
  onRequirement: (value: string) => void; onTarget: () => void
  onGenerate: () => void; onRecent: () => void
}

export function HomePage(props: Props) {
  const fileInput = useRef<HTMLInputElement>(null)
  const input = useRef<HTMLTextAreaElement>(null)
  const bottom = useRef<HTMLDivElement>(null)
  const latest = props.turns.at(-1)
  const hasThread = props.studyEnabled && !!latest
  const context = props.files.length ? undefined : props.contextTurn
  useEffect(() => {
    if (hasThread) bottom.current?.scrollIntoView({ block: 'nearest' })
  }, [hasThread, latest?.id])

  function suggest(text: string) {
    if (props.requirement.trim() || props.submitting) return
    props.onRequirement(text)
    input.current?.focus()
  }

  return <div className={`home-page page-enter${hasThread ? ' study-home' : ''}`}>
    {hasThread ? <>
      <header className="study-thread-header">
        <div><h1>学习对话</h1><small>{latest.libraryName}</small></div>
        <button className="archive-link" disabled={props.submitting} onClick={props.onNewThread}><Icon name="plus" size={15}/>新对话</button>
      </header>
      <section className="study-thread" aria-label="对话记录">
        {props.turns.map(turn => <StudyTurnCard key={turn.id} turn={turn} revision={props.revision}
          onOpen={props.onOpenTask} onSaved={props.onSaved} onRetry={turn.id === latest.id ? props.onRetry : undefined}
          onPrompt={turn.id === context?.id && !props.requirement.trim() ? suggest : undefined}/>)}
      </section>
    </> : <section className="assistant-intro" aria-labelledby="home-heading">
      <div className="assistant-copy">
        <span className="handbook-tag">学习手帐</span>
        <h1 id="home-heading">今天想<br/>练什么？</h1>
        <p className="intro-copy">{props.studyEnabled ? <>加一份资料，<br/>聊懂它，再练习。</> : <>从手边的资料，<br/>开始一组练习。</>}</p>
      </div>
      <img className="assistant-art" src={companion} width="194" height="206" alt=""/>
    </section>}
    <form className="composer" aria-label={props.studyEnabled ? '发送学习要求' : '出题'} onSubmit={event => { event.preventDefault(); props.onGenerate() }}>
      {context && <p className="study-context"><Icon name="file" size={14}/> 沿用 {context.sources.join('、')}</p>}
      <div className="composer-input">
        <label htmlFor="generation-requirement">{props.studyEnabled ? '你想怎么学？' : '出题要求'}</label>
        <textarea ref={input} id="generation-requirement" value={props.requirement} maxLength={600} disabled={props.submitting}
          enterKeyHint={props.studyEnabled ? 'send' : 'enter'}
          placeholder={context ? '继续追问，例如：把刚才的口诀改短一点' : props.studyEnabled ? '例如：解释这份资料，或者生成练习题' : '例如：根据这份资料出 5 道选择题'}
          onKeyDown={event => {
            if (!props.studyEnabled || event.key !== 'Enter' || event.shiftKey || event.nativeEvent.isComposing || event.keyCode === 229) return
            event.preventDefault()
            if (!props.submitting) event.currentTarget.form?.requestSubmit()
          }}
          onChange={event => props.onRequirement(event.target.value)}/>
      </div>
      {props.studyEnabled && !hasThread && !props.requirement.trim() && <div className="study-suggestions">
        <button type="button" onClick={() => suggest('帮我把资料中的要点编成记忆口诀')}>编口诀</button>
        <button type="button" onClick={() => suggest('根据资料生成填空练习')}>做填空</button>
        <button type="button" onClick={() => suggest('根据资料生成 3 道选择题')}>做选择题</button>
      </div>}
      {props.files.length > 0 && <ul className="attached-files" aria-label="已选择的本机文件">{props.files.map(file => <li key={file.id}>
        <span className="attachment-icon"><Icon name="file" size={17}/></span>
        <strong className="attachment-name" title={file.name}>{file.name}</strong>
        <button type="button" disabled={props.submitting} aria-label={`移除 ${file.name}`} onClick={() => props.onRemove(file.id)}><Icon name="close" size={16}/></button>
      </li>)}</ul>}
      <div className="composer-tools">
        <button type="button" disabled={props.submitting} className="add-file-button" aria-label="添加学习资料" onClick={() => fileInput.current?.click()}>
          <img src={plus} width="17" height="17" alt=""/>加资料
        </button>
        <input ref={fileInput} type="file" hidden multiple accept=".docx,.pdf,.png,.jpg,.jpeg,.webp,.bmp,.txt" aria-label="选择知识文件" onChange={event => { props.onFiles(Array.from(event.target.files ?? [])); event.target.value = '' }}/>
        <button type="button" disabled={props.submitting} className="archive-target" aria-label={`归档知识库：${props.libraryTitle}`} title={`归档知识库：${props.libraryTitle}`} onClick={props.onTarget}>
          <img src={folder} width="17" height="17" alt=""/>
          <span className="archive-target-copy"><small>归档到</small><strong>{props.libraryTitle}</strong></span>
          <img src={targetChevron} width="12" height="12" alt=""/>
        </button>
        <button className="send-button" type="submit" aria-label={props.studyEnabled ? '发送学习要求' : '开始生成题目'} disabled={props.submitting || (!props.files.length && !props.requirement.trim())}>
          <img src={arrow} width="17" height="17" alt=""/>{props.studyEnabled ? '发送' : '出题'}
        </button>
      </div>
      {props.submitting && <p className="study-context" role="status">{props.uploadDetail || '正在提交学习任务…'}{props.uploadPercent !== null ? ` · ${props.uploadPercent}%` : ''}</p>}
      {props.feedback && <p className="generation-error" role="alert">{props.feedback}</p>}
    </form>
    {!hasThread && <p className="composer-hint">支持 Word、PDF、图片和 TXT{onlineTrial && <><br/>资料保存在试用服务器，请勿上传敏感文件。</>}</p>}
    {!hasThread && <button type="button" className="last-generation" onClick={props.onRecent}>
      <span className="recent-mark"><img src={recent} width="20" height="20" alt=""/></span>
      <span className="recent-copy"><strong>最近出题</strong><small>查看出题进度与历史结果</small></span>
      <img src={recentChevron} width="17" height="17" alt=""/>
    </button>}
    <div ref={bottom}/>
  </div>
}

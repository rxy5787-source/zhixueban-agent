import { useRef, useState } from 'react'
import { onlineTrial, staticDemo } from '../deployment'
import { Icon } from '../components/Icon'
import type { DocumentKind, Library, LibraryDocument } from '../data/demo'

export function FileBadge({ format, large = false }: { format: LibraryDocument['format']; large?: boolean }) {
  return <span className={`file-badge format-${format.toLowerCase()} ${large ? 'large' : ''}`} aria-hidden="true"><span>{format === 'DOCX' ? 'W' : format === 'JPG' ? 'IMG' : format === 'QSET' ? '题' : format === 'NOTE' ? '记' : format}</span></span>
}
export function BookshelfPage({ libraries, deletedCount, loading, error, onRetry, onTrash, onOpen, onCreate }: {
  libraries: Library[]; deletedCount: number; loading: boolean; error: string
  onRetry: () => void; onTrash: () => void; onOpen: (id: string) => void; onCreate: () => void
}) {
  const [query, setQuery] = useState('')
  const search = useRef<HTMLInputElement>(null)
  const filtered = libraries.filter(library => `${library.title} ${library.subtitle}`.toLowerCase().includes(query.trim().toLowerCase()))
  function clearSearch() {
    setQuery('')
    search.current?.focus()
  }
  return <div className="bookshelf-page page-enter">
    <header className="editorial-heading">
      <div><h1>知识库</h1><p>{staticDemo ? '以下是示例主题。在线知识库尚未开放。' : '按主题整理资料、知识点和练习。'}</p></div>
      <button className="shelf-create" aria-label="新建知识库" onClick={onCreate}><Icon name="plus" size={18}/>新建</button>
    </header>
    <div className="shelf-tools">
      <div className="shelf-search" role="search"><Icon name="search" size={18}/><input ref={search} type="search" value={query} onChange={event => setQuery(event.target.value)} placeholder="搜索知识库" aria-label="搜索知识库"/>{query && <button aria-label="清空搜索" onClick={clearSearch}><Icon name="close" size={16}/></button>}</div>
    </div>
    <div className="shelf-caption"><h2 aria-live="polite">{query.trim() ? '搜索结果' : '全部主题'} <small>{filtered.length}</small></h2><button className="archive-link" onClick={onTrash}>回收站{deletedCount>0 ? ` · ${deletedCount}` : ''}</button></div>
    {loading && <p className="supporting" role="status">正在读取知识库…</p>}
    {error && <div className="generation-error" role="alert"><p>{error}</p><button className="archive-link" onClick={onRetry}>重新读取</button></div>}
    {filtered.length > 0 ? <ul className="catalog-grid">{filtered.map(library => <li key={library.id}><button className="catalog-item" onClick={() => onOpen(library.id)} aria-label={`打开${library.title}知识库`} aria-describedby={`catalog-counts-${library.id}`}>
      <span className={`catalog-spine cover-${library.color}`} aria-hidden="true"><Icon name="libraries" size={16}/><span>{library.mark}</span></span>
      <span className="catalog-copy"><strong>{library.title}</strong><span>{library.subtitle}</span><small id={`catalog-counts-${library.id}`}>{library.documents.filter(document => document.kind === 'source').length} 份资料 · {library.documents.filter(document => document.kind === 'questions').length} 份题目集</small></span>
      <Icon name="chevron" size={16}/>
    </button></li>)}</ul> : !loading && !error && <div className="empty-state"><Icon name={query.trim() ? 'search' : 'libraries'} size={28}/><h2>{query.trim() ? '没有找到这个知识库' : '还没有知识库'}</h2><p>{query.trim() ? '换个主题名称试试。' : '新建一个主题，归档你的第一份学习资料。'}</p><button className="secondary-button" onClick={query.trim() ? clearSearch : onCreate}>{query.trim() ? '清空搜索' : '新建知识库'}</button></div>}
  </div>
}
type Filter = 'all' | DocumentKind
const FILTERS: { id: Filter; title: string }[] = [{ id: 'all', title: '全部' }, { id: 'questions', title: '题目集' }, { id: 'source', title: '原始资料' }, { id: 'knowledge', title: '知识点' }]
export function LibraryDetailPage({ library, onBack, onDelete, onRename, onRemoveItem, onDocument, onCompose, onRecords, onAnalysis }: {
  library: Library; onBack: () => void; onDelete: () => void; onRename: () => void
  onRemoveItem: (document: LibraryDocument) => void; onDocument: (document: LibraryDocument) => void
  onCompose: () => void; onRecords: () => void; onAnalysis: () => void
}) {
  const [filter, setFilter] = useState<Filter>('all')
  const [managing, setManaging] = useState(false)
  const documents = library.documents.filter(document => filter === 'all' || document.kind === filter)
  return <div className="library-detail page-enter">
    <div className="library-actions"><button className="back-link" onClick={onBack}><Icon name="back" size={18}/>我的书架</button><div><button className="archive-link" onClick={onRename}>改名</button><button className="archive-link remove-link" onClick={onDelete}>删除知识库</button></div></div>
    <div className="library-heading"><span className={`mini-cover cover-${library.color}`}>{library.mark}</span><div><h1>{library.title}</h1><p>{library.subtitle}</p><span>{staticDemo ? '示例主题' : onlineTrial ? '主题知识库 · 试用存储' : '主题知识库 · 本机存储'}</span></div></div>
    <button className="compose-in-library" onClick={onCompose}><span><Icon name="plus" size={19}/>添加资料并出题</span><Icon name="arrow" size={17}/></button>
    <div className="document-filters" aria-label="知识库内容分类">{FILTERS.map(item => <button key={item.id} aria-pressed={filter === item.id} onClick={() => setFilter(item.id)}>{item.title}</button>)}</div>
    {filter === 'knowledge' && library.points.length > 0 && <div className="point-chips">{library.points.map(point => <span key={point}>{point}</span>)}</div>}
    {library.documents.length > 0 && <div className="manage-content"><button className="archive-link" aria-pressed={managing} onClick={() => setManaging(value => !value)}>{managing ? '完成管理' : '管理内容'}</button></div>}
    <div className="document-list">{documents.map(document => <div className="row-with-action" key={document.id}>
      <button className="document-row" onClick={() => onDocument(document)}><FileBadge format={document.format}/><span><strong>{document.title}</strong><small>{document.description}</small></span><Icon name={document.taskId ? 'play' : 'chevron'} size={15}/></button>
      {managing && (document.taskId || document.kind==='source') && <button className="archive-link remove-link" aria-label={`移除 ${document.title}`} onClick={() => onRemoveItem(document)}>移除</button>}
    </div>)}</div>
    {documents.length === 0 && !(filter === 'knowledge' && library.points.length) && <div className="empty-state"><Icon name="folder" size={28}/><h2>{library.documents.length ? '这里还没有这类内容' : '还没有学习资料'}</h2><p>{staticDemo ? '在线服务尚未开放。' : '添加学习资料，再将生成内容归档到这里。'}</p><button className="secondary-button" onClick={onCompose}>去添加资料</button></div>}
    <div className="library-insights"><button onClick={onRecords}><Icon name="clock" size={19}/><span>练习记录</span><Icon name="chevron" size={14}/></button><button onClick={onAnalysis}><Icon name="reports" size={19}/><span>学习分析</span><Icon name="chevron" size={14}/></button></div>
  </div>
}

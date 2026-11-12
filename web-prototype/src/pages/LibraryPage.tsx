import { useState } from 'react'
import { onlineTrial } from '../deployment'
import { BookGarden, Icon } from '../components/Icon'
import type { DocumentKind, Library, LibraryDocument } from '../data/demo'

export function FileBadge({ format, large = false }: { format: LibraryDocument['format']; large?: boolean }) {
  return <span className={`file-badge format-${format.toLowerCase()} ${large ? 'large' : ''}`} aria-hidden="true"><span>{format === 'DOCX' ? 'W' : format === 'JPG' ? 'IMG' : format === 'QSET' ? '题' : format === 'NOTE' ? '记' : format}</span></span>
}
export function BookshelfPage({ libraries, deletedCount, onTrash, onOpen, onCreate }: { libraries: Library[]; deletedCount: number; onTrash: () => void; onOpen: (id: string) => void; onCreate: () => void }) {
  const [query, setQuery] = useState('')
  const filtered = libraries.filter(library => `${library.title} ${library.subtitle}`.toLowerCase().includes(query.trim().toLowerCase()))
  return <div className="bookshelf-page page-enter">
    <header className="handbook-section-intro bookshelf-intro">
      <div className="handbook-section-copy">
        <span className="handbook-tag">学习手帐</span>
        <h1>我的知识库</h1>
        <p>把资料和题目收进自己的书架。</p>
      </div>
      <BookGarden />
    </header>
    <div className="shelf-tools">
      <label className="shelf-search"><Icon name="search" size={18}/><input value={query} onChange={event => setQuery(event.target.value)} placeholder="搜索知识库" aria-label="搜索知识库"/>{query && <button aria-label="清空搜索" onClick={() => setQuery('')}><Icon name="close" size={16}/></button>}</label>
      <button className="shelf-create" aria-label="新建知识库" onClick={onCreate}><Icon name="plus" size={18}/>新建</button>
    </div>
    <div className="shelf-caption"><span>{query ? '搜索结果' : '全部书架'} <small>{filtered.length}</small></span><button className="archive-link" onClick={onTrash}>回收站{deletedCount>0 ? ` · ${deletedCount}` : ''}</button></div>
    {filtered.length > 0 ? <div className="shelves">{Array.from({ length: Math.ceil(filtered.length / 2) }, (_, row) => <div className="shelf-row" key={row}>{filtered.slice(row * 2, row * 2 + 2).map(library => <button className="book-tile" key={library.id} onClick={() => onOpen(library.id)} aria-label={`打开${library.title}知识库`}>
      <span className={`book-cover cover-${library.color}`}><span className="book-series">知学伴 / KNOWLEDGE</span><span className="book-mark">{library.mark}</span><strong>{library.title}</strong><span className="book-subtitle">{library.subtitle}</span><span className="book-cover-footer"><span>学习资料集</span><Icon name="arrow" size={16}/></span></span>
      <span className="book-caption"><strong>{library.title}</strong><span>{library.documents.filter(document => document.kind === 'source').length} 份资料 <i/> {library.documents.filter(document => document.kind === 'questions').length} 份题目集</span><small>{library.updated}</small></span>
    </button>)}</div>)}</div> : <div className="empty-state"><Icon name="search" size={30}/><h2>没有找到这个知识库</h2><p>试试其他名称，或新建一个学习主题。</p><button className="secondary-button" onClick={onCreate}>新建知识库</button></div>}
    <p className="shelf-note"><Icon name="folder" size={15}/>原始资料、题目和知识点，按主题一起归档。</p>
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
    <div className="library-heading"><span className={`mini-cover cover-${library.color}`}>{library.mark}</span><div><h1>{library.title}</h1><p>{library.subtitle}</p><span>{onlineTrial ? '主题知识库 · 试用存储' : '主题知识库 · 本机存储'}</span></div></div>
    <button className="compose-in-library" onClick={onCompose}><span><Icon name="plus" size={19}/>添加资料并出题</span><Icon name="arrow" size={17}/></button>
    <div className="document-filters" aria-label="知识库内容分类">{FILTERS.map(item => <button key={item.id} aria-pressed={filter === item.id} onClick={() => setFilter(item.id)}>{item.title}</button>)}</div>
    {filter === 'knowledge' && library.points.length > 0 && <div className="point-chips">{library.points.map(point => <span key={point}>{point}</span>)}</div>}
    {library.documents.length > 0 && <div className="manage-content"><button className="archive-link" aria-pressed={managing} onClick={() => setManaging(value => !value)}>{managing ? '完成管理' : '管理内容'}</button></div>}
    <div className="document-list">{documents.map(document => <div className="row-with-action" key={document.id}>
      <button className="document-row" onClick={() => onDocument(document)}><FileBadge format={document.format}/><span><strong>{document.title}</strong><small>{document.description}</small></span><Icon name={document.taskId ? 'play' : 'chevron'} size={15}/></button>
      {managing && (document.taskId || document.kind==='source') && <button className="archive-link remove-link" aria-label={`移除 ${document.title}`} onClick={() => onRemoveItem(document)}>移除</button>}
    </div>)}</div>
    {documents.length === 0 && <div className="empty-state"><Icon name="folder" size={32}/><h2>{library.documents.length ? '这里还没有这类内容' : '书架准备好了'}</h2><p>添加学习资料，再将生成内容归档到这里。</p><button className="secondary-button" onClick={onCompose}>去添加资料</button></div>}
    <div className="library-insights"><button onClick={onRecords}><Icon name="clock" size={19}/><span>练习记录</span><Icon name="chevron" size={14}/></button><button onClick={onAnalysis}><Icon name="reports" size={19}/><span>学习分析</span><Icon name="chevron" size={14}/></button></div>
  </div>
}

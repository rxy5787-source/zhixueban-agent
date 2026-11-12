/** UI fixtures only: no AI, uploaded file contents or BKT calculations. */
export type Destination = 'home' | 'libraries' | 'profile'
export const DESTINATIONS: { id: Destination; title: string }[] = [
  { id: 'home', title: '首页' }, { id: 'libraries', title: '知识库' }, { id: 'profile', title: '我的' },
]
export type DocumentKind = 'source' | 'questions' | 'knowledge'
export type LibraryDocument = { id: string; title: string; format: 'PDF' | 'DOCX' | 'JPG' | 'QSET' | 'TXT' | 'NOTE'; kind: DocumentKind; description: string; taskId?: string; study?: boolean }
export type Library = {
  id: string; title: string; subtitle: string; mark: string
  color: 'mint' | 'sand' | 'blue' | 'rose'; updated: string
  documents: LibraryDocument[]; points: string[]
  question: { stem: string; options: string[] }
  records: { title: string; time: string; result: string }[]
}
export const LIBRARY_SEEDS: Library[] = [
  {
    id: 'sql', title: 'SQL 学习笔记', subtitle: '数据库 · 查询与应用', mark: 'SQL', color: 'mint', updated: '今天整理',
    documents: [
      { id: 'sql-source', title: 'SQL学习讲义.pdf', format: 'PDF', kind: 'source', description: '原始资料 · 24 页示例' },
      { id: 'sql-notes', title: '课堂笔记.docx', format: 'DOCX', kind: 'source', description: '原始资料 · Word 示例' },
      { id: 'sql-basic', title: '题目集_基础版.docx', format: 'DOCX', kind: 'questions', description: '10 道选择题 · 文档示例' },
      { id: 'sql-advanced', title: '题目集_提高版.pdf', format: 'PDF', kind: 'questions', description: '6 道提高题 · 文档示例' },
      { id: 'sql-summary', title: '知识点总结.docx', format: 'DOCX', kind: 'knowledge', description: '4 个知识点 · 文档示例' },
    ],
    points: ['SELECT 查询', '分组与聚合', '多表连接', '子查询'],
    question: { stem: '在 SQL 中，筛选分组后的聚合结果应使用哪个子句？', options: ['A. WHERE', 'B. HAVING', 'C. ORDER BY', 'D. LIMIT'] },
    records: [{ title: '基础查询练习', time: '昨天 20:30', result: '答对 5 / 6 题' }],
  },
  {
    id: 'structure', title: '数据结构', subtitle: '计算机 · 从理解到应用', mark: '{ }', color: 'sand', updated: '昨天整理',
    documents: [
      { id: 'ds-source', title: '数据结构复习.pdf', format: 'PDF', kind: 'source', description: '原始资料 · 32 页示例' },
      { id: 'ds-image', title: '二叉树课堂板书.jpg', format: 'JPG', kind: 'source', description: '原始资料 · 图片示例' },
      { id: 'ds-basic', title: '题目集_基础版.docx', format: 'DOCX', kind: 'questions', description: '12 道选择题 · 文档示例' },
      { id: 'ds-summary', title: '知识点总结.docx', format: 'DOCX', kind: 'knowledge', description: '4 个知识点 · 文档示例' },
    ],
    points: ['线性表', '栈与队列', '二叉树', '排序算法'],
    question: { stem: '以下哪种数据结构遵循先进先出的原则？', options: ['A. 栈', 'B. 队列', 'C. 二叉搜索树', 'D. 堆'] },
    records: [{ title: '线性结构练习', time: '10 月 30 日', result: '答对 6 / 8 题' }],
  },
  {
    id: 'english', title: '英语六级', subtitle: '语言 · 日积月累', mark: 'Aa', color: 'blue', updated: '2 天前整理',
    documents: [
      { id: 'en-source', title: '六级词汇笔记.docx', format: 'DOCX', kind: 'source', description: '原始资料 · Word 示例' },
      { id: 'en-basic', title: '题目集_基础版.pdf', format: 'PDF', kind: 'questions', description: '10 道词汇题 · 文档示例' },
      { id: 'en-summary', title: '知识点总结.docx', format: 'DOCX', kind: 'knowledge', description: '3 个知识点 · 文档示例' },
    ],
    points: ['核心词汇', '长难句', '阅读理解'],
    question: { stem: '请选择与 significant 含义最接近的词。', options: ['A. important', 'B. ordinary', 'C. temporary', 'D. narrow'] },
    records: [],
  },
  {
    id: 'reasoning', title: '行测资料分析', subtitle: '公考 · 数字里的逻辑', mark: '%', color: 'rose', updated: '3 天前整理',
    documents: [
      { id: 're-source', title: '资料分析方法.pdf', format: 'PDF', kind: 'source', description: '原始资料 · 18 页示例' },
      { id: 're-basic', title: '题目集_基础版.docx', format: 'DOCX', kind: 'questions', description: '10 道选择题 · 文档示例' },
      { id: 're-wrong', title: '错题巩固卷.pdf', format: 'PDF', kind: 'questions', description: '5 道巩固题 · 文档示例' },
      { id: 're-summary', title: '知识点总结.docx', format: 'DOCX', kind: 'knowledge', description: '3 个知识点 · 文档示例' },
    ],
    points: ['截位直除', '增长率与增长量', '比重'],
    question: { stem: '现期量为 120，基期量为 100，增长率是多少？', options: ['A. 10%', 'B. 15%', 'C. 20%', 'D. 25%'] },
    records: [{ title: '增长率基础练习', time: '10 月 29 日', result: '答对 4 / 6 题' }],
  },
]

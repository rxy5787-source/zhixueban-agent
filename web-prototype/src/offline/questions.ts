export type OfflineQuestion = { id: string; stem: string; options: string[]; answer: number; explanation: string }

// The four original demonstration questions, with explicit answers and explanations.
export const sampleQuestions: OfflineQuestion[] = [
  { id: 'sql-having', stem: '在 SQL 中，筛选分组后的聚合结果应使用哪个子句？',
    options: ['WHERE', 'HAVING', 'ORDER BY', 'LIMIT'], answer: 1, explanation: 'HAVING 筛选分组后的结果。WHERE 在分组前筛选数据行。' },
  { id: 'fifo', stem: '以下哪种数据结构遵循先进先出的原则？',
    options: ['栈', '队列', '二叉搜索树', '堆'], answer: 1, explanation: '队列从队尾入队、队首出队，因此最早入队的元素最先被取出。' },
  { id: 'significant', stem: '请选择与 significant 含义最接近的词。',
    options: ['important', 'ordinary', 'temporary', 'narrow'], answer: 0, explanation: 'significant 可表示重要的，和 important 含义相近。' },
  { id: 'growth-rate', stem: '现期量为 120，基期量为 100，增长率是多少？',
    options: ['10%', '15%', '20%', '25%'], answer: 2, explanation: '增长率等于增长量除以基期量，即 (120 − 100) ÷ 100 = 20%。' },
]

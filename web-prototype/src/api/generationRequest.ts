import type { ExamTopic } from './generation'

type GenerationRequest =
  | { kind: 'material'; questionCount: number }
  | { kind: 'exam'; questionCount: number; topic: ExamTopic }
  | { error: string }

function questionCount(text: string, fallback: number) {
  const quantities = [...text.matchAll(/(?:(共(?:计)?|合计|总数(?:为)?)|生成|出|给我|来|做|练|^)\s*([+-]?\d+(?:\.\d+)?|[零〇一二两三四五六七八九十百千万]+)\s*(?:道|题)/g)]
  const count = (quantities.find(match => match[1]) ?? quantities[0])?.[2]
  if (!count) return fallback
  if (/\d/.test(count)) return Number(count)
  return '零 一 二 三 四 五 六 七 八 九 十 十一 十二'.split(' ').indexOf(count.replace('两', '二'))
}

function calculationTopics(text: string): ExamTopic[] {
  const topics: ExamTopic[] = []
  const overflow = /补码(?:运算)?(?:与|和)?溢出|补码\s*(?:加法|减法|加减|运算)|(?:整数|加法|减法)\s*溢出/.test(text)
  if (overflow) topics.push('overflow')
  if (/补码(?:表示|编码|转换)/.test(text) || (!overflow && /补码/.test(text))) topics.push('complement')
  if (/浮点|阶码|尾数/.test(text)) topics.push('floating')
  if (/无向图|邻接矩阵/.test(text)) topics.push('graph')
  if (/\bcache\b|高速缓存|缓存(?:地址|映射)/i.test(text)) topics.push('cache')
  return topics
}

export function readGenerationRequest(requirement: string, hasFiles: boolean, defaultCount?: number): GenerationRequest {
  const text = requirement.normalize('NFKC').trim()
  const count = questionCount(text, defaultCount ?? (hasFiles ? 3 : 5))
  if (!Number.isInteger(count) || count < 1 || count > 12) {
    return { error: '每次支持 1–12 道单选题。请在要求中调整题量，例如“生成 5 道单选题”。' }
  }
  if (hasFiles) return { kind: 'material', questionCount: count }

  const topics = calculationTopics(text)
  const examNamed = /软考|软件设计师/.test(text)
  const mixed = (examNamed || topics.length > 0) && /综合计算|混合计算/.test(text)
  if (topics.length > 1 && !mixed) {
    return { error: '请选择一个计算考点，或写“生成 5 道软考综合计算题”。' }
  }
  const generic = /(?:软考|软件设计师)(?:考试)?(?:的)?\s*(?:综合|混合)?\s*计算(?:题|练习|专项)/.test(text)
  if (!topics.length && !mixed && !generic) {
    return { error: '请添加资料，或输入计算题要求，例如“生成 3 道软考补码题”。' }
  }
  if (/填空|多选|判断题|简答题|问答题|论述题/.test(text)) {
    return { error: '计算题目前按单选题生成。可以改写为“生成 3 道软考补码单选题”。' }
  }
  return { kind: 'exam', questionCount: count, topic: mixed ? 'mixed' : topics[0] ?? 'mixed' }
}

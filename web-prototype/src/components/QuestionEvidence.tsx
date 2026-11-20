import type { Question } from '../api/generation'

export function QuestionEvidence({ question }: { question: Question }) {
  const quote = question.ai.evidenceQuote?.trim()
  if (!quote || quote === question.explanation.trim()) return null
  return <details className="study-evidence">
    <summary>查看原文依据</summary>
    <figure><blockquote>{quote}</blockquote><figcaption>{question.ai.sourceLocation}</figcaption></figure>
  </details>
}

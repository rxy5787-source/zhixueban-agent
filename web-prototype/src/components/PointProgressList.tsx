import type { PointProgress } from '../api/generation'

type DisplayPoint = PointProgress & { sessionAnswered?: number; sessionCorrect?: number }

export function PointProgressList({ points }: { points: DisplayPoint[] }) {
  const priority = points.filter(point => point.reviewPriority)
  if (!points.length) return <p className="supporting">完成练习后，这里会显示知识点的掌握估计。</p>
  return <>
    <p className="supporting">{priority.length ? `优先复习：${priority.map(point => point.point).join('、')}` : '目前没有需要优先复习的知识点。'}</p>
    <ul className="mastery-list">
      {points.map(point => <li key={point.point}>
        <div><strong>{point.point}</strong><small>{point.sessionAnswered ? `本次 ${point.sessionCorrect}/${point.sessionAnswered} · ` : ''}累计答对 {point.correct}/{point.observations} 题{point.observations < 3 ? ' · 样本少' : ''}</small></div>
        <span className={point.reviewPriority ? 'mastery-weak' : ''}>估计 {Math.round(point.mastery * 100)}%</span>
      </li>)}
    </ul>
    <p className="supporting">掌握估计随作答更新。样本少时可用来安排复习，结论还会变化。</p>
  </>
}

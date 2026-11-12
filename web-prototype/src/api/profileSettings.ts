export type ProfileSettings = {
  nickname: string
  learningGoal: string
  avatar: 'profile' | 'book' | 'leaf'
  dailyTarget: number
  questionCount: number
  difficulty: 'auto' | 'basic' | 'intermediate' | 'advanced'
  weakFirst: boolean
}

const KEY = 'zhixue-profile-settings-v1'
export const DEFAULT_PROFILE: ProfileSettings = {
  nickname: '学习者', learningGoal: '', avatar: 'profile', dailyTarget: 10,
  questionCount: 0, difficulty: 'auto', weakFirst: false,
}

export function loadProfileSettings(): ProfileSettings {
  try {
    const value = JSON.parse(localStorage.getItem(KEY) ?? 'null')
    if (!value || typeof value !== 'object') return { ...DEFAULT_PROFILE }
    return {
      nickname: typeof value.nickname === 'string' && value.nickname.trim() ? value.nickname.trim().slice(0, 20) : DEFAULT_PROFILE.nickname,
      learningGoal: typeof value.learningGoal === 'string' ? value.learningGoal.trim().slice(0, 100) : '',
      avatar: ['profile', 'book', 'leaf'].includes(value.avatar) ? value.avatar : 'profile',
      dailyTarget: [5, 10, 20, 30].includes(value.dailyTarget) ? value.dailyTarget : 10,
      questionCount: [0, 3, 5, 10].includes(value.questionCount) ? value.questionCount : 0,
      difficulty: ['auto', 'basic', 'intermediate', 'advanced'].includes(value.difficulty) ? value.difficulty : 'auto',
      weakFirst: value.weakFirst === true,
    }
  } catch { return { ...DEFAULT_PROFILE } }
}

export function saveProfileSettings(value: ProfileSettings) {
  localStorage.setItem(KEY, JSON.stringify(value))
}

export function preferredRequirements(text: string, settings: ProfileSettings, weakPoints: string[]) {
  const additions: string[] = []
  const difficulty = { auto: '', basic: '基础', intermediate: '中等', advanced: '提高' }[settings.difficulty]
  if (difficulty && !/基础|简单|中等|提高|困难|难度/.test(text)) additions.push(`难度侧重${difficulty}。`)
  if ((settings.weakFirst || /薄弱/.test(text)) && weakPoints.length) {
    additions.push(`在资料支持的范围内优先考查这些待巩固知识点：${weakPoints.slice(0, 3).map(point => point.slice(0, 80)).join('、')}。`)
  }
  return [text.trim(), ...additions].filter(Boolean).join('\n')
}

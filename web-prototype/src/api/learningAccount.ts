let learner: string | undefined

export function setLearningAccount(username: string) { learner = username }

export function learningStorageKey(key: string) {
  return learner ? `account:${learner}:${key}` : key
}

export function learningFetch(path: string, options: RequestInit = {}) {
  if (!learner) return fetch(path, options)
  const headers = new Headers(options.headers)
  headers.set('X-Zhixue-Account', '1')
  headers.set('X-Zhixue-Learner', learner)
  return fetch(path, { ...options, headers }).then(response => {
    if (response.status === 401) location.replace('/account')
    return response
  })
}

export function applyLearningUploadHeaders(request: XMLHttpRequest) {
  if (!learner) return
  request.setRequestHeader('X-Zhixue-Account', '1')
  request.setRequestHeader('X-Zhixue-Learner', learner)
  request.addEventListener('load', () => {
    if (request.status === 401) location.replace('/account')
  })
}

/// <reference types="vite/client" />

export const onlineTrial = import.meta.env.VITE_ONLINE_TRIAL === "true"
export const staticDemo = import.meta.env.MODE === 'static-demo'
export const offlineStudy = import.meta.env.MODE === 'offline-study'

function configuredStudyOrigin(value?: string) {
  if (!value) return null
  try {
    const url = new URL(value)
    const local = url.protocol === 'http:' && ['localhost', '127.0.0.1'].includes(url.hostname)
      && ['localhost', '127.0.0.1'].includes(window.location.hostname)
    if ((url.protocol !== 'https:' && !local) || url.username || url.password ||
        url.pathname !== '/' || url.search || url.hash || url.origin === window.location.origin) return null
    return url.origin
  } catch { return null }
}

export const onlineStudyOrigin = configuredStudyOrigin(import.meta.env.VITE_STUDY_ONLINE_ORIGIN)

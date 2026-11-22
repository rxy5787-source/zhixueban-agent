import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { App } from './App'
import { StaticDemo } from './pages/StaticDemo'
import { OfflineStudy } from './pages/OfflineStudy'
import { offlineStudy, staticDemo } from './deployment'
import './styles/tokens.css'
import './styles/app.css'
import './styles/handbook.css'
import './styles/editorial.css'

const Root = offlineStudy ? OfflineStudy : staticDemo ? StaticDemo : App
createRoot(document.getElementById('root')!).render(<StrictMode><Root /></StrictMode>)

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { StaticDemo } from './pages/StaticDemo'
import { OfflineStudy } from './pages/OfflineStudy'
import { AccountLearning, AccountPage, GuestLearning } from './pages/AccountPage'
import { offlineStudy, staticDemo } from './deployment'
import './styles/tokens.css'
import './styles/app.css'
import './styles/handbook.css'
import './styles/editorial.css'

const Root = offlineStudy ? OfflineStudy : staticDemo ? StaticDemo
  : location.pathname === '/account' ? AccountPage
  : location.pathname === '/learn' ? AccountLearning : GuestLearning
createRoot(document.getElementById('root')!).render(<StrictMode><Root /></StrictMode>)

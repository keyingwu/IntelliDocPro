import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { FileSearch2, LayoutGrid } from 'lucide-react'
import { BrowserRouter, NavLink, Route, Routes } from 'react-router-dom'
import './app.css'
import { t } from './i18n'
import AgentsPage from './pages/AgentsPage'
import BuildWizard from './pages/BuildWizard'
import ResultsPage from './pages/ResultsPage'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
})

function Sidebar() {
  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <span className="brand-mark">
          <FileSearch2 size={19} strokeWidth={2.2} />
        </span>
        <span className="brand-text">
          <span className="brand-name">{t('app.name')}</span>
          <span className="brand-tagline">{t('app.tagline')}</span>
        </span>
      </div>
      <nav className="sidebar-nav">
        <NavLink to="/" end className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}>
          <LayoutGrid size={17} />
          {t('nav.agents')}
        </NavLink>
      </nav>
      <div className="sidebar-foot">v0.1 · IntelliDocPro</div>
    </aside>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <div className="shell">
          <Sidebar />
          <main className="main">
            <Routes>
              <Route path="/" element={<AgentsPage />} />
              <Route path="/build" element={<BuildWizard />} />
              <Route path="/build/:agentId" element={<BuildWizard />} />
              <Route path="/results/:agentId" element={<ResultsPage />} />
            </Routes>
          </main>
        </div>
      </BrowserRouter>
    </QueryClientProvider>
  )
}

import { useCallback, useEffect, useRef, useState } from 'react'
import * as api from './api'
import type { Preset, ScreeningJob } from './types'
import { ScreenView } from './ScreenView'
import { PresetsView } from './PresetsView'

const BotLogo = ({ size = 22, stroke = 1.8 }: { size?: number; stroke?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
    <line x1="12" y1="2" x2="12" y2="5" stroke="currentColor" strokeWidth={stroke} strokeLinecap="round" />
    <circle cx="12" cy="2.4" r="1.4" fill="currentColor" />
    <rect x="4" y="5.5" width="16" height="13" rx="4" stroke="currentColor" strokeWidth={stroke} />
    <circle cx="9" cy="11" r="1.5" fill="currentColor" />
    <circle cx="15" cy="11" r="1.5" fill="currentColor" />
    <path d="M9 15h6" stroke="currentColor" strokeWidth={stroke} strokeLinecap="round" />
    <line x1="4" y1="21.5" x2="20" y2="21.5" stroke="currentColor" strokeWidth={stroke} strokeLinecap="round" strokeDasharray="2.5 3" />
  </svg>
)

export { BotLogo }

const POLL_MS = 2000

export default function App() {
  const [view, setView] = useState<'screen' | 'presets'>('screen')
  const [theme, setTheme] = useState<'light' | 'dark'>(
    () => (localStorage.getItem('sb-theme') as 'light' | 'dark') || 'light',
  )
  const [presets, setPresets] = useState<Preset[]>([])
  const [jobs, setJobs] = useState<ScreeningJob[]>([])
  const [loadError, setLoadError] = useState<string | null>(null)
  const jobsRef = useRef(jobs)
  jobsRef.current = jobs

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('sb-theme', theme)
  }, [theme])

  const refreshPresets = useCallback(async () => {
    try {
      setPresets(await api.listPresets())
      setLoadError(null)
    } catch (e) {
      setLoadError(`Could not load presets — is the API running? (${(e as Error).message})`)
    }
  }, [])

  useEffect(() => {
    refreshPresets()
    // Hydrate jobs already running in this server process (e.g. after a reload).
    api.listScreenings().then(setJobs).catch(() => {})
  }, [refreshPresets])

  // Poll active jobs while any exist.
  useEffect(() => {
    const active = jobs.some((j) => j.status !== 'done' && j.status !== 'failed')
    if (!active) return
    const t = setInterval(async () => {
      const current = jobsRef.current
      const pending = current.filter((j) => j.status !== 'done' && j.status !== 'failed')
      const updates = await Promise.all(
        pending.map((j) => api.getScreening(j.id).catch(() => null)),
      )
      const byId = new Map(updates.filter(Boolean).map((j) => [j!.id, j!]))
      if (byId.size) {
        setJobs((prev) => prev.map((j) => byId.get(j.id) ?? j))
      }
    }, POLL_MS)
    return () => clearInterval(t)
  }, [jobs])

  const addJobs = useCallback((newJobs: ScreeningJob[]) => {
    setJobs((prev) => [...prev, ...newJobs])
  }, [])

  return (
    <div className="sb-app">
      <header className="sb-topbar">
        <div className="sb-logo">
          <BotLogo />
          <span>scorebot</span>
        </div>
        <nav className="sb-tabs">
          <button className={`sb-tab ${view === 'screen' ? 'sb-tab--on' : ''}`} onClick={() => setView('screen')}>
            Screen
          </button>
          <button className={`sb-tab ${view === 'presets' ? 'sb-tab--on' : ''}`} onClick={() => setView('presets')}>
            Presets
          </button>
        </nav>
        <div className="sb-spacer" />
        <button
          className="sb-iconbtn"
          title="Toggle dark mode"
          onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
        >
          {theme === 'dark' ? (
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <circle cx="12" cy="12" r="4" />
              <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
            </svg>
          ) : (
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
            </svg>
          )}
        </button>
      </header>

      {loadError && (
        <div className="sb-rejections" style={{ margin: '12px 24px' }}>
          <div className="msgs">
            <div className="msg">{loadError}</div>
          </div>
        </div>
      )}

      {view === 'screen' ? (
        <ScreenView presets={presets} jobs={jobs} onJobsAdded={addJobs} />
      ) : (
        <PresetsView presets={presets} onChanged={refreshPresets} />
      )}

      <footer className="sb-footer">
        <span>Scoring ignores name, gender, school, GPA, and location by design.</span>
        <span>·</span>
        <span>scorebot is a first-pass triage aid — a human reads every resume.</span>
      </footer>
    </div>
  )
}
